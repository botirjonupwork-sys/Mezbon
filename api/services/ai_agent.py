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
    confirmed: bool = False
    last_active: float = field(default_factory=time.time)

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


def menu_to_text(products: list[Product]) -> str:
    """AI uchun menyu — faqat ID, nom va narx."""
    if not products:
        return "(Menyu bo'sh)"
    lines = []
    for p in products:
        ctype = " [catering]" if (p.product_type or "regular") == "catering" else ""
        lines.append(f"#{p.id} — {p.name_uz} — {int(p.price):,} so'm{ctype}")
    return "\n".join(lines)


# ── System prompt va tool schemas ────────────────────────────────────────

DEFAULT_SYSTEM = (
    "Sen O'zbekistondagi 'Muhsina Dollar Somsa' restoranining ovozli AI operatorisan. "
    "Mijoz bilan o'zbek tilida (jonli, qisqa va xushmuomala) gaplashasan. "
    "Vazifang: telefon orqali kelgan mijozdan buyurtma qabul qilish.\n\n"
    "Qoidalar:\n"
    "1) Faqat menyuda mavjud mahsulotlarni taklif qiling. ID va narxlarni menyudan oling.\n"
    "2) Mahsulot va miqdorni mijoz aytganda 'add_to_cart' funksiyasini chaqiring.\n"
    "3) Mijoz fikrini o'zgartirsa 'remove_from_cart' yoki 'clear_cart' chaqiring.\n"
    "4) Manzilni so'rang va 'set_address' chaqiring (yetkazib berish bo'lsa).\n"
    "5) Buyurtmani tasdiqlashdan oldin 'view_cart' bilan tekshirib, mijozga ovoz "
    "chiqarib aytib bering: nimalar, miqdor, jami summa.\n"
    "6) Faqat mijoz aniq 'ha, tasdiqlayman' degandagina 'confirm_order' chaqiring.\n"
    "7) Agar mijoz 100 dan ortiq somsa yoki ko'p miqdorda kichik mahsulot so'rasa — "
    "bu CATERING (tadbir uchun) buyurtmasi. Mijozga ayting: 'tadbir uchun katta "
    "buyurtmalar alohida menejer orqali qabul qilinadi, sizga qo'ng'iroq qilamiz' "
    "va 'transfer_to_catering' chaqiring.\n"
    "8) Hech qachon o'zingizdan narx, mahsulot yoki ID o'ylab topmang.\n"
    "9) Javoblar qisqa — ovoz uchun mo'ljallangan, 1-2 jumla."
)


def build_system_prompt(restaurant: Restaurant, menu_text: str) -> str:
    custom = (restaurant.ai_agent_prompt or "").strip()
    parts = [DEFAULT_SYSTEM]
    if custom:
        parts.append(f"\nRestoran ko'rsatmasi:\n{custom}")
    parts.append(
        f"\nRESTORAN: {restaurant.name}\n"
        f"ISH VAQTI: {restaurant.work_hours_from}–{restaurant.work_hours_until}\n"
        f"MIN. BUYURTMA: {int(restaurant.min_order or 0):,} so'm\n"
        f"\nJORIY MENYU (faqat shu mahsulotlarni taklif qiling):\n{menu_text}"
    )
    return "\n".join(parts)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_to_cart",
            "description": "Mahsulotni mijoz savatiga qo'shadi.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "Menyudagi mahsulot ID"},
                    "quantity": {"type": "integer", "minimum": 1},
                },
                "required": ["product_id", "quantity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_from_cart",
            "description": "Mahsulotni savatdan olib tashlash.",
            "parameters": {
                "type": "object",
                "properties": {"product_id": {"type": "integer"}},
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clear_cart",
            "description": "Savatni butunlay tozalash.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "view_cart",
            "description": "Joriy savat tarkibini va jami summani qaytaradi.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_address",
            "description": "Yetkazib berish manzilini saqlash.",
            "parameters": {
                "type": "object",
                "properties": {"address": {"type": "string"}},
                "required": ["address"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_order",
            "description": "Buyurtmani tasdiqlash. Faqat mijoz ochiq tasdiqlasa chaqiring.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "transfer_to_catering",
            "description": "Katta (catering) buyurtmani alohida kanalga yo'naltirish.",
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
            },
        },
    },
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
        return {"ok": True, "address": sess.address}

    if name == "confirm_order":
        if not sess.cart:
            return {"error": "Savat bo'sh"}
        sess.confirmed = True
        return {"ok": True, "summary": sess.cart_summary(), "address": sess.address}

    if name == "transfer_to_catering":
        # Sessiyani belgilab qo'yamiz — tashqi handler order yaratmasdan transfer qiladi
        sess.confirmed = False
        return {"ok": True, "transferred": True, "reason": args.get("reason", "")}

    return {"error": f"Noma'lum funksiya: {name}"}


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


# ── OpenAI chat call ─────────────────────────────────────────────────────

async def _openai_chat(
    api_key: str, model: str, messages: list[dict], tools: list[dict]
) -> dict:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": 0.4,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(OPENAI_URL, json=payload, headers=headers)
        r.raise_for_status()
        return r.json()


def _is_mock_mode(restaurant: Restaurant) -> bool:
    """API key topilmasa mock mode (test).  AI hech narsa qaytarmaydi, statik javob."""
    api_key = restaurant.ai_agent_api_key or os.getenv("OPENAI_API_KEY", "")
    return not api_key.strip()


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
    products = await load_menu(db, restaurant.id)
    products_by_id = {p.id: p for p in products}
    menu_text = menu_to_text(products)

    # Tizim xabarini har murojaatda yangilab qo'yamiz (menyu o'zgargan bo'lishi mumkin)
    if not sess.messages:
        sess.messages.append({"role": "system", "content": build_system_prompt(restaurant, menu_text)})
    else:
        sess.messages[0] = {"role": "system", "content": build_system_prompt(restaurant, menu_text)}

    sess.messages.append({"role": "user", "content": user_text})

    # ── Mock rejim — API key yo'q bo'lsa minimal javob qaytaramiz ────────
    if _is_mock_mode(restaurant):
        reply = (
            "AI agent test rejimida. Iltimos, OpenAI kalitini Sozlamalar > "
            "AI Operator bo'limida kiriting."
        )
        sess.messages.append({"role": "assistant", "content": reply})
        return {
            "reply": reply, "tool_calls": [], "confirmed": False,
            "transferred": False, "cart": [], "address": sess.address,
            "is_catering": False, "mock": True,
        }

    api_key = restaurant.ai_agent_api_key or os.getenv("OPENAI_API_KEY", "")
    model = restaurant.ai_agent_model or DEFAULT_MODEL

    transferred = False
    executed_tools: list[dict] = []

    # Function-calling loop — tool chaqirilsa natija qo'shib, qayta chaqiramiz
    for _ in range(5):  # max 5 iteratsiya (cheksiz cycle himoyasi)
        try:
            data = await _openai_chat(api_key, model, sess.messages, TOOLS)
        except httpx.HTTPStatusError as e:
            from api.logging_config import log_critical
            log_critical(
                "ai_agent", "OpenAI request failed",
                http_code=e.response.status_code, restaurant_id=restaurant.id,
                call_id=sess.call_id, model=model,
            )
            err = f"OpenAI xato: {e.response.status_code}"
            sess.messages.append({"role": "assistant", "content": err})
            return {
                "reply": err, "tool_calls": executed_tools, "confirmed": False,
                "transferred": False, "cart": _cart_to_dicts(sess.cart),
                "address": sess.address, "is_catering": False, "error": err,
            }
        except Exception as e:
            from api.logging_config import log_critical
            log_critical(
                "ai_agent", "AI service unavailable",
                error=str(e), restaurant_id=restaurant.id, call_id=sess.call_id,
            )
            err = f"AI xizmati ishlamayapti: {e}"
            sess.messages.append({"role": "assistant", "content": err})
            return {
                "reply": err, "tool_calls": executed_tools, "confirmed": False,
                "transferred": False, "cart": _cart_to_dicts(sess.cart),
                "address": sess.address, "is_catering": False, "error": err,
            }

        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message", {})
        tool_calls = msg.get("tool_calls") or []

        # LLM xabarini history ga qo'shish
        sess.messages.append({
            "role": "assistant",
            "content": msg.get("content") or "",
            "tool_calls": tool_calls or None,
        })

        if not tool_calls:
            return {
                "reply": (msg.get("content") or "").strip(),
                "tool_calls": executed_tools,
                "confirmed": sess.confirmed,
                "transferred": transferred,
                "cart": _cart_to_dicts(sess.cart),
                "address": sess.address,
                "is_catering": is_catering_cart(sess.cart, restaurant),
            }

        # Tool chaqiruvlarni ketma-ket bajaramiz
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            result = _exec_tool(name, args, sess, products_by_id, restaurant)
            executed_tools.append({"name": name, "args": args, "result": result})
            if name == "transfer_to_catering":
                transferred = True
            sess.messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id"),
                "content": json.dumps(result, ensure_ascii=False),
            })

        # confirm yoki transfer bo'lsa loop'dan chiqamiz — yakuniy javobni LLM dan olish uchun
        if sess.confirmed or transferred:
            # Yakuniy assistant javobini olish uchun yana bir marta chaqiramiz
            try:
                data = await _openai_chat(api_key, model, sess.messages, TOOLS)
                final = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
                sess.messages.append({"role": "assistant", "content": final})
            except Exception:
                final = "Buyurtma tasdiqlandi." if sess.confirmed else "Sizga qo'ng'iroq qilamiz."
            return {
                "reply": final.strip(),
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
