from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def categories_kb(categories: list) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=cat["name_uz"], callback_data=f"cat:{cat['id']}")]
        for cat in categories
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def products_kb(products: list) -> InlineKeyboardMarkup:
    buttons = []
    for p in products:
        label = f"❌ {p['name_uz']}" if p["is_stop"] else f"{p['name_uz']} — {p['price']:,.0f} so'm"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"prod:{p['id']}")])

    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_categories")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def product_detail_kb(product: dict, quantity: int = 0) -> InlineKeyboardMarkup:
    """Mahsulot detail klaviaturasi — savattagi miqdorni ko'rsatadi."""
    buttons = []
    if not product["is_stop"]:
        if quantity > 0:
            # Savatta bor: ➖ | x{n} | ➕
            buttons.append([
                InlineKeyboardButton(text="➖", callback_data=f"remove:{product['id']}"),
                InlineKeyboardButton(text=f"🛒 {quantity} ta", callback_data="noop"),
                InlineKeyboardButton(text="➕", callback_data=f"add:{product['id']}"),
            ])
        else:
            # Savatta yo'q: bitta "Savatga" tugmasi
            buttons.append([
                InlineKeyboardButton(
                    text="🛒 Savatga qo'shish",
                    callback_data=f"add:{product['id']}"
                ),
            ])
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_categories")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
