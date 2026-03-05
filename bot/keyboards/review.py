from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def rating_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 ⭐", callback_data="rate:1"),
            InlineKeyboardButton(text="2 ⭐⭐", callback_data="rate:2"),
            InlineKeyboardButton(text="3 ⭐⭐⭐", callback_data="rate:3"),
        ],
        [
            InlineKeyboardButton(text="4 ⭐⭐⭐⭐", callback_data="rate:4"),
            InlineKeyboardButton(text="5 ⭐⭐⭐⭐⭐", callback_data="rate:5"),
        ],
    ])
