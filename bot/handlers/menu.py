from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
import httpx
import os
from bot.api_client import get_categories, get_products, get_product, get_branch_categories, get_branch_products
from bot.keyboards.menu import categories_kb, products_kb, product_detail_kb

router = Router()

API_BASE = os.getenv("API_URL") or os.getenv("API_BASE_URL", "http://localhost:8000")


@router.message(F.text == "🍽 Menyu")
async def show_categories(message: Message, state: FSMContext):
    data = await state.get_data()
    branch_id = data.get("branch_id")

    if branch_id:
        categories = await get_branch_categories(branch_id)
    else:
        categories = await get_categories()

    if not categories:
        await message.answer("Menyu hozircha bo'sh.")
        return

    branch_name = data.get("branch_name", "")
    title = f"📋 <b>{branch_name} — Menyu</b>" if branch_name else "📋 <b>Menyu</b>"
    await message.answer(
        f"{title}\n\nQaysi bo'limni ko'rmoqchisiz?",
        reply_markup=categories_kb(categories),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("cat:"))
async def show_products(callback: CallbackQuery, state: FSMContext):
    category_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    branch_id = data.get("branch_id")

    products = await get_branch_products(category_id, branch_id) if branch_id else await get_products(category_id)

    if not products:
        await callback.answer("Bu bo'limda hozircha mahsulot yo'q", show_alert=True)
        return

    text = "🍽 <b>Mahsulotlar</b>\n\n"
    for p in products:
        stop = "❌ <i>Stop</i>" if p["is_stop"] else f"{p['price']:,.0f} so'm"
        time_note = ""
        if p["has_time_limit"] and not p["is_stop"]:
            time_note = f" ⏰ {p['available_from']}–{p['available_until']}"
        text += f"• {p['name_uz']} — {stop}{time_note}\n"

    await callback.message.edit_text(
        text,
        reply_markup=products_kb(products),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("prod:"))
async def show_product_detail(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split(":")[1])
    p = await get_product(product_id)

    if not p:
        await callback.answer("Mahsulot topilmadi", show_alert=True)
        return

    # Savattagi miqdorni olamiz
    data = await state.get_data()
    cart = data.get("cart", {})
    qty = cart.get(str(product_id), {}).get("quantity", 0)

    status = "❌ Hozir mavjud emas" if p["is_stop"] else f"✅ Mavjud — {p['price']:,.0f} so'm"
    desc = f"\n📝 {p['description_uz']}" if p.get("description_uz") else ""
    time_info = ""
    if p["has_time_limit"]:
        time_info = f"\n⏰ {p['available_from']} – {p['available_until']} gacha"

    caption = (
        f"🥟 <b>{p['name_uz']}</b>{desc}\n\n"
        f"💰 {status}{time_info}"
    )

    kb = product_detail_kb(p, quantity=qty)
    image_url = p.get("image_url")

    try:
        if image_url:
            full_url = image_url if image_url.startswith("http") else f"{API_BASE}{image_url}"
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(full_url)
                if resp.status_code == 200:
                    photo_bytes = BufferedInputFile(resp.content, filename="product.jpg")
                    await callback.message.delete()
                    await callback.message.answer_photo(
                        photo=photo_bytes,
                        caption=caption,
                        reply_markup=kb,
                        parse_mode="HTML",
                    )
                    return
    except Exception:
        pass

    # Rasmsiz
    try:
        await callback.message.edit_text(
            caption,
            reply_markup=kb,
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        await callback.message.answer(
            caption,
            reply_markup=kb,
            parse_mode="HTML",
        )


@router.callback_query(F.data == "back_to_categories")
async def back_to_categories(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    branch_id = data.get("branch_id")

    if branch_id:
        categories = await get_branch_categories(branch_id)
    else:
        categories = await get_categories()

    try:
        await callback.message.edit_text(
            "📋 <b>Menyu bo'limlari</b>",
            reply_markup=categories_kb(categories),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        await callback.message.answer(
            "📋 <b>Menyu bo'limlari</b>",
            reply_markup=categories_kb(categories),
            parse_mode="HTML",
        )
