from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)


UZ_TZ = ZoneInfo("Asia/Tashkent")


def _nav_row(*, back: bool = True, cancel: bool = True) -> list[InlineKeyboardButton]:
    """Orqaga / Bekor qilish qatori (inline)."""
    row: list[InlineKeyboardButton] = []
    if back:
        row.append(InlineKeyboardButton(text="⬅️ Orqaga", callback_data="order_back"))
    if cancel:
        row.append(InlineKeyboardButton(text="❌ Bekor qilish", callback_data="order_cancel"))
    return row


def time_slots_kb(work_from: str = "09:00", work_until: str = "22:00") -> InlineKeyboardMarkup:
    """Dastavka vaqti tanlash klaviaturasi.

    Birinchi tugma: "⚡ Hozir (30-60 daq ichida)"
    Keyin: hozir + 30 daqiqadan boshlab, har 30 daqiqada slot, work_until gacha.

    Tashkent vaqti bo'yicha hisoblanadi.
    """
    buttons = [
        [InlineKeyboardButton(
            text="⚡ Hozir (30-60 daq ichida)",
            callback_data="time:now",
        )],
    ]

    try:
        now = datetime.now(UZ_TZ)
        # Boshlanish: hozir + 30 daqiqa, keyin keyingi 30-daqiqalik slotga yaxlitlash
        start = now + timedelta(minutes=30)
        # 30-daqiqali slotga yaxlitlash (yuqoriga)
        if start.minute < 30:
            start = start.replace(minute=30, second=0, microsecond=0)
        else:
            start = (start + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

        # Tugash vaqti — work_until
        try:
            wh_h, wh_m = work_until.split(":")
            end = now.replace(hour=int(wh_h), minute=int(wh_m), second=0, microsecond=0)
        except (ValueError, AttributeError):
            end = now.replace(hour=22, minute=0, second=0, microsecond=0)

        # Agar work_until allaqachon o'tib ketgan bo'lsa — ertangi
        if end < start:
            end = end + timedelta(days=1)

        # Slotlarni yig'ish — har 30 daqiqada
        slot = start
        slots: list[str] = []
        while slot <= end and len(slots) < 24:  # max 12 soat
            slots.append(slot.strftime("%H:%M"))
            slot += timedelta(minutes=30)

        # 3 tugma bir qatorda — siqishtirilgan ko'rinish
        row: list[InlineKeyboardButton] = []
        for s in slots:
            row.append(InlineKeyboardButton(text=f"🕐 {s}", callback_data=f"time:{s}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
    except Exception:
        # Xato bo'lsa hech bo'lmaganda "Hozir" tugmasi qoladi
        pass

    buttons.append(_nav_row(back=True, cancel=True))
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def delivery_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚗 Dastavka", callback_data="delivery")],
        [InlineKeyboardButton(text="🏪 Saboy olib ketish", callback_data="pickup")],
        [InlineKeyboardButton(text="⬅️ Savatga", callback_data="order_back")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="order_cancel")],
    ])


def location_request_kb() -> ReplyKeyboardMarkup:
    """Joylashuvni yuborish uchun ReplyKeyboard (+ orqaga/bekor)."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Joylashuvni yuborish", request_location=True)],
            [KeyboardButton(text="⬅️ Orqaga"), KeyboardButton(text="❌ Bekor qilish")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def address_nav_kb() -> InlineKeyboardMarkup:
    """Manzil bosqichi uchun inline orqaga/bekor (saqlangan manzillar bilan birga)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        _nav_row(back=True, cancel=True),
    ])


def saved_addresses_kb(addresses: list) -> InlineKeyboardMarkup:
    """Saqlangan manzillar (inline) + navigatsiya."""
    buttons = []
    for addr in addresses:
        buttons.append([InlineKeyboardButton(
            text=f"📍 {addr['title']} — {addr['address']}",
            callback_data=f"addr:{addr['address']}"
        )])
    buttons.append(_nav_row(back=True, cancel=True))
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def payment_kb() -> InlineKeyboardMarkup:
    """Asosiy zakaz uchun to'lov — faqat karta (Click/Payme).

    Naqd to'lov olib tashlandi (2026-05-01) — mijoz Telegram orqali oldindan
    karta bilan to'laydi, naqd kuryer'ga emas.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Click orqali to'lov", callback_data="pay:click")],
        [InlineKeyboardButton(text="💳 Payme orqali to'lov", callback_data="pay:payme")],
        _nav_row(back=True, cancel=True),
    ])


def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="confirm_order")],
        _nav_row(back=True, cancel=True),
    ])


def comment_skip_kb() -> InlineKeyboardMarkup:
    """Izoh maydoni uchun — skip + orqaga/bekor."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ O'tkazib yuborish", callback_data="skip_comment")],
        _nav_row(back=True, cancel=True),
    ])
