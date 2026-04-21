"""Catering (tadbir uchun buyurtma) oqimi — Dollar somsa va Nonlar.

Oqim:
1. Mahsulot tanlash
2. Miqdor
3. Yetkazib berish turi
4. Sana
5. Vaqt
6. Telefon
7. Lokatsiya (delivery yoki onsite bo'lsa)
8. To'lov usuli (naqd/karta)
9. To'lov vaqti (hozir/keyin)
10. Izoh (ixtiyoriy)
11. Tasdiqlash
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext

from bot.states import CateringFlow
from bot.api_client import (
    get_catering_products, calculate_catering_price, create_catering_order
)
from bot.keyboards.catering import (
    catering_products_kb, delivery_subtype_kb, date_kb, time_kb,
    phone_request_kb, location_kb, payment_method_kb, payment_timing_kb,
    confirm_kb, quantity_kb, _unit_label
)
from bot.keyboards.main import main_menu_kb

router = Router()


# ── Kirish: "🎉 Tadbir uchun buyurtma" ──────────────

@router.message(F.text == "🎉 Tadbir uchun buyurtma")
async def start_catering(message: Message, state: FSMContext):
    products = await get_catering_products()
    if not products:
        await message.answer("Hozircha catering mahsulotlari mavjud emas.")
        return

    await state.clear()
    await state.set_state(CateringFlow.choosing_product)
    await state.update_data(catering_products=products)

    text = (
        "🎉 <b>Tadbir uchun buyurtma</b>\n\n"
        "Bu bo'limda siz tadbirlar uchun somsa va non buyurtma berishingiz mumkin.\n"
        "Mahsulotni tanlang:"
    )
    await message.answer(text, reply_markup=catering_products_kb(products), parse_mode="HTML")


# ── 1. Mahsulot tanlash ──────────────────────────────

@router.callback_query(F.data.startswith("cat_prod:"))
async def product_selected(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    products = data.get("catering_products", [])
    product = next((p for p in products if p["id"] == product_id), None)
    if not product:
        await callback.answer("Mahsulot topilmadi", show_alert=True)
        return

    await state.update_data(product=product)
    await state.set_state(CateringFlow.choosing_quantity)

    unit_label = _unit_label(product.get("unit_type"), product.get("quantity_step", 1))
    min_q = product.get("min_quantity", 1)
    step = product.get("quantity_step", 1)

    text = (
        f"🛒 <b>{product['name_uz']}</b>\n\n"
        f"💰 Narxi: ${product['price_onsite_usd']:.0f} / {unit_label}\n"
        f"📦 Minimal: {min_q} dona\n"
    )
    if step > 1:
        text += f"📏 Qadam: {step} dona\n"
    text += "\nMiqdorni tanlang yoki kiriting:"

    await callback.message.edit_text(text, reply_markup=quantity_kb(product), parse_mode="HTML")
    await callback.answer()


# ── 2. Miqdor tanlash ────────────────────────────────

@router.callback_query(F.data.startswith("cat_qty:"))
async def quantity_selected(callback: CallbackQuery, state: FSMContext):
    quantity = int(callback.data.split(":")[1])
    await _set_quantity_and_continue(callback.message, state, quantity)
    await callback.answer()


@router.callback_query(F.data == "cat_qty_custom")
async def quantity_custom_prompt(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    product = data.get("product", {})
    step = product.get("quantity_step", 1)
    min_q = product.get("min_quantity", 1)
    unit_label = _unit_label(product.get("unit_type"), step)

    hint = f"{min_q} {unit_label}"
    if step > 1:
        hint = f"{min_q}, {min_q + step}, {min_q + step * 2}... ({step} qadam bilan)"

    await callback.message.answer(
        f"Miqdorni kiriting (minimal: {min_q}, {hint}):",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(CateringFlow.choosing_quantity)
    await callback.answer()


@router.message(CateringFlow.choosing_quantity, F.text)
async def quantity_typed(message: Message, state: FSMContext):
    try:
        quantity = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting")
        return

    data = await state.get_data()
    product = data.get("product", {})
    min_q = product.get("min_quantity", 1)
    step = product.get("quantity_step", 1)

    if quantity < min_q:
        await message.answer(f"❌ Minimal miqdor: {min_q}")
        return
    if step > 1 and quantity % step != 0:
        await message.answer(f"❌ Miqdor {step} ga karrali bo'lishi kerak")
        return

    await _set_quantity_and_continue(message, state, quantity)


async def _set_quantity_and_continue(message: Message, state: FSMContext, quantity: int):
    data = await state.get_data()
    product = data.get("product", {})
    min_q = product.get("min_quantity", 1)
    step = product.get("quantity_step", 1)

    if quantity < min_q:
        await message.answer(f"❌ Minimal miqdor: {min_q}")
        return
    if step > 1 and quantity % step != 0:
        await message.answer(f"❌ Miqdor {step} ga karrali bo'lishi kerak")
        return

    await state.update_data(quantity=quantity)
    await state.set_state(CateringFlow.choosing_delivery)

    unit_label = _unit_label(product.get("unit_type"), step)
    await message.answer(
        f"✅ Miqdor: <b>{quantity} {unit_label}</b>\n\n"
        f"🚗 Yetkazib berish turini tanlang:",
        reply_markup=delivery_subtype_kb(),
        parse_mode="HTML",
    )


# ── 3. Yetkazib berish turi ──────────────────────────

@router.callback_query(F.data.startswith("cat_dlv:"))
async def delivery_selected(callback: CallbackQuery, state: FSMContext):
    subtype = callback.data.split(":")[1]
    await state.update_data(delivery_subtype=subtype)
    await state.set_state(CateringFlow.choosing_date)

    labels = {
        "onsite": "🏠 Joyiga borib yopib berish",
        "pickup": "🛍 Olib ketish (saboy)",
        "delivery": "🚗 Dastavka",
    }
    await callback.message.edit_text(
        f"✅ {labels.get(subtype, subtype)}\n\n"
        f"📅 Qaysi sanaga kerak?",
        reply_markup=date_kb(),
    )
    await callback.answer()


# ── 4. Sana tanlash ──────────────────────────────────

@router.callback_query(F.data.startswith("cat_date:"))
async def date_selected(callback: CallbackQuery, state: FSMContext):
    date_str = callback.data.split(":", 1)[1]
    await state.update_data(schedule_date=date_str)
    await state.set_state(CateringFlow.choosing_time)
    await callback.message.edit_text(
        f"✅ Sana: <b>{date_str}</b>\n\n"
        f"⏰ Qaysi vaqtga tayyor bo'lsin?",
        reply_markup=time_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


# ── 5. Vaqt tanlash ──────────────────────────────────

@router.callback_query(F.data.startswith("cat_time:"))
async def time_selected(callback: CallbackQuery, state: FSMContext):
    time_str = callback.data.split(":", 1)[1]
    await state.update_data(schedule_time=time_str)
    await state.set_state(CateringFlow.entering_phone)
    await callback.message.delete()
    await callback.message.answer(
        f"✅ Vaqt: <b>{time_str}</b>\n\n"
        f"📞 Telefon raqamingizni yuboring:",
        reply_markup=phone_request_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


# ── 6. Telefon ───────────────────────────────────────

@router.message(CateringFlow.entering_phone, F.contact)
async def phone_contact(message: Message, state: FSMContext):
    await _save_phone(message, state, message.contact.phone_number)


@router.message(CateringFlow.entering_phone, F.text)
async def phone_typed(message: Message, state: FSMContext):
    phone = message.text.strip()
    if not phone.startswith("+") or len(phone) < 10:
        await message.answer("❌ Noto'g'ri format. Masalan: +998901234567")
        return
    await _save_phone(message, state, phone)


async def _save_phone(message: Message, state: FSMContext, phone: str):
    await state.update_data(phone=phone)
    data = await state.get_data()
    delivery_subtype = data.get("delivery_subtype")

    if delivery_subtype in ("onsite", "delivery"):
        await state.set_state(CateringFlow.entering_location)
        await message.answer(
            "📍 Tadbir manzili (lokatsiya yuboring):",
            reply_markup=location_kb(),
        )
    else:
        # Pickup — lokatsiya kerak emas
        await _ask_payment_method(message, state)


# ── 7. Lokatsiya ─────────────────────────────────────

@router.message(CateringFlow.entering_location, F.location)
async def location_received(message: Message, state: FSMContext):
    await state.update_data(
        latitude=message.location.latitude,
        longitude=message.location.longitude,
    )
    await _ask_address_text(message, state)


async def _ask_address_text(message: Message, state: FSMContext):
    await state.update_data(address_pending=True)
    await message.answer(
        "✅ Lokatsiya olindi\n\n"
        "Manzilni matn bilan yozib yuboring (masalan: <i>Toshkent, Yunusobod, To'yxona \"Grand\"</i>):",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML",
    )


@router.message(CateringFlow.entering_location, F.text)
async def address_text(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("address_pending"):
        await message.answer("Iltimos, avval lokatsiyani yuboring 📍")
        return
    await state.update_data(address=message.text.strip())
    await _ask_payment_method(message, state)


# ── 8. To'lov usuli ──────────────────────────────────

async def _ask_payment_method(message: Message, state: FSMContext):
    await state.set_state(CateringFlow.choosing_payment_method)
    await message.answer(
        "💳 To'lov usulini tanlang:",
        reply_markup=payment_method_kb(),
    )


@router.callback_query(F.data.startswith("cat_pay_m:"))
async def payment_method_selected(callback: CallbackQuery, state: FSMContext):
    method = callback.data.split(":")[1]
    await state.update_data(payment_method=method)
    await state.set_state(CateringFlow.choosing_payment_timing)
    await callback.message.edit_text(
        "⏰ To'lov vaqtini tanlang:",
        reply_markup=payment_timing_kb(),
    )
    await callback.answer()


# ── 9. To'lov vaqti ──────────────────────────────────

@router.callback_query(F.data.startswith("cat_pay_t:"))
async def payment_timing_selected(callback: CallbackQuery, state: FSMContext):
    timing = callback.data.split(":")[1]
    await state.update_data(payment_timing=timing)

    # Tasdiqlashga o'tish
    await _show_confirmation(callback.message, state, edit=True)
    await callback.answer()


# ── 10. Tasdiqlash ───────────────────────────────────

async def _show_confirmation(message: Message, state: FSMContext, edit: bool = False):
    data = await state.get_data()
    product = data.get("product", {})
    quantity = data.get("quantity")
    delivery_subtype = data.get("delivery_subtype")

    # Narxni hisoblash
    price = await calculate_catering_price(
        product_id=product["id"],
        quantity=quantity,
        delivery_subtype=delivery_subtype,
        distance_km=None,  # TODO: masofa hisoblash kerak bo'lsa
    )

    if not price:
        await message.answer("❌ Narxni hisoblashda xato.")
        return

    delivery_labels = {
        "onsite": "🏠 Joyiga borib yopib berish",
        "pickup": "🛍 Olib ketish (saboy)",
        "delivery": "🚗 Dastavka",
    }
    payment_m_labels = {"cash": "💵 Naqd", "card": "💳 Karta"}
    payment_t_labels = {"now": "⚡ Hozir", "later": "⏱ Buyurtma olganda"}

    unit_label = _unit_label(product.get("unit_type"), product.get("quantity_step", 1))

    text = (
        f"📋 <b>Buyurtma tasdiqlash</b>\n\n"
        f"🛒 Mahsulot: <b>{product['name_uz']}</b>\n"
        f"📦 Miqdor: <b>{quantity} {unit_label}</b>\n"
        f"🚗 Turi: {delivery_labels.get(delivery_subtype, delivery_subtype)}\n"
        f"📅 Sana: <b>{data.get('schedule_date')}</b>\n"
        f"⏰ Vaqt: <b>{data.get('schedule_time')}</b>\n"
        f"📞 Tel: {data.get('phone')}\n"
    )
    if data.get("address"):
        text += f"📍 Manzil: {data.get('address')}\n"
    text += (
        f"💳 To'lov: {payment_m_labels.get(data.get('payment_method'))} — "
        f"{payment_t_labels.get(data.get('payment_timing'))}\n\n"
        f"💰 <b>Jami:</b>\n"
        f"   💵 {price['total_price_uzs']:,.0f} so'm\n"
        f"   💲 ${price['total_price_usd']:.2f}\n"
        f"   📊 Kurs: 1$ = {price['currency_rate']:,.0f} so'm\n\n"
        f"Tasdiqlaysizmi?"
    )

    await state.update_data(
        calculated_price=price,
        latest_confirmation_text=text,
    )
    await state.set_state(CateringFlow.confirming)

    if edit:
        try:
            await message.edit_text(text, reply_markup=confirm_kb(), parse_mode="HTML")
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=confirm_kb(), parse_mode="HTML")


@router.callback_query(F.data == "cat_confirm")
async def confirm_order(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    product = data.get("product", {})

    order_data = {
        "product_id": product["id"],
        "quantity": data.get("quantity"),
        "delivery_subtype": data.get("delivery_subtype"),
        "schedule_date": data.get("schedule_date"),
        "schedule_time": data.get("schedule_time"),
        "phone": data.get("phone"),
        "payment_method": data.get("payment_method"),
        "payment_timing": data.get("payment_timing"),
    }
    if data.get("address"):
        order_data["address"] = data.get("address")
    if data.get("latitude"):
        order_data["latitude"] = data.get("latitude")
        order_data["longitude"] = data.get("longitude")

    branch_id = data.get("branch_id")
    result = await create_catering_order(
        str(callback.from_user.id), order_data, branch_id
    )

    if not result or result.get("error"):
        err_msg = result.get("error") if result else "Nomalum xato"
        await callback.message.answer(
            f"❌ Buyurtma yaratishda xato: {err_msg}",
            reply_markup=main_menu_kb(),
        )
        await state.clear()
        await callback.answer()
        return

    # Muvaffaqiyatli
    text = (
        f"✅ <b>Buyurtma #{result['id']} qabul qilindi!</b>\n\n"
        f"{result.get('message', '')}\n\n"
        f"💰 Jami: {result['total_price_uzs']:,.0f} so'm (${result['total_price_usd']:.2f})"
    )

    payment_info = result.get("payment_info")
    if payment_info and data.get("payment_timing") == "now":
        text += (
            f"\n\n💳 <b>To'lov uchun karta:</b>\n"
            f"<code>{payment_info['card_number']}</code>\n"
            f"Egasi: {payment_info['owner']}\n\n"
            f"To'lov amalga oshirilgandan so'ng check rasmini menejerga yuboring."
        )

    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.message.answer("Asosiy menyuga qaytdik.", reply_markup=main_menu_kb())
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "cat_cancel")
async def cancel_order(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Buyurtma bekor qilindi.")
    await callback.message.answer("Asosiy menyuga qaytdik.", reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "cat_back_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("Asosiy menyu:", reply_markup=main_menu_kb())
    await callback.answer()
