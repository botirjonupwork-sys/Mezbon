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
    greeting_default = (
        f"Assalomu alaykum! '{restaurant.name}' AI operatori. "
        "Menyumiz bilan tanishasizmi yoki to'g'ridan-to'g'ri buyurtma berasizmi?"
    )
    custom_greeting = (getattr(restaurant, "ai_agent_greeting", None) or "").strip()
    greeting = custom_greeting or greeting_default

    category_hint = (
        f"Bizdagi kategoriyalar: {categories_list}." if categories_list else ""
    )

    base = (
        f"Sen '{restaurant.name}' restoranining do'stona SOTUV operatorisan. "
        f"{_language_instruction(restaurant)} "
        "Javoblar qisqa (1-2 jumla), tabiiy, xushmuomala va jonli. "
        "Maqsading: mijozga yordam berib, YUMSHOQ tavsiyalar bilan to'g'ri "
        "buyurtma yig'ish (bosim qilmasdan).\n\n"

        "SOTUV USLUBI (yumshoq — hech qachon majburlama):\n"
        "- Mijoz ikkilansa yoki 'nima bor?' desa — eng mashhur 1-2 taomni tavsiya qil.\n"
        "- Buyurtma yig'ilgach, bir marta tabiiy qo'shimcha taklif qil "
        "(masalan: 'Yoniga ichimlik ham qo'shaymi?'). Mijoz 'yo'q' desa — qaytarma, hurmat qil.\n"
        "- Taklif faqat MENYUDAGI mahsulotlardan bo'lsin.\n"
        "- Maqtov ortiqcha bo'lmasin — tabiiy va samimiy gapir.\n\n"

        "SUHBAT OQIMI (har bosqichni o'tkazib yubormaslik kerak):\n"
        f"1. SALOMLASHISH (faqat suhbat boshida, agar hali aytmagan bo'lsang): "
        f"\"{greeting}\"\n"
        "2. AGAR MIJOZ MENYU SO'RASA: Kategoriyalarni ro'yxat qil va so'ra: "
        f"'{category_hint} Qaysi turidan boshlaymiz?'\n"
        "3. AGAR MIJOZ KATEGORIYA TANLASA: Shu kategoriyadagi mahsulotlarni "
        "narx bilan sanab ber. Yana yangi mahsulot taklif qilma.\n"
        "4. AGAR MIJOZ TO'G'RIDAN-TO'G'RI BUYURTMA BERSA: mahsulot va miqdorni "
        "add_to_cart bilan saqla. Mijoz bir vaqtda bir nechta narsa aytsa "
        "(masalan: '3 ta somsa va manzilim Chilonzor 5'), hammasini bir bora qabul qil "
        "— bir necha tool chaqir va qayta so'rama.\n"
        "5. SAVAT BO'SH EMAS BO'LGACH (agar yetkazish_turi hali tanlanmagan bo'lsa): "
        "so'ra: 'Yetkazib beraylikmi yoki o'zingiz olib ketasizmi?' "
        "→ Javobiga ko'ra set_delivery_type chaqir.\n"
        "6. AGAR DELIVERY TANLANSA va MANZIL HALI YO'Q BO'LSA: TO'LIQ manzilni so'ra "
        "— tuman/ko'cha, uy/kvartira va MO'LJAL (yaqin belgili joy), chunki ovoz orqali "
        "manzil noaniq bo'ladi. Manzilni eshitgach, MIJOZGA QAYTA AYT va tasdiqlat "
        "('Manzilingiz: ... — to'g'rimi?') → keyin set_address.\n"
        "7. BARCHA MA'LUMOT TO'LGANIDA (savat + yetkazish_turi + delivery'da manzil): "
        "view_cart bilan tekshir va mijozga jamlamani ayt: mahsulotlar, JAMI SUMMA, "
        "yetkazish turi, manzil. So'ra: 'Tasdiqlaysizmi?'\n"
        "8. AGAR MIJOZ 'HA, TASDIQLAYMAN' DESA: confirm_order chaqir.\n\n"

        "NAMUNA SUHBAT (uslub uchun):\n"
        "Mijoz: 'Salom, nima bor?'\n"
        "Sen: 'Assalomu alaykum! Eng mashhuri — go'shtli somsa. Nechta olamiz?'\n"
        "Mijoz: '3 ta'\n"
        "Sen: (add_to_cart) 'Bo'ldi, 3 ta go'shtli somsa. Yoniga ayron qo'shaymi?'\n"
        "Mijoz: 'Yo'q, rahmat'\n"
        "Sen: 'Mayli. Yetkazib beraylikmi yoki o'zingiz olib ketasizmi?'\n\n"

        "MUHIM QOIDALAR:\n"
        "- Mijoz allaqachon aytib bergan ma'lumotni QAYTA SO'RAMA. "
        "Masalan 'manzilim Yunusobod 5-uy, 4 ta somsa kerak' desa — manzil va "
        "miqdorni bir bora qabul qil.\n"
        "- Faqat menyudagi mahsulotlarni taklif qil (narx/ID menyudan).\n"
        "- Menyuda yo'q narsani taklif qilma. Mijoz so'rasa: 'Kechirasiz, bizda yo'q'.\n"
        "- confirm_order chaqirishdan oldin barcha slot to'la bo'lsin. "
        "Server validatsiyasi xato qaytarsa, yetishmayotgan ma'lumotni so'ra.\n"
        "- Tadbir uchun katta miqdor (100+ somsa, 40+ non) — transfer_to_catering.\n"
        "\n"
        "STT XATOLARINI TANISH (ovoz orqali kelgan matn aniq bo'lmaydi):\n"
        "- 'savoy', 'saboy', 'savoyni', 'soyim', 'o'zim', 'ozim', 'olaman', "
        "'olib ketaman', 'olib ketish', 'kelaman olib', 'pikap' → PICKUP "
        "(set_delivery_type('pickup')).\n"
        "- 'yetkazib', 'yetkazing', 'olib keling', 'manzilga', 'uyga bering', "
        "'eshikkacha', 'dostavka', 'dostavkasi' → DELIVERY "
        "(set_delivery_type('delivery')).\n"
        "- Raqamlar: 'тут' → 'to'rt' (4); 'бир-икки' → 'bir-ikki' (1-2, aniqlashtir); "
        "'ани' → 'ana o'sha' (oldingi nomga).\n"
        "- Agar mijoz 'yo'q, ...' deb gap boshlasa — bu rad etish/tuzatish. "
        "Oldingi qadamni qayta ko'rib chiq.\n"
        "- Ovoz juda noaniq bo'lsa — taxmin qilma, aniq so'ra."
    )

    parts = [base]

    custom = (restaurant.ai_agent_prompt or "").strip()
    if custom:
        parts.append(f"\nRestoran maxsus ko'rsatmasi:\n{custom}")

    fallback_phone = (getattr(restaurant, "ai_agent_fallback_phone", None) or "").strip()
    if fallback_phone:
        parts.append(
            f"\nAgar mijozning so'rovini tushuna olmasang yoki murakkab vaziyat bo'lsa, "
            f"unga ayting: 'Operator bilan bog'lanish uchun {fallback_phone} raqamiga qo'ng'iroq qiling.'"
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
            return {
                "reply": reply,
                "tool_calls": executed_tools,
                "confirmed": sess.confirmed,
                "transferred": transferred,
                "cart": _cart_to_dicts(sess.cart),
                "address": sess.address,
                "is_catering": is_catering_cart(sess.cart, restaurant),
            }

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

        # confirm yoki transfer bo'lsa loop'dan chiqamiz — yakuniy javobni LLM dan olish uchun
        if sess.confirmed or transferred:
            try:
                final_chat = await _chat_with_retry()
                sess.tokens_in += int(final_chat.usage.get("prompt_tokens") or 0)
                sess.tokens_out += int(final_chat.usage.get("completion_tokens") or 0)
                final = final_chat.content or ""
                sess.messages.append({"role": "assistant", "content": final})
            except Exception:
                final = "Buyurtma tasdiqlandi." if sess.confirmed else "Sizga qo'ng'iroq qilamiz."
            final = final.strip()
            if final:
                sess.add_transcript("assistant", final)
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
