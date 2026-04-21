from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍽 Menyu"), KeyboardButton(text="🛒 Savat")],
            [KeyboardButton(text="🎉 Tadbir uchun buyurtma")],
            [KeyboardButton(text="📦 Zakazlarim"), KeyboardButton(text="👤 Profil")],
            [KeyboardButton(text="📍 Filial tanlash"), KeyboardButton(text="📞 Bog'lanish")],
            [KeyboardButton(text="⭐ Baho berish")],
        ],
        resize_keyboard=True,
    )


def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📞 Raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def branch_location_kb() -> ReplyKeyboardMarkup:
    """Joylashuvni yuborish uchun tugma."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Joylashuvni yuborish", request_location=True)],
            [KeyboardButton(text="⬅️ Ortga")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def branches_kb(branches: list) -> InlineKeyboardMarkup:
    """Yaqin filiallar ro'yxati inline tugmalari."""
    buttons = []
    for b in branches:
        status = "✅" if b.get("is_open") else "❌"
        label = f"{status} {b['name']} ({b['distance_km']} km)"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"branch:{b['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
