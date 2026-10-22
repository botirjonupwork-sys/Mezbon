"""AI Call Operator agent — Vapi/Retell/OpenAI orqali ovozli buyurtma.

Bu modul ovozli provayderdan keladigan TRANSCRIPT (matn)ni qabul qiladi va
OpenAI Function Calling yordamida mijoz bilan dialog olib boradi:
salomlashish → menyu taklifi → savatga qo'shish → manzil → tasdiqlash → order.

Catering xususiyati: agar bitta `catering_group` mahsulot uchun miqdor
restoran chegarasidan (catering_somsa_min/catering_nan_min) oshib ketsa,
buyurtma `order_kind="catering"` deb belgilanadi va mijoz catering kanaliga
yo'naltirilishi mumkin.

Sessiyalar in-memory dict'da saqlanadi (call_id -> AIConversation). Production
uchun Redis ga ko'chirish kerak (oddiy o'zgartirish — `_SESSIONS` ni almashtirish).
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.services import platform
from database.models import Product, Restaurant


OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"
SESSION_TTL = 60 * 30  # 30 daqiqa

# Restoran UI dan sozlanadigan qo'shimcha AI parametrlari (JSON)
AI_CONFIG_DEFAULTS: dict[str, Any] = {
    "offline_reply": "",           # bo'sh = standart matn
    "time_limit_reply": "",
    "upsell_enabled": True,        # qo'shimcha taklif (ichimlik/non)
    "sms_location_enabled": True,  # yetkazishda SMS pin-havola
    "sms_location_template": "",   # {order_id} {link}
    "system_prompt_override": "",  # to'liq asosiy prompt o'rniga (menyudan oldin)
    "farewell_hint": "",           # xayrlash uslubi / qo'shimcha
}


def get_ai_config(restaurant: Restaurant) -> dict[str, Any]:
    raw = getattr(restaurant, "ai_agent_config", None) or {}
    if not isinstance(raw, dict):
        raw = {}
    out = dict(AI_CONFIG_DEFAULTS)
    for k, default in AI_CONFIG_DEFAULTS.items():
        if k not in raw:
            continue
        val = raw[k]
        if isinstance(default, bool):
            out[k] = bool(val)
        elif isinstance(default, str):
            out[k] = "" if val is None else str(val)
        else:
            out[k] = val
    return out


# ── In-memory sessions ───────────────────────────────────────────────────

@dataclass
class CartItem:
    product_id: int
    name: str
    quantity: int
    price: float
    catering_group: Optional[str] = None  # 'somsa' | 'nan' | None


@dataclass
class AIConversation:
    call_id: str
    restaurant_id: int
    user_phone: str
    messages: list[dict] = field(default_factory=list)   # OpenAI chat formatida
    cart: list[CartItem] = field(default_factory=list)
    address: Optional[str] = None
    delivery_type: Optional[str] = None   # 'delivery' | 'pickup' | None — slot
    confirmed: bool = False
    started_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    # Xarajat hisobi
    tokens_in: int = 0
    tokens_out: int = 0
    stt_seconds: float = 0.0
    tts_chars: int = 0
    user_turn_count: int = 0
    greeted: bool = False                       # operator salomlashdimi (call-start)
    order_placed: bool = False                  # shu qo'ng'iroqda kamida 1 buyurtma
    last_order_id: Optional[int] = None
    conversation_ended: bool = False            # xayrlashib suhbat tugadimi
    # Oxirgi LLM javobidan rate-limit holati (qolgan so'rov/token) — provayder bersa
    last_rate_limit: dict = field(default_factory=dict)
    # Tartibli transcript (DB'ga yozish uchun)
    transcript_log: list[dict] = field(default_factory=list)

    def elapsed_minutes(self) -> float:
        return (time.time() - self.started_at) / 60.0

    def add_transcript(self, role: str, content: str) -> None:
        self.transcript_log.append({"role": role, "content": content, "ts": int(time.time())})

    def cart_total(self) -> float:
        return sum(i.price * i.quantity for i in self.cart)

    def cart_summary(self) -> str:
        if not self.cart:
            return "savat bo'sh"
        lines = [f"{i.name} x{i.quantity} = {i.price * i.quantity:,.0f} so'm" for i in self.cart]
        lines.append(f"JAMI: {self.cart_total():,.0f} so'm")
        return "; ".join(lines)


_SESSIONS: dict[str, AIConversation] = {}


def _gc_sessions() -> None:
    """Eskirgan sessiyalarni tozalash (TTL)."""
    now = time.time()
    stale = [k for k, v in _SESSIONS.items() if now - v.last_active > SESSION_TTL]
    for k in stale:
        _SESSIONS.pop(k, None)


def get_session(call_id: str, restaurant_id: int, user_phone: str) -> AIConversation:
    _gc_sessions()
    sess = _SESSIONS.get(call_id)
    if sess is None:
        sess = AIConversation(call_id=call_id, restaurant_id=restaurant_id, user_phone=user_phone)
        _SESSIONS[call_id] = sess
    sess.last_active = time.time()
    return sess


def end_session(call_id: str) -> None:
    _SESSIONS.pop(call_id, None)


def get_greeting_text(restaurant: Restaurant) -> str:
    """Qo'ng'iroq boshidagi operator tabrigi (telefon qo'ng'irog'i kabi birinchi gap)."""
    default = (
        f"Assalomu alaykum! '{restaurant.name}' restorani. "
        "Menyumiz bilan tanishasizmi yoki to'g'ridan-to'g'ri buyurtma berasizmi?"
    )
    custom = (getattr(restaurant, "ai_agent_greeting", None) or "").strip()
    return custom or default


def reset_after_order(sess: AIConversation, order_id: int) -> None:
    """Buyurtma yaratilgach savatni tozalab, post-buyurtma bosqichiga o'tkazish."""
    sess.order_placed = True
    sess.last_order_id = order_id
    sess.cart.clear()
    sess.address = None
    sess.delivery_type = None
    sess.confirmed = False


async def start_call_session(
    restaurant: Restaurant,
    sess: AIConversation,
) -> dict:
    """Qo'ng'iroq ulanishi — operator birinchi gapiradi (SIP/chat bir xil)."""
    greeting = get_greeting_text(restaurant)
    sess.greeted = True
    sess.add_transcript("assistant", greeting)
    if not sess.messages:
        sess.messages.append({"role": "system", "content": "(system prompt keyingi turn'da to'ldiriladi)"})
    sess.messages.append({"role": "assistant", "content": greeting})
    return {
        "reply": greeting,
        "is_greeting": True,
        "greeted": True,
        "cart": [],
        "address": None,
        "confirmed": False,
        "transferred": False,
        "is_catering": False,
    }


# ── Xarajat hisobi va DB log yozish ──────────────────────────────────────

# LLM tarif (per 1M tokens). Provayderlar bo'yicha — 2026-05 yangilangan.
# Groq/Gemini bepul tier'da $0, lekin pullik o'tishda hisoblansin.
_LLM_RATES = {
    # OpenAI
    "gpt-4o-mini":      (0.15, 0.60),
    "gpt-4o":           (2.50, 10.00),
    "gpt-4.1-mini":     (0.40, 1.60),
    "gpt-4.1":          (2.00, 8.00),
    # Anthropic
    "claude-haiku-4-5":  (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-7":   (15.00, 75.00),
    # Gemini (faqat pullik tier)
    "gemini-1.5-pro":    (1.25, 5.00),
    # Bepul modellar — taxminiy 0 (Groq, Gemini free)
    "llama-3.3-70b-versatile": (0.0, 0.0),
    "llama-3.1-70b-versatile": (0.0, 0.0),
    "llama-3.1-8b-instant":    (0.0, 0.0),
    "mixtral-8x7b-32768":      (0.0, 0.0),
    "gemma2-9b-it":            (0.0, 0.0),
    "gemini-2.0-flash":        (0.0, 0.0),
    "gemini-2.0-flash-lite":   (0.0, 0.0),
    "gemini-1.5-flash":        (0.0, 0.0),
}


def _llm_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    rate_in, rate_out = _LLM_RATES.get(model, (0.0, 0.0))
    return (tokens_in * rate_in + tokens_out * rate_out) / 1_000_000.0


def estimate_session_cost(sess: AIConversation) -> float:
    """Sessiya jami xarajati ($).

    LLM + Whisper STT (per second) + OpenAI TTS (per char).
    Tariflar moslashtirilishi mumkin (2026-05 dagi rate'lar).
    """
    model = _platform_model()
    cost = _llm_cost(model, sess.tokens_in, sess.tokens_out)
    cost += (sess.stt_seconds / 60.0) * 0.006     # Whisper
    cost += (sess.tts_chars / 1_000_000.0) * 15.0  # TTS-1
    return round(cost, 6)


async def finalize_session(
    db,
    call_id: str,
    ended_reason: str,
    order_id: Optional[int] = None,
) -> None:
    """Sessiyani yopib, DB'ga `AICallLog` yozib qo'yadi.

    `end_session` o'rniga shu funksiyani chaqiring, agar call yakunlangan bo'lsa.
    Xato bo'lsa logda yozadi — har holda asosiy oqimni to'xtatmaydi.
    """
    sess = _SESSIONS.pop(call_id, None)
    if sess is None:
        return
    try:
        from database.models import AICallLog
        from datetime import datetime
        log = AICallLog(
            call_id=sess.call_id,
            restaurant_id=sess.restaurant_id,
            user_phone=sess.user_phone,
            started_at=datetime.utcfromtimestamp(sess.started_at),
            ended_at=datetime.utcnow(),
            duration_seconds=time.time() - sess.started_at,
            message_count=sess.user_turn_count,
            tokens_in=sess.tokens_in,
            tokens_out=sess.tokens_out,
            stt_seconds=sess.stt_seconds,
            tts_chars=sess.tts_chars,
            cost_usd=estimate_session_cost(sess),
            transcript=json.dumps(sess.transcript_log, ensure_ascii=False),
            order_id=order_id,
            ended_reason=ended_reason,
        )
        db.add(log)
        await db.commit()
    except Exception as e:
        from api.logging_config import log_critical
        log_critical("ai_agent", "AICallLog save failed", error=str(e), call_id=call_id)
        try:
            await db.rollback()
        except Exception:
            pass


# ── Menyu yuklash ────────────────────────────────────────────────────────

async def load_menu(db: AsyncSession, restaurant_id: int) -> list[Product]:
    """Restoranning faol va STOP'da bo'lmagan mahsulotlari."""
    result = await db.execute(
        select(Product).where(
            Product.restaurant_id == restaurant_id,
            Product.is_active == True,
            Product.is_stop == False,
        ).order_by(Product.category_id, Product.id)
    )
    return list(result.scalars().all())


async def load_categories(db: AsyncSession, restaurant_id: int) -> dict[int, str]:
    """Restoranning faol kategoriyalari: {id: name_uz}."""
    from database.models import Category
    result = await db.execute(
        select(Category).where(
            Category.restaurant_id == restaurant_id,
            Category.is_active == True,
        ).order_by(Category.order, Category.id)
    )
    return {c.id: c.name_uz for c in result.scalars().all()}


def menu_to_text(products: list[Product], categories: Optional[dict[int, str]] = None) -> str:
    """AI uchun menyu — kategoriyalar bo'yicha guruhlangan.

    Format:
      [Kategoriya 1]
      #1 — Mahsulot — 5,000 so'm
      #2 — Mahsulot 2 — 6,000 so'm

      [Kategoriya 2]
      ...

    Bu ko'rinish AI'ga "qaysi kategoriya kerak?" deb so'rashga yordam beradi.
    """
    if not products:
        return "(Menyu bo'sh)"
    cats = categories or {}
    by_cat: dict[int, list[Product]] = {}
    for p in products:
        by_cat.setdefault(p.category_id or 0, []).append(p)

    lines: list[str] = []
    for cat_id, items in by_cat.items():
        cat_name = cats.get(cat_id, "Boshqa")
        lines.append(f"\n[{cat_name}]")
        for p in items:
            ctype = " [catering]" if (p.product_type or "regular") == "catering" else ""
            lines.append(f"#{p.id} {p.name_uz} — {int(p.price):,} so'm{ctype}")
    return "\n".join(lines).strip()


def categories_to_text(categories: dict[int, str]) -> str:
    """Faqat kategoriya nomlarini ro'yxat qilib chiqaradi (AI'ga 'menyuda nima bor' uchun)."""
    if not categories:
        return ""
    return ", ".join(categories.values())


# ── System prompt va tool schemas ────────────────────────────────────────

_LANGUAGE_INSTRUCTIONS = {
    "uz": "Mijoz bilan o'zbek tilida (jonli, qisqa va xushmuomala) gaplashasan.",
    "ru": "Общайся с клиентом на русском языке (живо, кратко и вежливо).",
    "auto": (
        "Mijoz qaysi tilda gaplashsa shu tilda javob ber (o'zbek yoki rus). "
        "Standart — o'zbek tili."
    ),
}


def _language_instruction(restaurant: Restaurant) -> str:
    lang = (getattr(restaurant, "ai_agent_language", None) or "uz").lower()
    return _LANGUAGE_INSTRUCTIONS.get(lang, _LANGUAGE_INSTRUCTIONS["uz"])


def build_system_prompt(
    restaurant: Restaurant,
    menu_text: str,
    categories_list: str = "",
) -> str:
    """Restoranga moslangan system prompt — qadam-qadam suhbat shabloni.

    Muhim: AI faqat shu restoranning menyusidan mahsulot taklif qiladi va
    narxlarni faqat shu yerdagi ro'yxatdan oladi.
    """
    cfg = get_ai_config(restaurant)
    greeting_default = get_greeting_text(restaurant)
    greeting = greeting_default

    category_hint = (
        f"Bizdagi kategoriyalar: {categories_list}." if categories_list else ""
    )

    # Admin to'liq asosiy promptni o'zi yozgan bo'lsa — shundan foydalanamiz
    override = (cfg.get("system_prompt_override") or "").strip()
    if override:
        parts = [override]
        custom = (restaurant.ai_agent_prompt or "").strip()
        if custom:
            parts.append(f"\nRestoran maxsus ko'rsatmasi:\n{custom}")
        farewell = (cfg.get("farewell_hint") or "").strip()
        if farewell:
            parts.append(f"\nXayrlash / yakunlash uslubi:\n{farewell}")
        if not cfg.get("upsell_enabled", True):
            parts.append(
                "\nQO'SHIMCHA TAKLIF O'CHIRILGAN: ichimlik/non upsell qilma, "
                "darhol yetkazish turi va manzilga o't."
            )
        parts.append(
            f"\nRESTORAN: {restaurant.name}\n"
            f"ISH VAQTI: {restaurant.work_hours_from}–{restaurant.work_hours_until}\n"
            f"MIN. BUYURTMA: {int(restaurant.min_order or 0):,} so'm\n"
            f"\nMENYU (kategoriyalar bo'yicha, faqat shu mahsulotlar taklif qilinadi):\n{menu_text}"
        )
        return "\n".join(parts)

    base = (
        f"Sen '{restaurant.name}' restoranining do'stona SOTUV operatorisan. "
        f"{_language_instruction(restaurant)} "
        "Javoblar qisqa va tabiiy, xushmuomala va jonli bo'lsin — odam operator kabi. "
        "Maqsading: mijozga yordam berib, savollariga to'g'ri javob berib va "
        "YUMSHOQ tavsiyalar bilan to'g'ri buyurtma yig'ish (bosim qilmasdan).\n\n"

        "OVOZ KANALI (muhim):\n"
        "- Mijoz matni OVOZDAN matnga aylantirilgan (STT) — unda xato bo'lishi mumkin. "
        "Noaniq joyni TAXMIN QILMA, qisqa aniqlashtirib so'ra.\n"
        "- Sening javobing OVOZGA aylantiriladi (TTS): oddiy, gapiriladigan jumlalar ishlat. "
        "Ro'yxat belgilari, emoji, qavs, maxsus formatlash ISHLATMA — faqat tabiiy gap.\n"
        "- Qisqa bo'l, lekin to'liq javob ber (sun'iy ravishda kesib qisqartirma).\n\n"

        "FAQAT MA'LUMOTGA ASOSLAN (eng muhim qoida):\n"
        "- Faqat quyida berilgan MENYU va restoran ma'lumotidan javob ber. "
        "Narx, tarkib, ish vaqti — hammasi shu ro'yxatdan olinadi.\n"
        "- Agar javobni aniq bilmasang — TAXMIN QILMA. Halol ayt: "
        "'Buni aniq bilmayman, tekshirib aytaman' yoki operatorga uzat. "
        "Noto'g'ri ishonchli javob berishdan ko'ra 'bilmayman' deyish yaxshiroq.\n"
        "- HALAL / ALLERGIYA / tarkib bo'yicha: faqat menyuda ANIQ yozilган narsani ayt. "
        "Aniq belgilanmagan bo'lsa: 'Buni kafolat bilan ayta olmayman, oshxona bilan "
        "tasdiqlatib beraman' deb ayt — taxmin qilib aytma (bu sog'liq masalasi).\n\n"

        "SOTUV USLUBI (yumshoq — hech qachon majburlama):\n"
        "- Mijoz ikkilansa yoki 'nima bor?' desa — eng mashhur 1-2 taomni tavsiya qil.\n"
        "- ASOSIY taom savatga qo'shilgach, yetkazish turini so'rashdan OLDIN — ALBATTA "
        "BIR MARTA tabiiy, vaziyatga mos qo'shimcha taklif qil ('Yana nimadir qo'shamizmi?' "
        "yoki aniqroq). Bu majburiy bosqich, lekin YUMSHOQ va qisqa bo'lsin.\n"
        "- TAKLIF ANIQ bo'lsin — umumiy 'ichimlik qo'shamizmi?' emas, menyudagi BOSHQA "
        "kategoriyadan 1-2 ta HAQIQIY mahsulot nomini ayt (narxi bilan bo'lsa yana yaxshi):\n"
        "  • Somsa/issiq taom olsa → menyudagi ICHIMLIKLAR yoki NON dan aniq nom ayt "
        "('Yoniga Coca Cola yoki ayron olasizmi?').\n"
        "  • Ko'p taom (mehmon/oila) olsa → NON yoki SALAT dan aniq nom taklif qil.\n"
        "  • Faqat ichimlik olsa → somsa yoki biror taomni aniq nom bilan taklif qil.\n"
        "  Nomlar va narxlar FAQAT pastdagi menyudan olinsin (o'zingdan o'ylab topma).\n"
        "- Savatda ALLAQACHON bor narsani qayta taklif QILMA. Maksimum 1 marta taklif "
        "(eng ko'pi 2 narsa), bir nafasда stack qilma.\n"
        "- Mijoz 'yo'q' desa yoki qisqa/sovuq javob bersa — DARHOL to'xta, qaytarma, "
        "buyurtmani sodda yakunlashga o't. Bezor qilma. Hurmat muhim.\n"
        "- Taklif faqat MENYUDAGI mahsulotlardan bo'lsin. Maqtov ortiqcha bo'lmasin — "
        "tabiiy, do'stona ohangда (qo'pol/bosimli emas).\n\n"

        "SUHBAT OQIMI (har bosqichni o'tkazib yubormaslik kerak):\n"
        "1. SALOMLASHISH: agar JORIY HOLATda 'Salomlashish: bajarildi' bo'lsa — QAYTA "
        f"salomlashma (qo'ng'iroq allaqachon boshlangan). Aks holda: \"{greeting}\"\n"
        "2. AGAR MIJOZ MENYU SO'RASA: Kategoriyalarni ro'yxat qil va so'ra: "
        f"'{category_hint} Qaysi turidan boshlaymiz?'\n"
        "3. AGAR MIJOZ KATEGORIYA TANLASA: Shu kategoriyadagi mahsulotlarni "
        "narx bilan sanab ber. Yana yangi mahsulot taklif qilma.\n"
        "4. AGAR MIJOZ TO'G'RIDAN-TO'G'RI BUYURTMA BERSA: mahsulot va miqdorni "
        "add_to_cart bilan saqla. Mijoz bir vaqtda bir nechta narsa aytsa "
        "(masalan: '3 ta somsa va manzilim Chilonzor 5'), hammasini bir bora qabul qil "
        "— bir necha tool chaqir va qayta so'rama.\n"
        "5. QO'SHIMCHA TAKLIF (asosiy taom qo'shilgach, BIR MARTA — o'tkazib yuborma): "
        "savatga qarab vaziyatga mos yumshoq taklif qil ('Yoniga ayron yoki non olasizmi?'). "
        "Agar mijoz allaqachon yetkazish/manzilni ham aytgan bo'lsa yoki 'shu yetarli' degan "
        "bo'lsa — taklifni o'tkazib yubor. Mijoz rad etsa — qaytarma.\n"
        "6. SAVAT BO'SH EMAS BO'LGACH (agar yetkazish_turi hali tanlanmagan bo'lsa): "
        "so'ra: 'Yetkazib beraylikmi yoki o'zingiz olib ketasizmi?' "
        "→ Javobiga ko'ra set_delivery_type chaqir.\n"
        "7. MANZIL (delivery tanlansa):\n"
        "   - AGAR mijoz manzilni aytgan bo'lsa (qisqa bo'lsa ham, masalan 'Otchopar 1/2') — "
        "uni DARHOL set_address bilan saqla. Aytilganni E'TIBORSIZ QOLDIRIB qaytadan so'rama.\n"
        "   - Keyin TO'LIQROQ qilishni so'ra (aniq yetkazish uchun): 'Otchopar 1/2 — qabul "
        "qildim. To'liqroq aytasizmi: uy yoki kvartira raqami va mo'ljal (yaqin belgili joy)?' "
        "Mijoz qo'shimcha aytsa — set_address'ni to'liq manzil bilan yangila va tasdiqla "
        "('Manzilingiz: ... — to'g'rimi?').\n"
        "   - Mijoz 'shu yetarli' yoki boshqa narsa qo'shmasa — bor manzilni tasdiqlab davom et.\n"
        "   - Manzil umuman aytilmagan bo'lsa: 'Manzilingizni ayting — ko'cha, uy va mo'ljal.'\n"
        "8. BARCHA MA'LUMOT TO'LGANIDA (savat + yetkazish_turi + delivery'da manzil): "
        "view_cart bilan tekshir va mijozga jamlamani ayt: mahsulotlar, JAMI SUMMA, "
        "yetkazish turi, manzil. So'ra: 'Tasdiqlaysizmi?'\n"
        "9. AGAR MIJOZ 'HA, TASDIQLAYMAN' DESA: confirm_order chaqir.\n"
        "   Buyurtma tasdiqlangach javobda: qabul qilinganini ayt, yetkazish bo'lsa SMS "
        "haqida eslat (qadam 7b), keyin ALBATTA so'ra: 'Yana biror narsa buyurtma "
        "qilasizmi yoki boshqa savolingiz bormi?'\n"
        "10. POST-BUYURTMA (buyurtma allaqachon qabul qilingan, savat bo'sh):\n"
        "   - Mijoz yana buyurtma desa → start_new_order chaqir, yangi buyurtma boshla.\n"
        "   - Mijoz faqat savol bersa → javob ber, keyin yana 'Yana biror narsa?' deb so'ra.\n"
        "   - Mijoz 'yo'q/rahmat/shu yetarli/xayr/yo'q boshqa narsa yo'q' desa → iliq "
        "xayrlash va end_conversation chaqir.\n"
        "11. SUHBATNI YAKUNLASH (telefon qo'yilgandek):\n"
        "   - Xayrlash qisqa, iliq va tabiiy bo'lsin. Restoran nomini aytish mumkin.\n"
        "   - Namuna: 'Rahmat! Buyurtmangiz tez orada yetkaziladi. Yana savolingiz bo'lmasa, "
        "xayr va sog' bo'ling!'\n"
        "   - end_conversation faqat xayrlashgandan KEYIN chaqir — suhbatni yopadi.\n"
        "   - Buyurtma bo'lmasa ham mijoz 'xayr' desa — xayrlash va end_conversation.\n\n"

        "MANZIL VA ANIQ JOY (yetkazish uchun — operator suhbatida):\n"
        "7b. YETKAZISH MANZILI — ikki bosqich (suhbat + SMS):\n"
        "   - SUHBATDA: mijozdan MATN manzil oling (tuman, ko'cha, uy/kvartira, mo'ljal). "
        "set_address bilan saqlang.\n"
        "   - BUYURTMA TASDIQLANGACH: tizim mijoz telefoniga SMS yuboradi — unda xarita "
        "havolasi bor, mijoz aniq pin qo'yadi (kuryer shu joyga keladi).\n"
        "   - Suhbatda ayt: 'Telefoningizga SMS keladi, aniq yetkazish joyini xaritada "
        "belgilang' yoki qisqaroq shaklda.\n"
        "   - PICKUP (olib ketish) bo'lsa manzil va SMS kerak emas.\n\n"

        "NAMUNA SUHBATLAR (uslub va to'g'ri xatti-harakat uchun — shu na'munalarga ergash):\n"

        "1) Oddiy buyurtma + narx aytish + aniq upsell:\n"
        "Mijoz: 'Salom, nima bor?'\n"
        "Sen: 'Assalomu alaykum! Eng mashhuri — go'shtli somsa, 14 000 so'm. Nechta olamiz?'\n"
        "Mijoz: '3 ta'\n"
        "Sen: (add_to_cart) 'Bo'ldi, 3 ta go'shtli somsa — 42 000 so'm. Yoniga Coca Cola yoki ayron olasizmi?'\n"
        "Mijoz: 'Yo'q, rahmat'\n"
        "Sen: 'Mayli. Yetkazib beraylikmi yoki o'zingiz olib ketasizmi?'\n\n"

        "1b) Narx savoli (DARHOL ayt — e'tiborsiz qoldirma):\n"
        "Mijoz: 'Coca Cola 1.5 qancha?'\n"
        "Sen: 'Coca Cola 1.5 litr — 18 000 so'm. Qo'shaymizmi?' (narx menyudan; misol uchun)\n\n"

        "2) Ko'p narsa bir gapda + yetkazish so'zi (ENG MUHIM — qayta so'rama!):\n"
        "Mijoz: 'Tovuqli somsa 4 ta dastafka qibering'\n"
        "Sen: (add_to_cart: tovuqli somsa x4 VA set_delivery_type: delivery — IKKALASI birga) "
        "'Bo'ldi, 4 ta tovuqli somsa, yetkazib beramiz. Manzilingizni ayting — tuman, ko'cha, uy va mo'ljal.'\n"
        "(DIQQAT: yetkazish turini QAYTA SO'RAMADIK, chunki 'dastafka' allaqachon delivery degani.)\n\n"

        "3) Pickup (o'zi olib ketish) variantlari:\n"
        "Mijoz: 'Ikkita kartoshkali, o'zim olaman'\n"
        "Sen: (add_to_cart: kartoshkali somsa x2 VA set_delivery_type: pickup) "
        "'Bo'ldi, 2 ta kartoshkali somsa, o'zingiz olib ketasiz. Tasdiqlaymizmi?'\n\n"

        "4) Manzil + miqdor bitta gapda → tasdiqlash uchun qaytar (qayta SO'RAMA):\n"
        "Mijoz: 'Manzilim Chilonzor 9-kvartal 5-uy, 4 ta go'shtli somsa keltiring'\n"
        "Sen: (add_to_cart: go'shtli somsa x4; set_delivery_type: delivery; set_address: Chilonzor 9-kvartal 5-uy) "
        "'Manzilingiz: Chilonzor 9-kvartal, 5-uy — to'g'rimi?'\n\n"

        "4b) Qisqa manzil + dostavka bitta gapda (qabul qil + to'liqroq so'ra):\n"
        "Mijoz: 'Otchopar 1/2 dastafka qiberin'\n"
        "Sen: (set_delivery_type: delivery; set_address: Otchopar 1/2) "
        "'Otchopar 1/2 — qabul qildim. To'liqroq aytasizmi: uy yoki kvartira raqami va mo'ljal?'\n"
        "Mijoz: '4-kvartira, Korzinka yonida'\n"
        "Sen: (set_address: Otchopar 1/2, 4-kvartira, Korzinka yonida) "
        "'Manzilingiz: Otchopar 1/2, 4-kvartira (Korzinka yonida) — to'g'rimi?'\n"
        "(NOTO'G'RI: aytilgan manzilni e'tiborsiz qoldirib 'Manzilingizni ayting' deб qaytadan so'rash.)\n\n"

        "5) Menyuда yo'q narsa:\n"
        "Mijoz: 'Olot somsa bormi?'\n"
        "Sen: 'Kechirasiz, olot somsa yo'q. Bizda go'shtli, kartoshkali, tovuqli somsa bor — qaysi biridan olamiz?'\n"
        "(MUHIM: menyuда yo'q narsani 'bormi?' deб o'zing taklif qilma.)\n\n"

        "6) Tarkib / halal savoli (faqat aniq ma'lumot, aks holda eskalatsiya):\n"
        "Mijoz: 'Tovuqli somsa halalmi?'\n"
        "Sen (agar menyuда aniq belgi bo'lsa): 'Ha, tovuqli somsa halal.'\n"
        "Sen (agar aniq belgilanmagan bo'lsa): 'Buni kafolat bilan ayta olmayman, oshxona bilan tasdiqlatib beraman.' "
        "(taxmin qilib 'ha' DEMA.)\n\n"

        "7) Tavsiya so'rasa:\n"
        "Mijoz: 'Nima tavsiya qilasiz?'\n"
        "Sen: 'Eng ko'p olinadigani — go'shtli somsa va tovuqli somsa. Qaysi biridan boshlaymiz?'\n\n"

        "8) Tuzatish (mijoz fikrini o'zgartirsa):\n"
        "Mijoz: 'Yo'q, 4 ta emas, 3 ta bo'lsin'\n"
        "Sen: (add_to_cart/miqdorni 3 ga to'g'rila) 'Tuzatdim — 3 ta. Yana biror narsa kerakmi?'\n\n"

        "9) Tushunmaslik (generik 'tushunmadim' EMAS — aniq narsani so'ra):\n"
        "Mijoz: '...(noaniq)...'\n"
        "Sen: 'Uzr, nechta somsa edi — aniqroq aytasizmi?'\n\n"

        "10) Katta miqdor (tadbir) → catering:\n"
        "Mijoz: 'Tadbirga 200 ta somsa kerak'\n"
        "Sen: (transfer_to_catering) 'Bu katta buyurtma — catering bo'limimiz siz bilan bog'lanadi.'\n\n"

        "11) Buyurtma tasdiqlangach + yana savol:\n"
        "Mijoz: 'Ha, tasdiqlayman'\n"
        "Sen: (confirm_order) 'Buyurtmangiz qabul qilindi! Telefoningizga SMS keladi — "
        "aniq yetkazish joyini xaritada belgilang. Yana biror narsa buyurtma qilasizmi?'\n"
        "Mijoz: 'Yo'q, rahmat'\n"
        "Sen: (end_conversation) 'Rahmat! Tez orada yetkazamiz. Xayr, sog' bo'ling!'\n\n"

        "12) Ikkinchi buyurtma (bir qo'ng'iroqda):\n"
        "Mijoz: 'Ha, yana 2 ta go'shtli somsa qo'shing'\n"
        "Sen: (start_new_order, keyin add_to_cart) 'Albatta. 2 ta go'shtli somsa — ...'\n\n"

        "MUHIM QOIDALAR:\n"
        "- 'JORIY BUYURTMA HOLATI' blokiga QARAB ish tut: u yerда ko'rsatilgan to'lgan "
        "slotlarni (savat, yetkazish turi, manzil) mijozdan QAYTA SO'RAMA — faqat "
        "'Yetishmayotgan' deb belgilanganini so'ra.\n"
        "- Mijoz bitta gapда bir nechta narsa aytsa — HAMMASINI bir vaqtda qabul qil, "
        "tegishli tool'larni BIRGA chaqir, qayta so'rama. Masalan men 'Nechta kartoshkali "
        "somsa?' deб so'raganimда mijoz '4 ta, dastavka qiling' desa: add_to_cart(kartoshkali "
        "somsa, 4) VA set_delivery_type('delivery') ni birga chaqir — keyin faqat MANZILni so'ra "
        "(yetkazish turini qayta so'rama!).\n"
        "- Slot to'lgach faqat TASDIQLASH uchun qisqa qaytar ('Manzilingiz ... — to'g'rimi?'), "
        "lekin ma'lumotni qaytadan SO'RAMA.\n"
        "- Faqat menyudagi mahsulotlarni taklif qil (narx/ID menyudan).\n"
        "- Menyuda yo'q narsani taklif qilma. Mijoz so'rasa: 'Kechirasiz, bizda yo'q'.\n"
        "- confirm_order chaqirishdan oldin barcha slot to'la bo'lsin. "
        "Server validatsiyasi xato qaytarsa, yetishmayotgan ma'lumotni so'ra.\n"
        "- Tadbir uchun katta miqdor (100+ somsa, 40+ non) — transfer_to_catering.\n"
        "\n"

        "MIJOZ SAVOLLARIGA JAVOB (FAQ):\n"
        "- NARX: mijoz 'qancha?', 'narxi?', 'necha pul?' deб so'rasa — DARHOL menyudagi "
        "ANIQ narxni ayt (so'm bilan). Narx savolini hech qachon e'tiborsiz qoldirma.\n"
        "- Mahsulot savatga qo'shganda ham narxini ayt — masalan: 'Bo'ldi, 5 ta kartoshkali "
        "somsa — 35 000 so'm. Yana nimadir kerakmi?'\n"
        "- Ish vaqti, yetkazish, tarkib so'ralsa — menyu/restoran ma'lumotidan "
        "QISQA javob ber, keyin tabiiy ravishda buyurtmaga qaytar.\n"
        "- Ro'yxatda bo'lmagan narsani so'rasa: 'Kechirasiz, bizda yo'q' va bori bilan yordam taklif qil.\n"
        "- Bilmaydigan savol (siyosat, qaytarish, hujjat va h.k.) — taxmin qilma, "
        "'Buni aniq bilmayman' deb operatorga uzat.\n\n"

        "TUSHUNMASLIK VA TUZATISH:\n"
        "- Tushunmasang, generik 'tushunmadim' dema — yetishmayotgan ANIQ narsani qayta so'ra "
        "(masalan: 'Nechta somsa edi?'). Bu mijozga eshitganingni bildiradi.\n"
        "- Bir narsani 3 martadan ortiq tushunmasang — uzr so'rab, operatorga ulashni taklif qil.\n"
        "- Mijoz 'yo'q, ...' desa yoki fikrini o'zgartirsa — eski qadamni tuzat va qayta ko'rib chiq, "
        "ortiqcha uzr so'rama, darhol yangi gapига o't.\n"
        "\n"
        "YETKAZISH TURINI MA'NOSIGA QARAB ANIQLA (so'zning aniq shakliga emas, MA'NOGA qara):\n"
        "- Mijoz 'menga keltir / olib kelib ber / yetkaz / uyimga / manzilga / eshikkacha' "
        "MA'NOSIDA biror so'z aytsa → DELIVERY. Bunga 'dastavka', 'dastafka', 'dostavka', "
        "'dastavka qiling', 'qib bering', 'yetkazib bering', 'olib keling' va shu kabi HAR QANDAY "
        "buzilgan/STT variant kiradi → set_delivery_type('delivery').\n"
        "- Mijoz 'o'zim olaman / o'zim kelaman / olib ketaman / kelib olaman' MA'NOSINI bersa "
        "(masalan 'savoy', 'saboy', 'soyim', 'ozim', 'pikap' kabi STT variantlari) → PICKUP "
        "→ set_delivery_type('pickup').\n"
        "- MUHIM: mijoz buyurtma bilan BIRGA yetkazish so'zini aytsa (masalan 'tovuqli somsa 4 ta "
        "dastafka qibering') — add_to_cart VA set_delivery_type('delivery') ni DARHOL birga chaqir, "
        "keyin yetkazish turini QAYTA SO'RAMA, faqat manzilni so'ra.\n"
        "- Ma'no haqiqatan noaniq bo'lsagina so'ra: 'Yetkazib beraylikmi yoki o'zingiz olib ketasizmi?'\n"
        "STT BOSHQA XATOLARI:\n"
        "- Raqamlar: 'тут' → 'to'rt' (4); 'бир-икки' → 'bir-ikki' (1-2, aniqlashtir); "
        "'ани' → 'ana o'sha' (oldingi nomga).\n"
        "- Agar mijoz 'yo'q, ...' deb gap boshlasa — bu rad etish/tuzatish. "
        "Oldingi qadamni qayta ko'rib chiq.\n"
        "- Ovoz/matn juda noaniq bo'lsa — taxmin qilma, aniq so'ra."
    )

    parts = [base]

    if not cfg.get("upsell_enabled", True):
        parts.append(
            "\nQO'SHIMCHA TAKLIF O'CHIRILGAN: 5-bosqich (upsell) ni o'tkazib yubor. "
            "Ichimlik/non taklif qilma — darhol yetkazish turi va manzilga o't."
        )

    custom = (restaurant.ai_agent_prompt or "").strip()
    if custom:
        parts.append(f"\nRestoran maxsus ko'rsatmasi:\n{custom}")

    farewell = (cfg.get("farewell_hint") or "").strip()
    if farewell:
        parts.append(f"\nXayrlash / yakunlash uslubi:\n{farewell}")

    fallback_phone = (getattr(restaurant, "ai_agent_fallback_phone", None) or "").strip()
    if fallback_phone:
        parts.append(
            f"\nAgar mijozning so'rovini tushuna olmasang yoki murakkab vaziyat bo'lsa, "
            f"unga ayting: 'Operator bilan bog'lanish uchun {fallback_phone} raqamiga qo'ng'iroq qiling.'"
        )

    if not cfg.get("sms_location_enabled", True):
        parts.append(
            "\nSMS PIN O'CHIRILGAN: buyurtmadan keyin xarita SMS haqida gapirma."
        )

    parts.append(
        f"\nRESTORAN: {restaurant.name}\n"
        f"ISH VAQTI: {restaurant.work_hours_from}–{restaurant.work_hours_until}\n"
        f"MIN. BUYURTMA: {int(restaurant.min_order or 0):,} so'm\n"
        f"\nMENYU (kategoriyalar bo'yicha, faqat shu mahsulotlar taklif qilinadi):\n{menu_text}"
    )
    return "\n".join(parts)


def _recover_failed_tool_calls(failed_generation: str) -> list[dict]:
    """Llama 4 va boshqa modellar ba'zan tool_call'larni xato formatda yuboradi:
      - Raqamlarni string sifatida ('product_id': '92')
      - 'parameters' field nomini ishlatadi (OpenAI 'arguments' kutadi)
      - 'arguments' o'rniga to'liq object yuboradi

    Bu funksiya failed_generation matnini parse qilib, to'g'ri formatda
    tool_calls ro'yxatini qaytaradi. Type coercion ham qo'shilgan.
    """
    import json as _json
    import re as _re
    if not failed_generation:
        return []

    # JSON'ni topib parse qilamiz (matnda boshqa narsalar bo'lishi mumkin)
    text = failed_generation.strip()
    # Markdown code blocks olib tashlash
    if text.startswith("```"):
        text = _re.sub(r"^```\w*\n?", "", text)
        text = _re.sub(r"\n?```$", "", text)
    try:
        parsed = _json.loads(text)
    except Exception:
        # Massiv emas, faqat bitta object bo'lishi mumkin
        try:
            # Birinchi { dan oxirgi } gacha yoki [ dan ]
            start = min((text.find(c) for c in "[{" if text.find(c) >= 0), default=-1)
            end_arr = text.rfind("]")
            end_obj = text.rfind("}")
            end = max(end_arr, end_obj)
            if start < 0 or end <= start:
                return []
            parsed = _json.loads(text[start:end+1])
        except Exception:
            return []

    items = parsed if isinstance(parsed, list) else [parsed]

    # Tools schema'sidan integer maydonlarini olamiz
    int_fields_per_tool: dict[str, set] = {}
    for t in TOOLS:
        fn = t.get("function", {})
        name = fn.get("name", "")
        props = (fn.get("parameters") or {}).get("properties") or {}
        int_fields_per_tool[name] = {
            k for k, v in props.items() if isinstance(v, dict) and v.get("type") == "integer"
        }

    recovered = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("function") or ""
        if not name:
            continue
        # arguments yoki parameters yoki to'g'ridan-to'g'ri object
        args = item.get("arguments")
        if args is None:
            args = item.get("parameters") or {}
        # arguments string bo'lsa — JSON parse
        if isinstance(args, str):
            try:
                args = _json.loads(args)
            except Exception:
                args = {}
        if not isinstance(args, dict):
            args = {}

        # Integer maydonlarini coerce qilish (string → int)
        for f in int_fields_per_tool.get(name, set()):
            if f in args and isinstance(args[f], str):
                try:
                    args[f] = int(args[f].strip())
                except Exception:
                    pass

        recovered.append({
            "id": f"recovered_{i}",
            "name": name,
            "arguments": args,
        })

    return recovered


TOOLS = [
    {"type": "function", "function": {
        "name": "add_to_cart", "description": "Savatga qo'shish.",
        "parameters": {"type": "object", "properties": {
            "product_id": {"type": "integer"}, "quantity": {"type": "integer", "minimum": 1}
        }, "required": ["product_id", "quantity"]},
    }},
    {"type": "function", "function": {
        "name": "remove_from_cart", "description": "Savatdan o'chirish.",
        "parameters": {"type": "object", "properties": {"product_id": {"type": "integer"}}, "required": ["product_id"]},
    }},
    {"type": "function", "function": {
        "name": "clear_cart", "description": "Savatni tozalash.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "view_cart", "description": "Savatni ko'rish.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "set_address", "description": "Yetkazish manzilini saqlash.",
        "parameters": {"type": "object", "properties": {"address": {"type": "string"}}, "required": ["address"]},
    }},
    {"type": "function", "function": {
        "name": "set_delivery_type",
        "description": "Yetkazib berish yoki olib ketish turini saqlash.",
        "parameters": {"type": "object", "properties": {
            "type": {"type": "string", "enum": ["delivery", "pickup"]}
        }, "required": ["type"]},
    }},
    {"type": "function", "function": {
        "name": "confirm_order",
        "description": "Buyurtmani tasdiqlash. Faqat barcha ma'lumotlar to'liq bo'lganda chaqiring.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "transfer_to_catering", "description": "Catering kanaliga uzatish.",
        "parameters": {"type": "object", "properties": {"reason": {"type": "string"}}},
    }},
    {"type": "function", "function": {
        "name": "start_new_order",
        "description": "Yangi buyurtma boshlash (oldingi buyurtma allaqachon qabul qilingan). Savatni tozalaydi.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "end_conversation",
        "description": "Suhbatni yakunlash. Faqat mijozga xayrlashgandan keyin chaqir — qo'ng'iroq tugaydi.",
        "parameters": {"type": "object", "properties": {}},
    }},
]


# ── Function dispatch ────────────────────────────────────────────────────

def _exec_tool(
    name: str,
    args: dict,
    sess: AIConversation,
    products_by_id: dict[int, Product],
    restaurant: Restaurant,
) -> dict:
    """Tool chaqiruvini bajarish va natijani LLM ga matn sifatida qaytarish."""
    if name == "add_to_cart":
        pid = int(args.get("product_id", 0))
        qty = max(1, int(args.get("quantity", 1)))
        prod = products_by_id.get(pid)
        if not prod:
            return {"error": f"Mahsulot #{pid} menyuda yo'q"}
        # mavjud item bo'lsa qo'shamiz
        for it in sess.cart:
            if it.product_id == pid:
                it.quantity += qty
                return {"ok": True, "cart": sess.cart_summary()}
        sess.cart.append(CartItem(
            product_id=pid, name=prod.name_uz, quantity=qty, price=float(prod.price),
            catering_group=prod.catering_group,
        ))
        return {"ok": True, "cart": sess.cart_summary()}

    if name == "remove_from_cart":
        pid = int(args.get("product_id", 0))
        sess.cart = [i for i in sess.cart if i.product_id != pid]
        return {"ok": True, "cart": sess.cart_summary()}

    if name == "clear_cart":
        sess.cart.clear()
        return {"ok": True}

    if name == "view_cart":
        return {"cart": sess.cart_summary(), "total_uzs": sess.cart_total()}

    if name == "set_address":
        sess.address = (args.get("address") or "").strip() or None
        # Manzil berilganda — yetkazib berish deb belgilaymiz (agar hali aniqlanmagan bo'lsa)
        if sess.address and not sess.delivery_type:
            sess.delivery_type = "delivery"
        return {"ok": True, "address": sess.address, "delivery_type": sess.delivery_type}

    if name == "set_delivery_type":
        dt = (args.get("type") or "").strip().lower()
        if dt not in ("delivery", "pickup"):
            return {"error": "type 'delivery' yoki 'pickup' bo'lishi kerak"}
        sess.delivery_type = dt
        if dt == "pickup":
            sess.address = None
        return {"ok": True, "delivery_type": dt}

    if name == "confirm_order":
        # Slot validatsiyasi — kerakli ma'lumotlar to'liqmi?
        missing = order_missing_slots(sess)
        if missing:
            return {
                "error": "missing_slots",
                "missing": missing,
                "instruction": (
                    f"Buyurtmani tasdiqlash uchun quyidagi ma'lumotlar yetishmayapti: "
                    f"{', '.join(missing)}. Mijozdan shularni so'rang."
                ),
            }
        sess.confirmed = True
        return {
            "ok": True, "summary": sess.cart_summary(),
            "address": sess.address, "delivery_type": sess.delivery_type,
        }

    if name == "transfer_to_catering":
        # Sessiyani belgilab qo'yamiz — tashqi handler order yaratmasdan transfer qiladi
        sess.confirmed = False
        return {"ok": True, "transferred": True, "reason": args.get("reason", "")}

    if name == "start_new_order":
        sess.cart.clear()
        sess.address = None
        sess.delivery_type = None
        sess.confirmed = False
        return {"ok": True, "message": "Yangi buyurtma boshlandi. Savat tozalandi."}

    if name == "end_conversation":
        sess.conversation_ended = True
        return {"ok": True, "ended": True, "message": "Suhbat yakunlandi."}

    return {"error": f"Noma'lum funksiya: {name}"}


# ── Slot validatsiyasi (buyurtma to'liqligini tekshirish) ───────────────

def order_missing_slots(sess: AIConversation) -> list[str]:
    """Buyurtma tasdiqlashga yetishmayotgan slotlar ro'yxati.

    Slotlar:
      - 'mahsulot' — savatda kamida 1 ta mahsulot
      - 'yetkazish_turi' — delivery yoki pickup tanlanishi kerak
      - 'manzil' — agar delivery bo'lsa, manzil
    """
    missing: list[str] = []
    if not sess.cart:
        missing.append("mahsulot (savat bo'sh)")
    if not sess.delivery_type:
        missing.append("yetkazish_turi (delivery yoki pickup)")
    elif sess.delivery_type == "delivery" and not sess.address:
        missing.append("manzil (yetkazib berish uchun)")
    return missing


# ── Catering aniqlash ────────────────────────────────────────────────────

def is_catering_cart(cart: list[CartItem], restaurant: Restaurant) -> bool:
    """Catering chegarasi oshganligini tekshirish (somsa_min, nan_min)."""
    somsa_q = sum(i.quantity for i in cart if i.catering_group == "somsa")
    nan_q   = sum(i.quantity for i in cart if i.catering_group == "nan")
    if somsa_q >= (restaurant.catering_somsa_min or 100):
        return True
    if nan_q >= (restaurant.catering_nan_min or 40):
        return True
    return False


# ── LLM provayder qatlami (multi-provider abstraktsiya) ─────────────────

from api.services.llm import get_provider, get_provider_by_name
from api.services.llm.registry import get_provider_api_key


def _platform_api_key() -> str:
    """Joriy provayder uchun API kalit (super-admin tomonidan kiritiladi)."""
    return get_provider_api_key()


def _platform_model() -> str:
    return (platform.get("ai_llm_model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _platform_provider_name() -> str:
    return (platform.get("ai_llm_provider") or "openai").strip().lower() or "openai"


def _is_mock_mode(restaurant: Restaurant) -> bool:
    """Joriy provayder uchun API kalit yo'q bo'lsa mock rejim."""
    return not _platform_api_key()


def _is_within_work_hours(restaurant: Restaurant) -> bool:
    """Restoran ish vaqti ichidami? (Asia/Tashkent vaqti bo'yicha)

    work_hours_from va work_hours_until "HH:MM" formatida saqlanadi.
    Kechki o'tish (masalan 22:00–02:00) ham qo'llab-quvvatlanadi.
    """
    try:
        from datetime import datetime
        try:
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo("Asia/Tashkent"))
        except Exception:
            now = datetime.now()
        wf = (restaurant.work_hours_from or "00:00").strip()
        wu = (restaurant.work_hours_until or "23:59").strip()
        fh, fm = [int(x) for x in wf.split(":")[:2]]
        uh, um = [int(x) for x in wu.split(":")[:2]]
        cur_minutes = now.hour * 60 + now.minute
        from_minutes = fh * 60 + fm
        until_minutes = uh * 60 + um
        if until_minutes >= from_minutes:
            return from_minutes <= cur_minutes <= until_minutes
        # Kechki o'tish (22:00 → 02:00)
        return cur_minutes >= from_minutes or cur_minutes <= until_minutes
    except Exception:
        # Xatolik bo'lsa — yopib qo'ymaymiz, ochiq deb hisoblaymiz
        return True


def _build_offline_reply(restaurant: Restaurant) -> str:
    """AI o'chirilgan vaqtda (ish vaqtidan tashqari) mijozga aytiladigan xabar."""
    cfg = get_ai_config(restaurant)
    custom = (cfg.get("offline_reply") or "").strip()
    if custom:
        return custom
    wf = restaurant.work_hours_from or "09:00"
    wu = restaurant.work_hours_until or "22:00"
    fallback = (getattr(restaurant, "ai_agent_fallback_phone", None) or "").strip()
    parts = [
        f"Kechirasiz, hozir restoran yopiq. Ish vaqti: {wf}–{wu}.",
        "Iltimos, ish vaqtida qayta qo'ng'iroq qiling.",
    ]
    if fallback:
        parts.append(f"Shoshilinch hollarda: {fallback}")
    return " ".join(parts)


def _build_time_limit_reply(restaurant: Restaurant) -> str:
    cfg = get_ai_config(restaurant)
    custom = (cfg.get("time_limit_reply") or "").strip()
    if custom:
        return custom
    fallback = (getattr(restaurant, "ai_agent_fallback_phone", None) or "").strip()
    base = "Kechirasiz, suhbat vaqti yakunlandi. Buyurtmangizni yana boshlash uchun qayta qo'ng'iroq qiling."
    if fallback:
        return f"{base} Yoki operator bilan bog'laning: {fallback}"
    return base


async def process_message(
    db: AsyncSession,
    restaurant: Restaurant,
    sess: AIConversation,
    user_text: str,
) -> dict:
    """Bitta foydalanuvchi reploki uchun AI javobini olish.

    Qaytaradi:
      {
        "reply": "...",          # mijozga ovoz qilib aytiladigan matn
        "tool_calls": [...],     # bajarilgan funksiyalar (debug uchun)
        "confirmed": bool,       # buyurtma tasdiqlandimi
        "transferred": bool,     # catering kanaliga yo'naltirilsinmi
        "cart": [...],           # joriy savat
        "address": "...",
        "is_catering": bool,
      }
    """
    # ── Ish vaqti tekshiruvi ─────────────────────────────────────────────
    if getattr(restaurant, "ai_agent_work_hours_only", False):
        if not _is_within_work_hours(restaurant):
            reply = _build_offline_reply(restaurant)
            sess.messages.append({"role": "assistant", "content": reply})
            return {
                "reply": reply, "tool_calls": [], "confirmed": False,
                "transferred": False, "cart": _cart_to_dicts(sess.cart),
                "address": sess.address, "is_catering": False,
                "ended_reason": "outside_work_hours",
            }

    # ── Max suhbat davomiyligi (xarajat nazorati) ────────────────────────
    max_min = int(getattr(restaurant, "ai_agent_max_call_minutes", None) or 10)
    if sess.elapsed_minutes() >= max_min:
        reply = _build_time_limit_reply(restaurant)
        sess.messages.append({"role": "assistant", "content": reply})
        return {
            "reply": reply, "tool_calls": [], "confirmed": False,
            "transferred": False, "cart": _cart_to_dicts(sess.cart),
            "address": sess.address, "is_catering": False,
            "ended_reason": "time_limit",
        }

    products = await load_menu(db, restaurant.id)
    products_by_id = {p.id: p for p in products}
    categories = await load_categories(db, restaurant.id)
    menu_text = menu_to_text(products, categories)
    categories_list = categories_to_text(categories)

    # Tizim xabarini har murojaatda yangilab qo'yamiz (menyu o'zgargan bo'lishi mumkin)
    sys_content = build_system_prompt(restaurant, menu_text, categories_list)

    # ── JORIY HOLAT — modelga to'lgan slotlarni ANIQ ko'rsatamiz ─────────────
    # History trim (MAX_HISTORY) tufayli model eski xabarlarni unutadi va allaqachon
    # aytilgan ma'lumotni qayta so'raydi. Bu blok har murojaatda to'lgan slotlarni
    # eslatib turadi → qayta so'ramaydi, faqat yetishmayotganini so'raydi.
    if sess.delivery_type == "delivery":
        _addr = sess.address or "KERAK — hali aytilmagan"
    elif sess.delivery_type == "pickup":
        _addr = "kerak emas (olib ketish)"
    else:
        _addr = sess.address or "—"
    _missing = order_missing_slots(sess)
    _missing_str = ", ".join(_missing) if _missing else "yo'q — tasdiqlashga tayyor"
    _phase = "buyurtma yig'ish"
    if sess.conversation_ended:
        _phase = "suhbat tugadi"
    elif sess.order_placed and not sess.cart:
        _phase = "POST-BUYURTMA — 'Yana biror narsa?' deb so'ra yoki xayrlash"
    elif sess.confirmed:
        _phase = "tasdiqlash jarayonida"
    sys_content += (
        "\n\nJORIY BUYURTMA HOLATI (bu ma'lumotlar ALLAQACHON ma'lum — mijozdan QAYTA "
        "SO'RAMA; faqat yetishmayotganini so'ra; tasdiqlashda esa qisqa qaytarib o'qib chiq):\n"
        f"- Suhbat bosqichi: {_phase}\n"
        f"- Salomlashish: {'bajarildi' if sess.greeted else 'kerak — qisqa salomlash'}\n"
        f"- Savat: {sess.cart_summary()}\n"
        f"- Yetkazish turi: {sess.delivery_type or 'tanlanmagan'}\n"
        f"- Manzil: {_addr}\n"
        f"- Yetishmayotgan: {_missing_str}"
    )
    if sess.order_placed and sess.last_order_id:
        sys_content += (
            f"\n- Oxirgi qabul qilingan buyurtma: #{sess.last_order_id} "
            "(mijoz allaqachon buyurtma bergan — qayta tasdiqlatma, faqat yangi buyurtma yoki xayrlash)"
        )

    if not sess.messages:
        sess.messages.append({"role": "system", "content": sys_content})
    else:
        sess.messages[0] = {"role": "system", "content": sys_content}

    sess.messages.append({"role": "user", "content": user_text})
    sess.user_turn_count += 1
    sess.add_transcript("user", user_text)

    # ── Mock rejim — API key yo'q bo'lsa minimal javob qaytaramiz ────────
    if _is_mock_mode(restaurant):
        reply = (
            "AI agent test rejimida. Mezbon platforma administratori AI kalitni "
            "sozlamasi kerak."
        )
        sess.messages.append({"role": "assistant", "content": reply})
        sess.add_transcript("assistant", reply)
        return {
            "reply": reply, "tool_calls": [], "confirmed": False,
            "transferred": False, "cart": [], "address": sess.address,
            "is_catering": False, "mock": True,
        }

    api_key = _platform_api_key()
    model = _platform_model()
    provider = get_provider()
    provider_label = provider.display_name

    transferred = False
    executed_tools: list[dict] = []

    # ── Conversation history trim — eski xabarlar token'larini tejash ───
    # system + oxirgi 6 ta xabar (user/assistant/tool) yetadi — buyurtma uchun
    # context'ning so'nggi bosqichlari muhim
    MAX_HISTORY = 7   # 1 system + 6 oxirgi
    if len(sess.messages) > MAX_HISTORY:
        # System xabarni saqlab, oxirgi (MAX_HISTORY-1) ta xabarni qoldiramiz
        system_msg = sess.messages[0] if sess.messages and sess.messages[0].get("role") == "system" else None
        kept = sess.messages[-(MAX_HISTORY - 1):]
        # tool/assistant juftliklari sinmasligi uchun — agar birinchi qolgan xabar 'tool' bo'lsa, uni o'tkazib yuboramiz
        while kept and kept[0].get("role") == "tool":
            kept = kept[1:]
        sess.messages = ([system_msg] if system_msg else []) + kept

    # ── Function-calling loop (max 5 iteratsiya) + retry on 429/tool_use_failed ──
    async def _chat_with_retry():
        """Avtomatik retry: 429 → server aytgan vaqtni kutib; tool_use_failed → qayta."""
        import asyncio as _asyncio
        import re as _re
        try:
            return await provider.chat(api_key, model, sess.messages, TOOLS)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                # 1) Retry-After header
                wait_s = 0.0
                try:
                    ra = e.response.headers.get("retry-after")
                    if ra:
                        wait_s = float(ra)
                except Exception:
                    pass
                # 2) Yoki xato matnidan "try again in X.YYs" olib kutamiz
                if wait_s <= 0:
                    try:
                        body = e.response.json()
                        msg = (body.get("error") or {}).get("message") or ""
                        m = _re.search(r"try again in ([\d.]+)\s*s", msg)
                        if m:
                            wait_s = float(m.group(1)) + 0.5  # +0.5 sek xavfsizlik
                    except Exception:
                        pass
                # 3) Default 3 sek
                if wait_s <= 0:
                    wait_s = 3.0
                # Max 15 sekund — undan ko'p kutmaymiz (foydalanuvchi kutib qoladi)
                wait_s = min(15.0, wait_s)
                await _asyncio.sleep(wait_s)
                return await provider.chat(api_key, model, sess.messages, TOOLS)
            # tool_use_failed → Llama'ning xato tool format chiqishi.
            # 1) Avval failed_generation'dan tool call'larni parse qilib, qaytarib ko'ramiz
            # 2) Bu ishlamasa — oddiy retry
            if e.response.status_code == 400:
                try:
                    body = e.response.json()
                    err = body.get("error") or {}
                    if err.get("code") == "tool_use_failed":
                        fg = err.get("failed_generation") or ""
                        recovered = _recover_failed_tool_calls(fg)
                        if recovered:
                            # AI to'g'ri tushindi, lekin format xato — biz qutqaramiz
                            from .llm.base import ChatResult
                            return ChatResult(
                                content="", tool_calls=recovered,
                                usage={"prompt_tokens": 0, "completion_tokens": 0},
                            )
                        # Recover bo'lmasa — retry
                        await _asyncio.sleep(0.5)
                        return await provider.chat(api_key, model, sess.messages, TOOLS)
                except Exception:
                    pass
            raise

    for _ in range(5):  # max 5 iteratsiya (cheksiz cycle himoyasi)
        try:
            result_chat = await _chat_with_retry()
        except httpx.HTTPStatusError as e:
            # Provayder batafsil xato xabarini ajratib olamiz
            err_code = None
            err_msg = ""
            failed_gen = ""
            try:
                body = e.response.json()
                # OpenAI/Groq formati
                if isinstance(body, dict) and "error" in body and isinstance(body["error"], dict):
                    err_code = body["error"].get("code") or body["error"].get("type")
                    err_msg = body["error"].get("message") or ""
                    # Groq tool_use_failed uchun batafsil generation
                    fg = body["error"].get("failed_generation")
                    if fg:
                        failed_gen = str(fg)[:600]
                # Anthropic formati
                elif isinstance(body, dict) and body.get("type") == "error":
                    err_code = (body.get("error") or {}).get("type")
                    err_msg = (body.get("error") or {}).get("message") or ""
            except Exception:
                err_msg = e.response.text[:200]
            from api.logging_config import log_critical
            log_critical(
                "ai_agent", "LLM provider request failed",
                provider=provider.name,
                http_code=e.response.status_code, error_code=err_code, error_message=err_msg,
                failed_generation=failed_gen,
                restaurant_id=restaurant.id, call_id=sess.call_id, model=model,
            )
            # Foydalanuvchiga tushunarli xabar
            err_msg_l = (err_msg or "").lower()
            err_code_s = str(err_code or "")

            if err_code in {"insufficient_quota", "billing_not_active"}:
                friendly = f"{provider_label} hisobida kredit yo'q. Super-admin balansni to'ldirishi yoki bepul provayderga (Groq) o'tishi kerak."
            elif e.response.status_code == 429 and "free_tier" in err_msg_l and "limit: 0" in err_msg_l:
                # Gemini-spesifik: free tier mavjud emas (mintaqa cheklov)
                friendly = (
                    f"{provider_label} sizning hisobingiz uchun bepul tier'ni bermagan "
                    "(mintaqa cheklov yoki yangi loyiha bo'lishi mumkin). "
                    "Groq (Llama) provayderiga o'ting — u O'zbekistonda bepul ishlaydi."
                )
            elif e.response.status_code == 429:
                friendly = f"Hozir {provider_label}'ga juda ko'p so'rov. Bir necha soniyadan keyin qayta urinib ko'ring."
            elif err_code in {"rate_limit_exceeded", "rate_limit_error"}:
                friendly = f"Hozir {provider_label}'ga juda ko'p so'rov. Bir necha soniyadan keyin qayta urinib ko'ring."
            elif err_code in {"invalid_api_key", "authentication_error"} or e.response.status_code == 401:
                friendly = f"{provider_label} kaliti noto'g'ri yoki mos kelmaydi (boshqa provayderning kaliti bo'lishi mumkin). Super-admin sozlamalarda kalitni qayta tekshiring."
            elif err_code == "tool_use_failed":
                friendly = (
                    "AI buyurtmangizni tushuna olmadi. Iltimos, aniqroq aytib bering. "
                    "Masalan: 'Bitta go'shli somsa olaman' yoki 'Manzilim Chilonzor 5-mavze, 12-uy'."
                )
            else:
                code_label = err_code_s or "noma'lum"
                friendly = f"{provider_label} xato: {e.response.status_code} ({code_label})"
            sess.messages.append({"role": "assistant", "content": friendly})
            return {
                "reply": friendly, "tool_calls": executed_tools, "confirmed": False,
                "transferred": False, "cart": _cart_to_dicts(sess.cart),
                "address": sess.address, "is_catering": False, "error": err_msg or friendly,
            }
        except Exception as e:
            from api.logging_config import log_critical
            log_critical(
                "ai_agent", "AI service unavailable",
                provider=provider.name, error=str(e),
                restaurant_id=restaurant.id, call_id=sess.call_id,
            )
            err = f"AI xizmati ishlamayapti: {e}"
            sess.messages.append({"role": "assistant", "content": err})
            return {
                "reply": err, "tool_calls": executed_tools, "confirmed": False,
                "transferred": False, "cart": _cart_to_dicts(sess.cart),
                "address": sess.address, "is_catering": False, "error": err,
            }

        # Token usage tracking
        sess.tokens_in += int(result_chat.usage.get("prompt_tokens") or 0)
        sess.tokens_out += int(result_chat.usage.get("completion_tokens") or 0)
        if result_chat.rate_limit:
            sess.last_rate_limit = result_chat.rate_limit

        # LLM xabarini history ga qo'shish (OpenAI shaklida — provayderlar normalizatsiya qiladi)
        # MUHIM: Groq null tool_calls'ni qabul qilmaydi, shuning uchun tool_calls yo'q bo'lsa
        # field'ni butunlay qo'shmaymiz.
        assistant_msg: dict = {
            "role": "assistant",
            "content": result_chat.content or "",
        }
        if result_chat.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc.get("arguments") or {}, ensure_ascii=False),
                    },
                }
                for tc in result_chat.tool_calls
            ]
        sess.messages.append(assistant_msg)

        if not result_chat.tool_calls:
            reply = (result_chat.content or "").strip()
            if reply:
                sess.add_transcript("assistant", reply)
            if not sess.greeted and reply:
                sess.greeted = True
            out = {
                "reply": reply,
                "tool_calls": executed_tools,
                "confirmed": sess.confirmed,
                "transferred": transferred,
                "cart": _cart_to_dicts(sess.cart),
                "address": sess.address,
                "is_catering": is_catering_cart(sess.cart, restaurant),
            }
            if sess.conversation_ended:
                out["ended_reason"] = "conversation_complete"
            return out

        # Tool chaqiruvlarni ketma-ket bajaramiz
        for tc in result_chat.tool_calls:
            name = tc.get("name", "")
            args = tc.get("arguments") or {}
            tool_result = _exec_tool(name, args, sess, products_by_id, restaurant)
            executed_tools.append({"name": name, "args": args, "result": tool_result})
            if name == "transfer_to_catering":
                transferred = True
            sess.messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id"),
                "name": name,
                "content": json.dumps(tool_result, ensure_ascii=False),
            })

        # Suhbat yakunlandi — xayrlash bilan qo'ng'iroq tugaydi
        if sess.conversation_ended:
            reply = (result_chat.content or "Rahmat! Xayr, sog' bo'ling!").strip()
            if reply:
                sess.add_transcript("assistant", reply)
            sess.greeted = True
            return {
                "reply": reply,
                "tool_calls": executed_tools,
                "confirmed": False,
                "transferred": False,
                "cart": _cart_to_dicts(sess.cart),
                "address": sess.address,
                "is_catering": False,
                "ended_reason": "conversation_complete",
            }

        # confirm yoki transfer bo'lsa loop'dan chiqamiz — yakuniy javobni LLM dan olish uchun
        if sess.confirmed or transferred:
            try:
                final_chat = await _chat_with_retry()
                sess.tokens_in += int(final_chat.usage.get("prompt_tokens") or 0)
                sess.tokens_out += int(final_chat.usage.get("completion_tokens") or 0)
                if final_chat.rate_limit:
                    sess.last_rate_limit = final_chat.rate_limit
                final = final_chat.content or ""
                sess.messages.append({"role": "assistant", "content": final})
            except Exception:
                if sess.confirmed:
                    final = (
                        "Buyurtmangiz qabul qilindi. Yana biror narsa buyurtma qilasizmi "
                        "yoki boshqa savolingiz bormi?"
                    )
                else:
                    final = "Sizga qo'ng'iroq qilamiz."
            final = final.strip()
            if final:
                sess.add_transcript("assistant", final)
            sess.greeted = True
            return {
                "reply": final,
                "tool_calls": executed_tools,
                "confirmed": sess.confirmed,
                "transferred": transferred,
                "cart": _cart_to_dicts(sess.cart),
                "address": sess.address,
                "is_catering": is_catering_cart(sess.cart, restaurant),
            }

    # 5 iteratsiyada to'xtamasa — fallback
    return {
        "reply": "Kechirasiz, qayta urinib ko'ring.",
        "tool_calls": executed_tools, "confirmed": False, "transferred": False,
        "cart": _cart_to_dicts(sess.cart), "address": sess.address,
        "is_catering": is_catering_cart(sess.cart, restaurant),
    }


def _cart_to_dicts(cart: list[CartItem]) -> list[dict]:
    return [
        {
            "product_id": i.product_id, "name": i.name,
            "quantity": i.quantity, "price": i.price,
            "catering_group": i.catering_group,
        }
        for i in cart
    ]
