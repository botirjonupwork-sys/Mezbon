from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍽 Menyu"), KeyboardButton(text="🛒 Savat")],
            [KeyboardButton(text="📦 Zakazlarim"), KeyboardButton(text="👤 Profil")],
            [KeyboardButton(text="⭐ Baho berish"), KeyboardButton(text="📞 Bog'lanish")],
        ],
        resize_keyboard=True,
    )


def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📞 Raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
