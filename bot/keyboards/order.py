from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)


def delivery_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚗 Dastavka", callback_data="delivery")],
        [InlineKeyboardButton(text="🏪 Saboy olib ketish", callback_data="pickup")],
    ])


def location_request_kb() -> ReplyKeyboardMarkup:
    """Joylashuvni yuborish uchun ReplyKeyboard."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Joylashuvni yuborish", request_location=True)],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def saved_addresses_kb(addresses: list) -> InlineKeyboardMarkup:
    """Saqlangan manzillar (inline)."""
    buttons = []
    for addr in addresses:
        buttons.append([InlineKeyboardButton(
            text=f"📍 {addr['title']} — {addr['address']}",
            callback_data=f"addr:{addr['address']}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def payment_kb() -> InlineKeyboardMarkup:
    """Asosiy zakaz uchun to'lov — faqat karta (Click/Payme).

    Naqd to'lov olib tashlandi (2026-05-01) — mijoz Telegram orqali oldindan
    karta bilan to'laydi, naqd kuryer'ga emas.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Click orqali to'lov", callback_data="pay:click")],
        [InlineKeyboardButton(text="💳 Payme orqali to'lov", callback_data="pay:payme")],
    ])


def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="confirm_order")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_order")],
    ])
