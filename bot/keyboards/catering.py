"""Catering (tadbir uchun buyurtma) keyboardlari."""
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup
)
from datetime import datetime, timedelta


def catering_products_kb(products: list) -> InlineKeyboardMarkup:
    """Catering mahsulotlar tanlash."""
    rows = []
    for p in products:
        unit_label = _unit_label(p.get("unit_type"), p.get("quantity_step", 1))
        price = p.get("price_onsite_usd")
        label = f"{p['name_uz']} — ${price:.0f}/{unit_label}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"cat_prod:{p['id']}")])
    rows.append([InlineKeyboardButton(text="⬅️ Ortga", callback_data="cat_back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _unit_label(unit_type: str, step: int) -> str:
    if unit_type == "bunch_100":
        return f"{step} dona"
    if unit_type == "tandir_40":
        return "tandir (40 dona)"
    return "dona"


def delivery_subtype_kb() -> InlineKeyboardMarkup:
    """Yetkazib berish turini tanlash."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Joyiga borib yopib berish", callback_data="cat_dlv:onsite")],
        [InlineKeyboardButton(text="🛍 Olib ketish (saboy)", callback_data="cat_dlv:pickup")],
        [InlineKeyboardButton(text="🚗 Dastavka", callback_data="cat_dlv:delivery")],
        [InlineKeyboardButton(text="⬅️ Ortga", callback_data="cat_back_qty")],
    ])


def date_kb() -> InlineKeyboardMarkup:
    """30 kunlik sana tanlash — inline grid."""
    today = datetime.now().date()
    rows = []
    row = []
    for i in range(30):
        d = today + timedelta(days=i)
        label = f"{d.day}/{d.month}"
        if i == 0:
            label = f"Bugun ({label})"
        elif i == 1:
            label = f"Erta ({label})"
        row.append(InlineKeyboardButton(text=label, callback_data=f"cat_date:{d.isoformat()}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="⬅️ Ortga", callback_data="cat_back_dlv")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def time_kb() -> InlineKeyboardMarkup:
    """08:00 dan 22:00 gacha 30 daqiqa oralig'ida."""
    rows = []
    row = []
    for hour in range(8, 23):
        for minute in (0, 30):
            if hour == 22 and minute == 30:
                continue  # 22:00 gacha
            time_str = f"{hour:02d}:{minute:02d}"
            row.append(InlineKeyboardButton(text=time_str, callback_data=f"cat_time:{time_str}"))
            if len(row) == 4:
                rows.append(row)
                row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="⬅️ Ortga", callback_data="cat_back_date")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def phone_request_kb() -> ReplyKeyboardMarkup:
    """Telefon raqamni so'rash."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefonimni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def location_kb() -> ReplyKeyboardMarkup:
    """Lokatsiya so'rash."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Lokatsiya yuborish", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def payment_method_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 Naqd", callback_data="cat_pay_m:cash")],
        [InlineKeyboardButton(text="💳 Karta orqali", callback_data="cat_pay_m:card")],
    ])


def payment_timing_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ Hozir to'lash", callback_data="cat_pay_t:now")],
        [InlineKeyboardButton(text="⏱ Buyurtma olganda", callback_data="cat_pay_t:later")],
    ])


def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="cat_confirm")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cat_cancel")],
    ])


def quantity_kb(product: dict) -> InlineKeyboardMarkup:
    """Tezkor miqdor tanlash tugmalari."""
    step = product.get("quantity_step", 1)
    min_q = product.get("min_quantity", 1)

    if step >= 100:
        options = [min_q, min_q * 2, min_q * 3, min_q * 5, min_q * 10]
    else:
        options = [1, 2, 3, 5, 10]

    rows = []
    row = []
    for q in options:
        row.append(InlineKeyboardButton(text=str(q), callback_data=f"cat_qty:{q}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="✏️ Boshqa miqdor", callback_data="cat_qty_custom")])
    rows.append([InlineKeyboardButton(text="⬅️ Ortga", callback_data="cat_back_prod")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
