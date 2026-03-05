from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def cart_kb(cart: dict) -> InlineKeyboardMarkup:
    """Savat klaviaturasi — har mahsulot 2 qatorda ko'rsatiladi:
    1-qator: Nomi + narxi (to'liq kenglik)
    2-qator: ➖ | miqdor | ➕
    """
    buttons = []
    for pid, item in cart.items():
        subtotal = item['price'] * item['quantity']
        # 1-qator: mahsulot nomi (to'liq kenglik, noop)
        buttons.append([
            InlineKeyboardButton(
                text=f"🥟 {item['name']} — {subtotal:,.0f} so'm",
                callback_data="noop"
            )
        ])
        # 2-qator: miqdor boshqarish
        buttons.append([
            InlineKeyboardButton(text="➖", callback_data=f"remove:{pid}"),
            InlineKeyboardButton(text=f"   {item['quantity']} ta   ", callback_data="noop"),
            InlineKeyboardButton(text="➕", callback_data=f"add:{pid}"),
        ])

    buttons.append([
        InlineKeyboardButton(text="🗑 Tozalash", callback_data="clear_cart"),
        InlineKeyboardButton(text="✅ Zakaz berish", callback_data="checkout"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
