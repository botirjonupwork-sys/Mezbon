import json
import os
import math
import logging
import httpx
from datetime import datetime
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

UZ_TZ = ZoneInfo("Asia/Tashkent")
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from bot.states import OrderFlow
from bot.api_client import get_user, create_order, get_addresses, get_branch
from bot import api_client
from bot.handlers.cart import get_cart, save_cart
from bot.handlers.notifications import notify_admin
from bot.keyboards.order import (
    delivery_type_kb, payment_kb, confirm_kb,
    location_request_kb, saved_addresses_kb,
    time_slots_kb, comment_skip_kb,
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


async def _show_progress_and_ask(message: Message, state: FSMContext, ask_text: str, **kwargs):
    """Hozirgi qadamda — yig'ilgan ma'lumotlar + keyingi savol."""
    data = await state.get_data()
    progress = _format_progress(data)
    text = (f"📋 <b>Buyurtma ma'lumotlari</b>\n{progress}\n\n" if progress else "") + ask_text
    await message.answer(text, parse_mode="HTML", **kwargs)


# Eski _ask_comment olib tashlangan — yangi versiya pastda (Faza 10)
# qisqartirilgan xabar va comment_skip_kb klaviaturasi bilan
    await state.set_state(OrderFlow.entering_comment)


@router.callback_query(F.data == "checkout")
async def checkout_start(callback: CallbackQuery, state: FSMContext):
    cart = await get_cart(state)
    if not cart:
        await callback.answer("Savat bo'sh!", show_alert=True)
        return

    data = await state.get_data()
    branch_id = data.get("branch_id")
    no_branches = data.get("no_branches", False)

    # Agar branch_id va no_branches flag yo'q bo'lsa — DB'dan tekshirish
    if not branch_id and not no_branches:
        from bot.api_client import get_restaurant_branches
        branches = await get_restaurant_branches()
        if len(branches) == 0:
            no_branches = True
            await state.update_data(no_branches=True)
        else:
            await callback.answer("📍 Avval filial tanlang!", show_alert=True)
            return

    # Filial ochiqligini tekshirish (faqat filial tanlangan bo'lsa)
    branch_info = await get_branch(branch_id) if branch_id else None
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
        # Saboy uchun vaqt va manzil bosqichlari o'tkazib yuboriladi
        await state.update_data(address="Saboy olib ketish", delivery_time_slot="now")
        await _ask_comment(callback.message, state, pickup=True)
    else:
        # Dastavka — avval vaqt tanlash, keyin manzil
        data = await state.get_data()
        branch_id = data.get("branch_id")
        branch_info = await get_branch(branch_id) if branch_id else None
        work_from = (branch_info or {}).get("work_hours_from") or _load_settings().get("work_hours_from", "09:00")
        work_until = (branch_info or {}).get("work_hours_until") or _load_settings().get("work_hours_until", "22:00")

        await state.set_state(OrderFlow.choosing_time)
        await callback.message.answer(
            "⏰ <b>Buyurtmangiz qachon yetkazib berilsin?</b>",
            reply_markup=time_slots_kb(work_from=work_from, work_until=work_until),
            parse_mode="HTML",
        )

    await callback.answer()


# ── Vaqt tanlash (Faza 10) ──────────────────────────────
@router.callback_query(OrderFlow.choosing_time, F.data.startswith("time:"))
async def choose_delivery_time(callback: CallbackQuery, state: FSMContext):
    """Dastavka vaqti — Hozir / Keyinroq slot."""
    parts = (callback.data or "").split(":", 1)
    if len(parts) != 2:
        await callback.answer("Vaqt tanlash xato", show_alert=True)
        return
    choice = parts[1]

    if choice == "back":
        # Dastavka turini qayta tanlash
        await state.set_state(OrderFlow.choosing_delivery)
        await callback.message.answer(
            "🚚 Yetkazib berish turini tanlang:",
            reply_markup=delivery_type_kb(),
        )
        await callback.answer()
        return

    # "now" yoki "HH:MM"
    if choice != "now":
        # Format tekshirish
        try:
            hh, mm = choice.split(":")
            int(hh); int(mm)
        except (ValueError, IndexError):
            await callback.answer("Vaqt format xato", show_alert=True)
            return

    await state.update_data(delivery_time_slot=choice)

    # Manzil bosqichiga o'tish
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
        "📍 Tugmani bosing — joriy joylashuv yuboriladi\n"
        "📎 Yoki skrepka → Joylashuv → xaritadan tanlash\n\n"
        "<i>Manzilni matn ko'rinishida ham yozishingiz mumkin</i>",
        reply_markup=location_request_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


async def _ask_comment(message: Message, state: FSMContext, *, pickup: bool = False):
    """Izoh so'rash — qisqartirilgan xabar (Faza 10)."""
    prefix = ""
    if pickup:
        prefix = "🏪 Bizning manzil: <b>Toshkent sh.</b>\n\n"
    await message.answer(
        f"{prefix}💬 Izoh qoldiring yoki <b>/skip</b> bosing",
        reply_markup=comment_skip_kb(),
        parse_mode="HTML",
    )
    await state.set_state(OrderFlow.entering_comment)


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
@router.callback_query(OrderFlow.entering_comment, F.data == "skip_comment")
async def skip_comment_callback(callback: CallbackQuery, state: FSMContext):
    """Izoh skip tugmasi orqali — bo'sh saqlash va davom etish."""
    await _process_comment(callback.message, state, comment_text="")
    await callback.answer()


@router.message(OrderFlow.entering_comment, F.text == "/skip")
@router.message(OrderFlow.entering_comment)
async def enter_comment(message: Message, state: FSMContext):
    """Izoh kiritildi → darhol tasdiqlash xulosasi (to'lov turi tasdiqdan keyin)."""
    comment = "" if (message.text or "") == "/skip" else (message.text or "").strip()
    await _process_comment(message, state, comment_text=comment)


async def _process_comment(message: Message, state: FSMContext, *, comment_text: str):
    """Izohni qabul qilib, tasdiqlash xulosasini ko'rsatish."""
    comment = comment_text or ""
    # Telegram message length cheklov + XSS himoya
    if len(comment) > 500:
        comment = comment[:500] + "…"
    await state.update_data(comment=comment, payment="card")  # default karta

    data = await state.get_data()
    cart = data.get("cart", {})

    lines = [f"• {v['name']} x{v['quantity']} — {v['price'] * v['quantity']:,.0f} so'm" for v in cart.values()]
    items_total = sum(v["price"] * v["quantity"] for v in cart.values())
    is_delivery = data["delivery_type"] == "delivery"

    delivery_fee = 0
    delivery_text = ""
    if is_delivery:
        delivery_text = "\n🚗 Dastavka: kuryer bilan yetkazib berish narxi kelishiladi"
    await state.update_data(delivery_fee=delivery_fee)

    # QQS — restaurant.is_vat_payer bo'lsa ko'rsatamiz
    vat_text = ""
    try:
        from bot.api_client import get_settings as _gs
        settings = await _gs()
        if settings.get("is_vat_payer"):
            vat_percent = float(settings.get("vat_percent") or 0)
            if vat_percent > 0:
                # ichkarida (inclusive) VAT — total ichidan ushlab olinadi
                vat_amount = items_total * vat_percent / (100 + vat_percent)
                vat_text = f"\n📊 QQS ({vat_percent:.0f}%, ichkarida): <b>{vat_amount:,.0f} so'm</b>"
    except Exception:
        pass

    text = (
        "📋 <b>Buyurtma ma'lumotlari</b>\n\n"
        + _format_progress(data)
        + "\n\n<b>Mahsulotlar:</b>\n"
        + "\n".join(lines)
        + f"\n\n💰 Jami: <b>{items_total:,.0f} so'm</b>"
        + vat_text
        + delivery_text
        + "\n\n💳 To'lov: tasdiqlagandan keyin Click/Payme/Uzum tanlanadi"
        + "\n\nTasdiqlaysizmi?"
    )

    await message.answer(text, reply_markup=confirm_kb(), parse_mode="HTML")
    await state.set_state(OrderFlow.confirming)


def _format_progress(data: dict, *, payment_done: bool = False, provider_label: str = "") -> str:
    """Buyurtma ma'lumotlarini "checklist" shaklida ko'rsatish.

    Foydalanuvchi har qadamda allaqachon kiritgan ma'lumotlarni ko'radi —
    ishonch beradi va ortga qaytishda yo'qotmaydi.

    XSS himoyasi: foydalanuvchi kiritgan barcha matnlar HTML escape qilinadi.
    """
    from html import escape as _esc
    lines = []
    user_name = _esc(str(data.get("user_name") or "—"))
    user_phone = _esc(str(data.get("user_phone") or "—"))
    lines.append(f"👤 {user_name}  📞 {user_phone}")

    delivery_type = data.get("delivery_type")
    if delivery_type == "delivery":
        lines.append("✅ Turi: 🚗 Dastavka")
    elif delivery_type == "pickup":
        lines.append("✅ Turi: 🏪 Saboy olib ketish")

    # Faza 10: Dastavka vaqti
    time_slot = data.get("delivery_time_slot")
    if delivery_type == "delivery":
        if time_slot == "now":
            lines.append("✅ Vaqt: ⚡ Hozir (30-60 daq ichida)")
        elif time_slot:
            lines.append(f"✅ Vaqt: 🕐 {_esc(str(time_slot))}")

    address = data.get("address")
    if address and delivery_type == "delivery":
        lines.append(f"✅ Manzil: {_esc(str(address))}")

    comment = data.get("comment")
    if comment:
        lines.append(f"✅ Izoh: {_esc(str(comment))}")
    elif comment == "":
        lines.append("✅ Izoh: yo'q")

    if payment_done and provider_label:
        lines.append(f"✅ To'lov: 💳 {_esc(str(provider_label))}")

    return "\n".join(lines)


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
                # Faza 10: dastavka vaqti
                "delivery_time_slot": data.get("delivery_time_slot"),
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

    # ── Direct app link to'lov: Click / Payme / Uzum ──
    # Foydalanuvchi tugmaga bossa, telefondagi app avtomatik ochiladi va to'lov o'sha yerda bo'ladi.
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    provider_label = {
        "click": "💳 Click bilan to'lash",
        "payme": "💳 Payme bilan to'lash",
        "uzum":  "💳 Uzum bilan to'lash",
    }

    try:
        pay_data = await api_client.get_pay_options(order['id'])
        options = pay_data.get('options') or []
    except Exception as e:
        log.exception("get_pay_options failed")
        options = []

    rows = []
    for opt in options:
        prov = opt.get('provider')
        url = opt.get('url')
        if prov and url:
            rows.append([InlineKeyboardButton(text=provider_label.get(prov, prov), url=url)])

    rows.append([InlineKeyboardButton(text="❌ Buyurtmani bekor qilish", callback_data=f"tgpay_cancel:{order['id']}")])
    pay_kb = InlineKeyboardMarkup(inline_keyboard=rows)

    if options:
        body = (
            f"💳 <b>To'lov usulini tanlang — Buyurtma #{order['id']}</b>\n\n"
            f"💰 To'lanadigan summa: <b>{order.get('total_price', 0):,.0f} so'm</b>\n\n"
            f"⬇️ Tugma bosilganda telefoningizdagi mos app ochiladi va to'lovni o'sha yerda yakunlaysiz.\n"
            f"<i>To'lov tasdiqlanganda bu chat'ga avtomatik xabar yuboriladi.</i>"
        )
    else:
        body = (
            f"⚠️ <b>To'lov usuli sozlanmagan</b>\n\n"
            f"Buyurtma #{order['id']}\n"
            f"Restoran administratori Click/Payme/Uzum sozlamalarini hali yoqmagan.\n\n"
            f"Iltimos, naqd to'lovni tanlang yoki restoran bilan bog'laning."
        )

    await callback.message.answer(body, parse_mode="HTML", reply_markup=pay_kb)
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
