from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def cart_kb(cart: dict) -> InlineKeyboardMarkup:
    """Savat klaviaturasi.

    Har mahsulot uchun bitta qator:  ➖ | Nomi N ta — narx | ➕
    Pastda esa Tozalash va Zakaz berish.

    Ko'p mahsulot bo'lganda ham foydalanuvchi pastdagi "Zakaz berish"
    tugmasiga osongina yetib boradi (qatorlar 2 baravar kam).
    """
    buttons = []
    for pid, item in cart.items():
        subtotal = item['price'] * item['quantity']
        # Nom uzunligini cheklaymiz — Telegram tugma matn limiti taxminan 64 belgi
        name = item['name']
        if len(name) > 18:
            name = name[:17] + "…"
        center_label = f"{name}  {item['quantity']} ta"
        buttons.append([
            InlineKeyboardButton(text="➖", callback_data=f"remove:{pid}"),
            InlineKeyboardButton(text=center_label, callback_data="noop"),
            InlineKeyboardButton(text="➕", callback_data=f"add:{pid}"),
        ])

    buttons.append([
        InlineKeyboardButton(text="🗑 Tozalash", callback_data="clear_cart"),
        InlineKeyboardButton(text="✅ Zakaz berish", callback_data="checkout"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
