import json
import os
import math
import httpx
from datetime import datetime
from zoneinfo import ZoneInfo

UZ_TZ = ZoneInfo("Asia/Tashkent")
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from bot.states import OrderFlow
from bot.api_client import get_user, create_order, get_addresses, get_branch
from bot.handlers.cart import get_cart, save_cart
from bot.handlers.notifications import notify_admin
from bot.keyboards.order import (
    delivery_type_kb, payment_kb, confirm_kb,
    location_request_kb, saved_addresses_kb
)
from bot.keyboards.main import main_menu_kb

router = Router()


def _load_settings() -> dict:
    """settings.json dan sozlamalarni bevosita fayldan o'qiydi."""
    path = os.path.join(os.getcwd(), "settings.json")
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _load_work_hours() -> tuple:
    s = _load_settings()
    return s.get("work_hours_from", "09:00"), s.get("work_hours_until", "22:00")


def _is_open() -> bool:
    """Hozirgi vaqt ish vaqtida ekanligini tekshiradi."""
    try:
        work_from, work_until = _load_work_hours()
        now = datetime.now(UZ_TZ).strftime("%H:%M")
        return work_from <= now <= work_until
    except Exception:
        return True


async def _reverse_geocode(lat: float, lon: float) -> str:
    """Koordinatalardan odam o'qiy oladigan manzil olish (Nominatim)."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={"lat": lat, "lon": lon, "format": "json", "accept-language": "uz,ru"},
                headers={"User-Agent": "MuhsinaDollarSomsaBot/1.0"},
                timeout=5.0,
            )
            if r.status_code == 200:
                data = r.json()
                addr = data.get("address", {})
                parts = []
                for key in ("road", "suburb", "city_district", "city", "town", "village"):
                    val = addr.get(key)
                    if val and val not in parts:
                        parts.append(val)
                if parts:
                    return ", ".join(parts)
                return data.get("display_name", f"{lat:.5f}, {lon:.5f}")
    except Exception:
        pass
    return f"{lat:.5f}, {lon:.5f}"


def _haversine(lat1, lon1, lat2, lon2) -> float:
    """Ikki nuqta orasidagi masofani km da hisoblash."""
    R = 6371  # Yer radiusi km da
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _calc_delivery_fee(lat: float, lon: float, branch_info: dict = None) -> float:
    """Masofaga qarab dastavka narxini hisoblash."""
    if branch_info:
        rest_lat = branch_info.get("latitude", 41.2995)
        rest_lon = branch_info.get("longitude", 69.2401)
        base_fee = branch_info.get("delivery_base_fee", 10000)
        per_km = branch_info.get("delivery_per_km", 3000)
    else:
        s = _load_settings()
        rest_lat = s.get("restaurant_lat", 41.2995)
        rest_lon = s.get("restaurant_lon", 69.2401)
        base_fee = s.get("delivery_base_fee", 10000)
        per_km = s.get("delivery_per_km", 3000)

    distance = _haversine(rest_lat, rest_lon, lat, lon)
    return round(base_fee + distance * per_km, -2)  # 100 ga yaxlitlash


STATUS_TEXT = {
    "pending":    "⏳ Kutilmoqda",
    "confirmed":  "✅ Qabul qilindi",
    "preparing":  "👨‍🍳 Tayyorlanmoqda",
    "ready":      "📦 Tayyor",
    "delivering": "🚗 Yo'lda",
    "delivered":  "✅ Yetkazildi",
    "cancelled":  "❌ Bekor qilindi",
}


async def _ask_comment(message: Message, state: FSMContext):
    await message.answer(
        "💬 Izoh qoldirmoqchimisiz? (ixtiyoriy)\n"
        "Masalan: 'Qo'ng'iroq qilmang', '3-qavat'\n\n"
        "Yo'q bo'lsa /skip yozing",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(OrderFlow.entering_comment)


@router.callback_query(F.data == "checkout")
async def checkout_start(callback: CallbackQuery, state: FSMContext):
    cart = await get_cart(state)
    if not cart:
        await callback.answer("Savat bo'sh!", show_alert=True)
        return

    data = await state.get_data()
    branch_id = data.get("branch_id")

    if not branch_id:
        await callback.answer("📍 Avval filial tanlang!", show_alert=True)
        return

    # Filial ochiqligini tekshirish
    branch_info = await get_branch(branch_id)
    if branch_info and not branch_info.get("is_open"):
        await callback.answer(
            f"⏰ {branch_info.get('name', 'Filial')} hozir yopiq!\n"
            f"Ish vaqti: {branch_info.get('work_hours_from', '09:00')} – {branch_info.get('work_hours_until', '22:00')}",
            show_alert=True,
        )
        return

    await state.update_data(cart_total=sum(v["price"] * v["quantity"] for v in cart.values()))

    user = await get_user(str(callback.from_user.id))
    if not user:
        await callback.message.answer(
            "📝 Zakaz berish uchun avval ro'yxatdan o'ting!\n"
            "Ismingizni kiriting:"
        )
        from bot.states import Registration
        await state.set_state(Registration.full_name)
        return

    await state.update_data(
        user_name=user.get("full_name", "—"),
        user_phone=user.get("phone", "—"),
    )
    await callback.message.answer(
        "🚚 Yetkazib berish turini tanlang:",
        reply_markup=delivery_type_kb(),
    )
    await state.set_state(OrderFlow.choosing_delivery)
    await callback.answer()


@router.callback_query(OrderFlow.choosing_delivery, F.data.in_(["delivery", "pickup"]))
async def choose_delivery(callback: CallbackQuery, state: FSMContext):
    delivery_type = callback.data

    # Dastavka uchun minimal zakaz tekshiruvi
    if delivery_type == "delivery":
        data = await state.get_data()
        cart = data.get("cart", {})
        total = sum(v["price"] * v["quantity"] for v in cart.values())
        # Filial sozlamalaridan min_order olish
        branch_id = data.get("branch_id")
        branch_info = await get_branch(branch_id) if branch_id else None
        min_order = branch_info.get("min_order", 30000) if branch_info else _load_settings().get("min_order", 30000)
        if total < min_order:
            await callback.answer(
                f"\U0001f69a Dastavka uchun minimal zakaz: {min_order:,.0f} so'm\n"
                f"Hozirgi summa: {total:,.0f} so'm\n\n"
                f"\U0001f3ea Saboy olib ketish limitsiz!",
                show_alert=True,
            )
            return

    await state.update_data(delivery_type=delivery_type)

    if delivery_type == "pickup":
        await state.update_data(address="Saboy olib ketish")
        await callback.message.answer(
            "🏪 Bizning manzil:\n<b>Toshkent sh.</b>\n\n"
            "💬 Izoh qoldirmoqchimisiz? (ixtiyoriy)\n"
            "Yo'q bo'lsa /skip yozing",
            parse_mode="HTML",
        )
        await state.set_state(OrderFlow.entering_comment)
    else:
        # Dastavka — manzil MAJBURIY
        try:
            addresses = await get_addresses(str(callback.from_user.id))
        except Exception:
            addresses = []

        if addresses:
            await callback.message.answer(
                "📍 <b>Saqlangan manzillardan birini tanlang:</b>",
                reply_markup=saved_addresses_kb(addresses),
                parse_mode="HTML",
            )

        await state.set_state(OrderFlow.entering_address)
        await callback.message.answer(
            "📍 <b>Yetkazib berish manzili</b>\n\n"
            "Joylashuvni yuborish uchun:\n"
            "▪️ <b>📍 Tugmani bosing</b> — joriy joylashuvingiz yuboriladi\n"
            "▪️ Yoki <b>📎 (skrepka) → Joylashuv</b> → xaritadan istalgan nuqtani tanlang\n\n"
            "<i>Manzilni matn ko'rinishida ham yozishingiz mumkin</i>",
            reply_markup=location_request_kb(),
            parse_mode="HTML",
        )

    await callback.answer()


# ── Saqlangan manzilni tanlash ────────────────────────
@router.callback_query(OrderFlow.entering_address, F.data.startswith("addr:"))
async def select_saved_address(callback: CallbackQuery, state: FSMContext):
    address = callback.data.split(":", 1)[1]
    await state.update_data(address=address)
    await callback.answer("✅ Manzil tanlandi")
    await _ask_comment(callback.message, state)


# ── Telegram GPS yoki xaritadan joylashuv ─────────────
@router.message(OrderFlow.entering_address, F.location)
async def enter_location(message: Message, state: FSMContext):
    lat = message.location.latitude
    lon = message.location.longitude

    await message.answer("🔍 Manzil aniqlanmoqda...")

    addr_name = await _reverse_geocode(lat, lon)
    await state.update_data(address=addr_name, latitude=lat, longitude=lon)

    await message.answer(
        f"✅ Manzil aniqlandi!\n📍 {addr_name}",
        reply_markup=ReplyKeyboardRemove(),
    )
    await _ask_comment(message, state)


# ── WebApp dan kelgan ma'lumot ────────────────────────
@router.message(OrderFlow.entering_address, F.web_app_data)
async def enter_map_location(message: Message, state: FSMContext):
    try:
        data = json.loads(message.web_app_data.data)
        lat = float(data["lat"])
        lon = float(data["lon"])
        addr_name = await _reverse_geocode(lat, lon)
        await state.update_data(address=addr_name, latitude=lat, longitude=lon)
        await message.answer(
            f"✅ Manzil aniqlandi!\n📍 {addr_name}",
            reply_markup=ReplyKeyboardRemove(),
        )
        await _ask_comment(message, state)
    except Exception:
        await message.answer(
            "⚠️ Xaritadan ma'lumot olishda xato. Qaytadan urinib ko'ring.",
            reply_markup=location_request_kb(),
        )


# ── Matn ko'rinishida manzil (foydalanuvchi o'zi yozadi) ─
@router.message(OrderFlow.entering_address, F.text)
async def enter_text_address(message: Message, state: FSMContext):
    text = message.text.strip()
    if len(text) < 5:
        await message.answer(
            "⚠️ Manzil juda qisqa. To'liq manzil yozing.\n"
            "<i>Masalan: Chilonzor 7-mavze, 12-uy</i>",
            parse_mode="HTML",
        )
        return
    await state.update_data(address=text)
    await _ask_comment(message, state)


# ── Izoh ─────────────────────────────────────────────
@router.message(OrderFlow.entering_comment, F.text == "/skip")
@router.message(OrderFlow.entering_comment)
async def enter_comment(message: Message, state: FSMContext):
    comment = "" if message.text == "/skip" else message.text.strip()
    await state.update_data(comment=comment)
    await message.answer(
        "💳 To'lov usulini tanlang:",
        reply_markup=payment_kb(),
    )
    await state.set_state(OrderFlow.choosing_payment)


# ── To'lov ────────────────────────────────────────────
@router.callback_query(OrderFlow.choosing_payment, F.data.startswith("pay:"))
async def choose_payment(callback: CallbackQuery, state: FSMContext):
    payment = callback.data.split(":")[1]
    await state.update_data(payment=payment)

    data = await state.get_data()
    cart = data.get("cart", {})

    lines = [f"• {v['name']} x{v['quantity']} — {v['price'] * v['quantity']:,.0f} so'm" for v in cart.values()]
    items_total = sum(v["price"] * v["quantity"] for v in cart.values())
    is_delivery = data["delivery_type"] == "delivery"

    delivery_fee = 0
    delivery_text = ""

    if is_delivery:
        delivery_text = "\n🚗 Dastavka: kuryer bilan yetkazib berish narxi kelishiladi"

    grand_total = items_total + delivery_fee
    await state.update_data(delivery_fee=delivery_fee)

    text = (
        "📋 <b>Zakaz xulosasi</b>\n\n"
        + "\n".join(lines)
        + f"\n\n🚚 Tur: {'🚗 Dastavka' if is_delivery else '🏪 Saboy'}"
        + (f"\n📍 Manzil: {data.get('address', '—')}" if is_delivery else "")
        + (f"\n💬 Izoh: {data['comment']}" if data.get("comment") else "")
        + "\n💳 To'lov: 💵 Naqd"
        + f"\n\n💰 Mahsulotlar: <b>{items_total:,.0f} so'm</b>"
        + delivery_text
    )

    await callback.message.answer(text, reply_markup=confirm_kb(), parse_mode="HTML")
    await state.set_state(OrderFlow.confirming)
    await callback.answer()


# ── Tasdiqlash ────────────────────────────────────────
@router.callback_query(OrderFlow.confirming, F.data == "confirm_order")
async def confirm_order(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cart = data.get("cart", {})

    items = [
        {"product_id": int(pid), "quantity": v["quantity"]}
        for pid, v in cart.items()
    ]

    try:
        order = await create_order(
            telegram_id=str(callback.from_user.id),
            order_data={
                "delivery_type": data["delivery_type"],
                "address": data.get("address"),
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude"),
                "comment": data.get("comment", ""),
                "payment_method": data.get("payment", "cash"),
                "delivery_fee": data.get("delivery_fee", 0),
                "branch_id": data.get("branch_id"),
                "items": items,
            },
        )
    except Exception:
        await callback.answer("⚠️ Server bilan bog'lanishda xato!", show_alert=True)
        await callback.message.answer(
            "⚠️ Zakaz yaratishda xato yuz berdi. Qaytadan urinib ko'ring."
        )
        return

    if not order or "id" not in order:
        await callback.answer("⚠️ Zakaz yaratishda xato!", show_alert=True)
        await callback.message.answer(
            "⚠️ Zakaz yaratishda xato yuz berdi. Qaytadan urinib ko'ring."
        )
        return

    user_name  = data.get("user_name",  "—")
    user_phone = data.get("user_phone", "—")
    branch_id = data.get("branch_id")
    branch_name = data.get("branch_name")

    await save_cart(state, {})
    await state.clear()

    # Filial ma'lumotlarini qayta tiklaymiz
    if branch_id:
        await state.update_data(branch_id=branch_id, branch_name=branch_name)

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.message.answer(
        f"✅ <b>Zakaz qabul qilindi!</b>\n\n"
        f"📦 Zakaz raqami: <b>#{order['id']}</b>\n"
        f"⏳ Holat: {STATUS_TEXT.get(order['status'], order['status'])}\n\n"
        f"Zakaz holati haqida xabar beramiz!",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()

    # Adminga xabar yuborish
    admin_chat_id = os.getenv("ADMIN_CHAT_ID", "")
    await notify_admin(
        bot=callback.bot,
        admin_chat_id=admin_chat_id,
        order=order,
        cart=cart,
        user_name=user_name,
        user_phone=user_phone,
    )


@router.callback_query(OrderFlow.confirming, F.data == "cancel_order")
async def cancel_order(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    branch_id = data.get("branch_id")
    branch_name = data.get("branch_name")
    await state.clear()
    if branch_id:
        await state.update_data(branch_id=branch_id, branch_name=branch_name)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer("❌ Zakaz bekor qilindi.", reply_markup=main_menu_kb())
    await callback.answer()
