"""Catering oqimi — Somsa va Non aralash buyurtmalari.

Yangi oqim:
1. Guruh tanlash (Somsa / Non)
2. Mahsulotlar selector (turli turlardan miqdor)
3. Umumiy miqdor tekshirish
4. Yetkazib berish turi
5. Sana
6. Vaqt
7. Telefon
8. Lokatsiya
9. To'lov
10. Tasdiqlash
"""
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext

from bot.states import CateringFlow
from bot.api_client import (
    get_catering_groups, calculate_catering_price_multi, create_catering_order
)
from bot.keyboards.catering import (
    groups_kb, items_selector_kb, ask_qty_menu_kb, delivery_subtype_kb, date_kb, time_kb,
    phone_request_kb, location_kb, payment_method_kb, payment_timing_kb,
    confirm_kb, format_date_uz, MONTH_UZ
)
from bot.keyboards.main import main_menu_kb

router = Router()


# ── Kirish ───────────────────────────────────────────

@router.message(F.text == "🎉 Tadbir uchun buyurtma")
async def start_catering(message: Message, state: FSMContext):
    groups = await get_catering_groups()
    if not groups or not any(g.get("products") for g in groups):
        await message.answer("Hozircha catering mahsulotlari mavjud emas.")
        return

    await state.clear()
    await state.set_state(CateringFlow.choosing_group)
    await state.update_data(catering_groups=groups)

    await message.answer(
        "🎉 <b>Tadbir uchun buyurtma</b>\n\n"
        "Qaysi guruhdan buyurtma bermoqchisiz?",
        reply_markup=groups_kb(groups),
        parse_mode="HTML",
    )


# ── 1. Guruh tanlash ─────────────────────────────────

@router.callback_query(F.data.startswith("cat_g:"))
async def group_selected(callback: CallbackQuery, state: FSMContext):
    group = callback.data.split(":")[1]
    data = await state.get_data()
    groups = data.get("catering_groups", [])
    group_info = next((g for g in groups if g["group"] == group), None)
    if not group_info or not group_info.get("products"):
        await callback.answer("Bu guruhda mahsulot yo'q", show_alert=True)
        return

    await state.update_data(
        group=group,
        group_info=group_info,
        selected_items={},  # {product_id: quantity}
    )
    await state.set_state(CateringFlow.selecting_items)

    text = _build_selector_text(group_info, {})
    await callback.message.edit_text(
        text,
        reply_markup=items_selector_kb(group_info["products"], {}, group_info),
        parse_mode="HTML",
    )
    await callback.answer()


def _build_selector_text(group_info: dict, selected: dict) -> str:
    min_t = group_info.get("min_total", 0)
    step = group_info.get("step", 1)
    total = sum(selected.values())
    step_info = f", jami {step} ga karrali" if step > 1 else ""
    return (
        f"🛒 <b>{group_info['label']} — mahsulotlar tanlash</b>\n\n"
        f"📏 Minimal: <b>{min_t} ta</b>{step_info}\n"
        f"📦 Hozir tanlangan: <b>{total} ta</b>\n\n"
        f"<i>Har bir mahsulot ostidagi tugmalardan miqdor qo'shing:</i>\n"
        f"<i>• ➕ tugmasi bosilganda shu miqdor qo'shiladi</i>\n"
        f"<i>• ➖ 10 donaga kamaytiradi, 0️ — tozalash</i>\n"
        f"<i>• Turli mahsulotlarni aralashtirib tanlashingiz mumkin</i>"
    )


# ── 2. Items quick-add va ± ──────────────────────────

@router.callback_query(F.data.startswith("cat_add:"))
async def item_add(callback: CallbackQuery, state: FSMContext):
    """Quick-add tugmasi: +10, +50, +100, +20, +40 ..."""
    parts = callback.data.split(":")
    product_id = int(parts[1])
    delta = int(parts[2])
    await _apply_delta(callback, state, product_id, delta)


@router.callback_query(F.data.startswith("cat_dec:"))
async def item_dec(callback: CallbackQuery, state: FSMContext):
    """Minus: default 10 ga kamaytiradi (yoki 1 agar kam bo'lsa)."""
    product_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    selected = dict(data.get("selected_items", {}))
    current = selected.get(product_id, 0)
    dec = 10 if current >= 10 else (current or 1)
    await _apply_delta(callback, state, product_id, -dec)


@router.callback_query(F.data.startswith("cat_zero:"))
async def item_zero(callback: CallbackQuery, state: FSMContext):
    """Mahsulot miqdorini 0 ga tushirish."""
    product_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    selected = dict(data.get("selected_items", {}))
    selected.pop(product_id, None)
    await state.update_data(selected_items=selected)
    await _refresh_selector(callback, state)


async def _apply_delta(callback: CallbackQuery, state: FSMContext, product_id: int, delta: int):
    data = await state.get_data()
    selected = dict(data.get("selected_items", {}))
    current = selected.get(product_id, 0)
    new_q = max(0, current + delta)
    if new_q == 0:
        selected.pop(product_id, None)
    else:
        selected[product_id] = new_q
    await state.update_data(selected_items=selected)
    await _refresh_selector(callback, state)


async def _refresh_selector(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    group_info = data.get("group_info", {})
    selected = data.get("selected_items", {})
    text = _build_selector_text(group_info, selected)
    try:
        await callback.message.edit_text(
            text,
            reply_markup=items_selector_kb(group_info["products"], selected, group_info),
            parse_mode="HTML",
        )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "cat_ask_qty_menu")
async def ask_qty_menu(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    group_info = data.get("group_info", {})
    selected = data.get("selected_items", {})
    await callback.message.edit_text(
        "Qaysi mahsulot uchun aniq miqdor kiritmoqchisiz?",
        reply_markup=ask_qty_menu_kb(group_info.get("products", []), selected),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cat_ask_qty:"))
async def item_ask_qty(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split(":")[1])
    await state.update_data(pending_product_id=product_id)
    await state.set_state(CateringFlow.entering_quantity)

    data = await state.get_data()
    group_info = data.get("group_info", {})
    product = next((p for p in group_info.get("products", []) if p["id"] == product_id), None)
    await callback.message.answer(
        f"{product['name_uz'] if product else 'Mahsulot'} uchun miqdorni kiriting (raqam):",
        reply_markup=ReplyKeyboardRemove(),
    )
    await callback.answer()


@router.message(CateringFlow.entering_quantity, F.text)
async def item_qty_typed(message: Message, state: FSMContext):
    try:
        qty = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting")
        return
    if qty < 0:
        await message.answer("❌ Manfiy raqam bo'lmaydi")
        return

    data = await state.get_data()
    product_id = data.get("pending_product_id")
    group_info = data.get("group_info", {})
    selected = dict(data.get("selected_items", {}))
    if qty == 0:
        selected.pop(product_id, None)
    else:
        selected[product_id] = qty
    await state.update_data(selected_items=selected, pending_product_id=None)
    await state.set_state(CateringFlow.selecting_items)

    text = _build_selector_text(group_info, selected)
    await message.answer(
        text,
        reply_markup=items_selector_kb(group_info["products"], selected, group_info),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("cat_noop"))
async def noop(callback: CallbackQuery):
    await callback.answer()


# ── 3. Items done ────────────────────────────────────

@router.callback_query(F.data == "cat_items_done")
async def items_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected_items", {})
    group_info = data.get("group_info", {})
    total = sum(selected.values())
    min_t = group_info.get("min_total", 0)
    step = group_info.get("step", 1)

    if total < min_t:
        await callback.answer(f"Minimal {min_t} ta kerak!", show_alert=True)
        return
    if step > 1 and total % step != 0:
        await callback.answer(f"Jami miqdor {step} ga karrali bo'lishi kerak!", show_alert=True)
        return

    await state.set_state(CateringFlow.choosing_delivery)
    await callback.message.edit_text(
        f"✅ Mahsulotlar tanlandi (jami: {total} ta)\n\n"
        f"🚗 Yetkazib berish turini tanlang:",
        reply_markup=delivery_subtype_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "cat_back_group")
async def back_to_group(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    groups = data.get("catering_groups", [])
    await state.set_state(CateringFlow.choosing_group)
    await callback.message.edit_text(
        "🎉 <b>Tadbir uchun buyurtma</b>\n\nQaysi guruhdan buyurtma bermoqchisiz?",
        reply_markup=groups_kb(groups),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "cat_back_items")
async def back_to_items(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    group_info = data.get("group_info", {})
    selected = data.get("selected_items", {})
    await state.set_state(CateringFlow.selecting_items)
    text = _build_selector_text(group_info, selected)
    await callback.message.edit_text(
        text,
        reply_markup=items_selector_kb(group_info["products"], selected, group_info),
        parse_mode="HTML",
    )
    await callback.answer()


# ── 4. Delivery ──────────────────────────────────────

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
        f"✅ {labels.get(subtype, subtype)}\n\n📅 Qaysi sanaga kerak?",
        reply_markup=date_kb(),
    )
    await callback.answer()


# ── 5. Sana ──────────────────────────────────────────

@router.callback_query(F.data.startswith("cat_date:"))
async def date_selected(callback: CallbackQuery, state: FSMContext):
    date_str = callback.data.split(":", 1)[1]
    d = datetime.fromisoformat(date_str).date()
    await state.update_data(schedule_date=date_str)
    await state.set_state(CateringFlow.choosing_time)
    await callback.message.edit_text(
        f"✅ Sana: <b>{format_date_uz(d)}</b>\n\n⏰ Qaysi vaqtga tayyor bo'lsin?",
        reply_markup=time_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "cat_date_custom")
async def date_custom(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CateringFlow.entering_date_custom)
    today = datetime.now().date()
    example = (today + timedelta(days=7)).strftime("%d.%m.%Y")
    await callback.message.answer(
        f"📅 Sanani kiriting (masalan: <code>{example}</code> yoki <code>{example.replace('.', '/')}</code>)\n\n"
        f"🗓 Formatlar: <b>DD.MM.YYYY</b> yoki <b>DD/MM/YYYY</b> yoki <b>DD-MM-YYYY</b>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(CateringFlow.entering_date_custom, F.text)
async def date_custom_input(message: Message, state: FSMContext):
    text = message.text.strip().replace("/", ".").replace("-", ".")
    try:
        d = datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer("❌ Format noto'g'ri. Masalan: 28.04.2026")
        return

    today = datetime.now().date()
    if d < today:
        await message.answer("❌ Sana o'tmishda bo'lmasligi kerak")
        return
    if (d - today).days > 60:
        await message.answer("❌ Eng ko'pi bilan 60 kun oldinga yozilsin")
        return

    await state.update_data(schedule_date=d.isoformat())
    await state.set_state(CateringFlow.choosing_time)
    await message.answer(
        f"✅ Sana: <b>{format_date_uz(d)}</b>\n\n⏰ Qaysi vaqtga tayyor bo'lsin?",
        reply_markup=time_kb(),
        parse_mode="HTML",
    )


# ── 6. Vaqt ──────────────────────────────────────────

@router.callback_query(F.data.startswith("cat_time:"))
async def time_selected(callback: CallbackQuery, state: FSMContext):
    time_str = callback.data.split(":", 1)[1]
    await state.update_data(schedule_time=time_str)
    await state.set_state(CateringFlow.entering_phone)
    await callback.message.delete()
    await callback.message.answer(
        f"✅ Vaqt: <b>{time_str}</b>\n\n📞 Telefon raqamingizni yuboring:",
        reply_markup=phone_request_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "cat_time_custom")
async def time_custom(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CateringFlow.entering_time_custom)
    await callback.message.answer(
        "⏰ Vaqtni kiriting (masalan: <code>14:30</code> yoki <code>9:00</code>)\n\n"
        "Format: <b>HH:MM</b> (24 soatli)",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(CateringFlow.entering_time_custom, F.text)
async def time_custom_input(message: Message, state: FSMContext):
    text = message.text.strip()
    try:
        t = datetime.strptime(text, "%H:%M").time()
    except ValueError:
        try:
            t = datetime.strptime(text, "%H.%M").time()
        except ValueError:
            await message.answer("❌ Format noto'g'ri. Masalan: 14:30")
            return
    time_str = t.strftime("%H:%M")
    await state.update_data(schedule_time=time_str)
    await state.set_state(CateringFlow.entering_phone)
    await message.answer(
        f"✅ Vaqt: <b>{time_str}</b>\n\n📞 Telefon raqamingizni yuboring:",
        reply_markup=phone_request_kb(),
        parse_mode="HTML",
    )


# ── 7. Telefon ───────────────────────────────────────

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
            "📍 Tadbir manzili — <b>lokatsiya yuboring</b>:",
            reply_markup=location_kb(),
            parse_mode="HTML",
        )
    else:
        await _ask_payment_method(message, state)


# ── 8. Lokatsiya ─────────────────────────────────────

@router.message(CateringFlow.entering_location, F.location)
async def location_received(message: Message, state: FSMContext):
    await state.update_data(
        latitude=message.location.latitude,
        longitude=message.location.longitude,
        address_pending=True,
    )
    await message.answer(
        "✅ Lokatsiya olindi.\n\n"
        "Manzilni matn bilan kiriting (masalan: <i>To'yxona \"Navoi\"</i>):",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML",
    )


@router.message(CateringFlow.entering_location, F.text)
async def address_text(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("address_pending"):
        await message.answer("Iltimos, avval lokatsiyani yuboring 📍", reply_markup=location_kb())
        return
    await state.update_data(address=message.text.strip())
    await _ask_payment_method(message, state)


# ── 9. To'lov usuli ──────────────────────────────────

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


# ── 10. To'lov vaqti ─────────────────────────────────

@router.callback_query(F.data.startswith("cat_pay_t:"))
async def payment_timing_selected(callback: CallbackQuery, state: FSMContext):
    timing = callback.data.split(":")[1]
    await state.update_data(payment_timing=timing)
    await _show_confirmation(callback.message, state, edit=True)
    await callback.answer()


# ── 11. Tasdiqlash ───────────────────────────────────

async def _show_confirmation(message: Message, state: FSMContext, edit: bool = False):
    data = await state.get_data()
    selected = data.get("selected_items", {})
    group = data.get("group")
    group_info = data.get("group_info", {})
    delivery_subtype = data.get("delivery_subtype")

    items = [{"product_id": int(pid), "quantity": q} for pid, q in selected.items() if q > 0]
    price = await calculate_catering_price_multi(
        group=group,
        items=items,
        delivery_subtype=delivery_subtype,
        distance_km=None,
    )
    if not price or price.get("error"):
        await message.answer(f"❌ Narxni hisoblashda xato: {price.get('error') if price else ''}")
        return

    delivery_labels = {
        "onsite": "🏠 Joyiga borib yopib berish",
        "pickup": "🛍 Olib ketish (saboy)",
        "delivery": "🚗 Dastavka",
    }
    payment_m_labels = {"cash": "💵 Naqd", "card": "💳 Karta"}
    payment_t_labels = {"now": "⚡ Hozir", "later": "⏱ Buyurtma olganda"}

    # Mahsulotlar ro'yxati
    items_text = ""
    for b in price.get("breakdown", []):
        items_text += f"  • {b['name_uz']}: <b>{b['quantity']} ta</b> (${b['item_usd']:.2f})\n"

    d = datetime.fromisoformat(data.get("schedule_date")).date()
    text = (
        f"📋 <b>Buyurtma tasdiqlash</b>\n\n"
        f"🎉 Guruh: <b>{group_info.get('label', group)}</b>\n"
        f"{items_text}"
        f"📦 Jami: <b>{price['total_quantity']} ta</b>\n\n"
        f"🚗 Turi: {delivery_labels.get(delivery_subtype)}\n"
        f"📅 Sana: <b>{format_date_uz(d)}</b>\n"
        f"⏰ Vaqt: <b>{data.get('schedule_time')}</b>\n"
        f"📞 Tel: {data.get('phone')}\n"
    )
    if data.get("address"):
        text += f"📍 Manzil: {data.get('address')}\n"
    text += (
        f"💳 To'lov: {payment_m_labels.get(data.get('payment_method'))} — "
        f"{payment_t_labels.get(data.get('payment_timing'))}\n\n"
        f"💰 <b>Jami summa:</b>\n"
        f"   💵 {price['total_price_uzs']:,.0f} so'm\n"
        f"   💲 ${price['total_price_usd']:.2f}\n"
        f"   📊 Kurs: 1$ = {price['currency_rate']:,.0f} so'm\n"
    )
    if price.get("delivery_fee_uzs"):
        text += f"   🚗 Dastavka: {price['delivery_fee_uzs']:,.0f} so'm\n"
    text += "\nTasdiqlaysizmi?"

    await state.update_data(calculated_price=price)
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
    selected = data.get("selected_items", {})
    items = [{"product_id": int(pid), "quantity": q} for pid, q in selected.items() if q > 0]

    order_data = {
        "group": data.get("group"),
        "items": items,
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
    result = await create_catering_order(str(callback.from_user.id), order_data, branch_id)

    if not result or result.get("error"):
        err = result.get("error") if result else "Noma'lum xato"
        await callback.message.answer(
            f"❌ Buyurtma yaratishda xato: {err}",
            reply_markup=main_menu_kb(),
        )
        await state.clear()
        await callback.answer()
        return

    text = (
        f"✅ <b>Buyurtma #{result['id']} qabul qilindi!</b>\n\n"
        f"{result.get('message', '')}\n\n"
        f"📦 Jami: {result['total_quantity']} ta\n"
        f"💰 {result['total_price_uzs']:,.0f} so'm (${result['total_price_usd']:.2f})"
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


@router.callback_query(F.data == "cat_back_dlv")
async def back_to_delivery(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CateringFlow.choosing_delivery)
    await callback.message.edit_text(
        "🚗 Yetkazib berish turini tanlang:",
        reply_markup=delivery_subtype_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "cat_back_date")
async def back_to_date(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CateringFlow.choosing_date)
    await callback.message.edit_text(
        "📅 Qaysi sanaga kerak?",
        reply_markup=date_kb(),
    )
    await callback.answer()
