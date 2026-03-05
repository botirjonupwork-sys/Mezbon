from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from bot.api_client import get_product
from bot.keyboards.cart import cart_kb
from bot.keyboards.menu import product_detail_kb
from bot.keyboards.main import main_menu_kb

router = Router()


async def get_cart(state: FSMContext) -> dict:
    data = await state.get_data()
    return data.get("cart", {})


async def save_cart(state: FSMContext, cart: dict):
    await state.update_data(cart=cart)


def _is_product_detail_view(callback: CallbackQuery) -> bool:
    """Xabar mahsulot detail sahifasida ekanligini tekshiramiz.
    back_to_categories tugmasi bormi — shu bilan aniqlaymiz."""
    if not callback.message or not callback.message.reply_markup:
        return False
    for row in callback.message.reply_markup.inline_keyboard:
        for btn in row:
            if btn.callback_data == "back_to_categories":
                return True
    return False


async def _edit_message_markup(callback: CallbackQuery, markup):
    """Xabar klaviaturasini yangilaymiz — photo yoki text bo'lsin."""
    try:
        await callback.message.edit_reply_markup(reply_markup=markup)
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("add:"))
async def add_to_cart(callback: CallbackQuery, state: FSMContext):
    product_id = callback.data.split(":")[1]
    product = await get_product(int(product_id))

    if not product or product["is_stop"]:
        await callback.answer("❌ Bu mahsulot hozir mavjud emas", show_alert=True)
        return

    # Vaqt limiti tekshiruvi
    if product.get("has_time_limit"):
        now = datetime.now().strftime("%H:%M")
        avail_from = product.get("available_from", "00:00")
        avail_until = product.get("available_until", "23:59")
        if not (avail_from <= now <= avail_until):
            await callback.answer(
                f"⏰ Bu mahsulot faqat {avail_from} – {avail_until} oralig'ida mavjud!",
                show_alert=True,
            )
            return

    cart = await get_cart(state)
    if product_id in cart:
        cart[product_id]["quantity"] += 1
    else:
        cart[product_id] = {
            "name": product["name_uz"],
            "price": product["price"],
            "quantity": 1,
        }

    await save_cart(state, cart)
    qty = cart[product_id]["quantity"]
    total = sum(v["price"] * v["quantity"] for v in cart.values())
    count = sum(v["quantity"] for v in cart.values())

    if _is_product_detail_view(callback):
        # Mahsulot detail sahifasida: faqat klaviaturani yangilaymiz
        new_kb = product_detail_kb(product, quantity=qty)
        await _edit_message_markup(callback, new_kb)
        await callback.answer(
            f"✅ Savatda: {qty} ta | Jami: {total:,.0f} so'm"
        )
    else:
        # Savat sahifasida: savat xabarini to'liq yangilaymiz
        await show_cart_message(callback.message, cart, edit=True)
        await callback.answer(
            f"✅ Qo'shildi! Savat: {count} ta — {total:,.0f} so'm"
        )


@router.callback_query(F.data.startswith("remove:"))
async def remove_from_cart(callback: CallbackQuery, state: FSMContext):
    product_id = callback.data.split(":")[1]
    cart = await get_cart(state)

    if product_id in cart:
        if cart[product_id]["quantity"] > 1:
            cart[product_id]["quantity"] -= 1
        else:
            del cart[product_id]

    await save_cart(state, cart)

    if _is_product_detail_view(callback):
        # Mahsulot detail sahifasida: faqat klaviaturani yangilaymiz
        product = await get_product(int(product_id))
        qty = cart.get(product_id, {}).get("quantity", 0)
        new_kb = product_detail_kb(product, quantity=qty)
        await _edit_message_markup(callback, new_kb)
        total = sum(v["price"] * v["quantity"] for v in cart.values())
        if qty > 0:
            await callback.answer(f"Savatda: {qty} ta | Jami: {total:,.0f} so'm")
        else:
            await callback.answer("Mahsulot savatdan olib tashlandi")
    else:
        # Savat sahifasida: savat xabarini to'liq yangilaymiz
        await show_cart_message(callback.message, cart, edit=True)
        await callback.answer()


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    """Miqdor ko'rsatuvchi tugma — hech narsa qilmaydi."""
    await callback.answer()


@router.message(F.text == "🛒 Savat")
async def show_cart(message: Message, state: FSMContext):
    cart = await get_cart(state)
    await show_cart_message(message, cart)


async def show_cart_message(message: Message, cart: dict, edit: bool = False):
    if not cart:
        text = "🛒 Savatingiz bo'sh.\n\nMenyu dan mahsulot tanlang!"
        kb = None
    else:
        lines = []
        total = 0.0
        for pid, item in cart.items():
            subtotal = item["price"] * item["quantity"]
            total += subtotal
            lines.append(
                f"• {item['name']} x{item['quantity']} = {subtotal:,.0f} so'm"
            )

        text = (
            "🛒 <b>Savat</b>\n\n"
            + "\n".join(lines)
            + f"\n\n💰 Jami: <b>{total:,.0f} so'm</b>"
        )
        kb = cart_kb(cart)

    if edit:
        try:
            await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except TelegramBadRequest:
            await message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "clear_cart")
async def clear_cart(callback: CallbackQuery, state: FSMContext):
    await save_cart(state, {})
    try:
        await callback.message.edit_text("🗑 Savat tozalandi.")
    except TelegramBadRequest:
        pass
    await callback.answer()
