"""Catering keyboardlari — guruh tanlash, multi-product selector, sana/vaqt."""
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup
)
from datetime import datetime, timedelta


# ── Guruh tanlash ────────────────────────────────────

def groups_kb(groups: list) -> InlineKeyboardMarkup:
    """Somsa / Non tanlash."""
    rows = []
    for g in groups:
        label = f"{g['label']} (min {g['min_total']} ta)"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"cat_g:{g['group']}")])
    rows.append([InlineKeyboardButton(text="⬅️ Ortga", callback_data="cat_back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Multi-product selector ───────────────────────────

def items_selector_kb(products: list, selected: dict, group_info: dict) -> InlineKeyboardMarkup:
    """Har bir mahsulot uchun +/- va joriy miqdor.

    selected: {product_id: quantity}
    """
    rows = []
    for p in products:
        qty = selected.get(p["id"], 0)
        price_usd = p.get("unit_price_usd") or 0
        # Mahsulot nomi + narx
        header_text = f"{p['name_uz']} — ${price_usd:.1f}/dona"
        rows.append([InlineKeyboardButton(text=header_text, callback_data=f"cat_noop:{p['id']}")])
        # -1, miqdor, +1 (somsa), -40 yoki +40 (non)
        step = group_info.get("step", 1)
        minus_label = f"➖{step}" if step > 1 else "➖"
        plus_label = f"➕{step}" if step > 1 else "➕"
        rows.append([
            InlineKeyboardButton(text=minus_label, callback_data=f"cat_dec:{p['id']}"),
            InlineKeyboardButton(text=f"{qty}", callback_data=f"cat_ask_qty:{p['id']}"),
            InlineKeyboardButton(text=plus_label, callback_data=f"cat_inc:{p['id']}"),
        ])

    # Umumiy miqdor
    total = sum(selected.values())
    min_t = group_info.get("min_total", 0)
    status = f"✅ {total} / min {min_t}" if total >= min_t else f"⚠️ {total} / min {min_t}"
    rows.append([InlineKeyboardButton(text=status, callback_data="cat_noop:total")])

    rows.append([
        InlineKeyboardButton(text="✅ Davom etish", callback_data="cat_items_done"),
        InlineKeyboardButton(text="⬅️ Ortga", callback_data="cat_back_group"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Delivery type ────────────────────────────────────

def delivery_subtype_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Joyiga borib yopib berish", callback_data="cat_dlv:onsite")],
        [InlineKeyboardButton(text="🛍 Olib ketish (saboy)", callback_data="cat_dlv:pickup")],
        [InlineKeyboardButton(text="🚗 Dastavka", callback_data="cat_dlv:delivery")],
        [InlineKeyboardButton(text="⬅️ Ortga", callback_data="cat_back_items")],
    ])


# ── Sana tanlash ─────────────────────────────────────

MONTH_UZ = {
    1: "yanvar", 2: "fevral", 3: "mart", 4: "aprel",
    5: "may", 6: "iyun", 7: "iyul", 8: "avgust",
    9: "sentabr", 10: "oktabr", 11: "noyabr", 12: "dekabr",
}
WEEKDAY_UZ = ["Du", "Se", "Chor", "Pay", "Ju", "Sh", "Ya"]


def format_date_uz(d) -> str:
    """21-aprel, Seshanba kabi format."""
    return f"{d.day}-{MONTH_UZ.get(d.month, '')}, {WEEKDAY_UZ[d.weekday()]}"


def date_kb() -> InlineKeyboardMarkup:
    """30 kunlik sana — 2 qatorda, tushunarli format."""
    today = datetime.now().date()
    rows = []
    # Quick options
    rows.append([
        InlineKeyboardButton(text=f"📅 Bugun ({today.day}-{MONTH_UZ[today.month]})", callback_data=f"cat_date:{today.isoformat()}"),
    ])
    tomorrow = today + timedelta(days=1)
    rows.append([
        InlineKeyboardButton(text=f"📅 Erta ({tomorrow.day}-{MONTH_UZ[tomorrow.month]})", callback_data=f"cat_date:{tomorrow.isoformat()}"),
    ])
    # Keyingi 28 kun (2 ta ustun)
    row = []
    for i in range(2, 30):
        d = today + timedelta(days=i)
        label = f"{d.day}-{MONTH_UZ[d.month]} ({WEEKDAY_UZ[d.weekday()]})"
        row.append(InlineKeyboardButton(text=label, callback_data=f"cat_date:{d.isoformat()}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="✏️ Boshqa sana", callback_data="cat_date_custom")])
    rows.append([InlineKeyboardButton(text="⬅️ Ortga", callback_data="cat_back_dlv")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Vaqt tanlash ─────────────────────────────────────

def time_kb() -> InlineKeyboardMarkup:
    """08:00–22:00 oralig'ida 30 daqiqa qadam bilan."""
    rows = []
    row = []
    for hour in range(8, 23):
        for minute in (0, 30):
            if hour == 22 and minute == 30:
                continue
            time_str = f"{hour:02d}:{minute:02d}"
            row.append(InlineKeyboardButton(text=time_str, callback_data=f"cat_time:{time_str}"))
            if len(row) == 4:
                rows.append(row)
                row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="✏️ Boshqa vaqt", callback_data="cat_time_custom")])
    rows.append([InlineKeyboardButton(text="⬅️ Ortga", callback_data="cat_back_date")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Telefon / Lokatsiya ─────────────────────────────

def phone_request_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefonimni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def location_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Lokatsiya yuborish", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ── To'lov ──────────────────────────────────────────

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
