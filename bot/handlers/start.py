from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from bot.states import Registration
from bot.api_client import get_user, create_user, get_nearest_branches, get_branch, get_restaurant_branches, set_user_branch, get_restaurant_id
from bot.keyboards.main import main_menu_kb, phone_kb, branch_location_kb, branches_kb
from bot.validators import normalize_uz_phone

router = Router()


@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    branch_id = data.get("branch_id")
    branch_name = data.get("branch_name", "")

    # 1) FSM da yo'q bo'lsa — DB'dan saqlangan filialni olish (faqat shu restoranniki)
    current_rid = get_restaurant_id()
    if not branch_id:
        user = await get_user(str(message.from_user.id))
        if user and user.get("selected_branch_id"):
            saved_branch = await get_branch(user["selected_branch_id"])
            # SaaS izolatsiya: saqlangan branch shu restoranniki ekanini tekshirish
            if saved_branch and saved_branch.get("restaurant_id") == current_rid:
                branch_id = saved_branch["id"]
                branch_name = saved_branch["name"]
                await state.update_data(branch_id=branch_id, branch_name=branch_name)
            elif saved_branch:
                # Boshqa restoranniki — bu user'ning shu botda boshqa branch tanlashi kerak
                pass

    # 2) Hali ham yo'q bo'lsa — filiallar sonini tekshiramiz
    if not branch_id:
        branches = await get_restaurant_branches()
        if len(branches) == 1:
            # 1 ta filial bor — avtomatik tanlash
            b = branches[0]
            branch_id = b["id"]
            branch_name = b["name"]
            await state.update_data(branch_id=branch_id, branch_name=branch_name)
            await set_user_branch(str(message.from_user.id), branch_id)
        elif len(branches) == 0:
            # Filial yo'q — restoran asosiy ma'lumotidan foydalanamiz
            await state.update_data(branch_id=None, branch_name=None, no_branches=True)

    # Restoran nomi va salomlash xabarini ko'rsatish
    from bot.api_client import get_settings
    settings_data = await get_settings()
    rest_name = settings_data.get("restaurant_name") or settings_data.get("name") or "Bizning restoran"

    if branch_id:
        # Filial tanlangan
        if not branch_name:
            branch = await get_branch(branch_id)
            branch_name = branch["name"] if branch else ""
        await message.answer(
            f"🥟 <b>{rest_name}</b> ga xush kelibsiz!\n\n"
            f"📍 Filial: <b>{branch_name}</b>\n\n"
            f"Bizning mazali taomlarimizdan buyurtma bering!",
            reply_markup=main_menu_kb(),
            parse_mode="HTML",
        )
    else:
        # Hali filial tanlanmagan — sonini tekshiramiz
        data = await state.get_data()
        no_branches = data.get("no_branches", False)
        if no_branches:
            # Filiallar yo'q — to'g'ridan-to'g'ri menyu
            await message.answer(
                f"🥟 <b>{rest_name}</b> ga xush kelibsiz!\n\n"
                f"Bizning mazali taomlarimizdan buyurtma bering!",
                reply_markup=main_menu_kb(),
                parse_mode="HTML",
            )
        else:
            # Bir nechta filial — tanlash kerak
            await message.answer(
                f"🥟 <b>{rest_name}</b> ga xush kelibsiz!\n\n"
                "📍 Avval yaqin filialini topish uchun joylashuvingizni yuboring!",
                reply_markup=branch_location_kb(),
                parse_mode="HTML",
            )


# ── Filial tanlash ─────────────────────────────────────

@router.message(F.text == "📍 Filial tanlash")
async def branch_select_start(message: Message, state: FSMContext):
    branches = await get_restaurant_branches()
    if len(branches) == 0:
        await state.update_data(no_branches=True, branch_id=None)
        await message.answer(
            "ℹ️ Bu restoranda hozircha filiallar yo'q.\n"
            "Buyurtma berishingiz mumkin — restoran asosiy manzilida xizmat ko'rsatiladi.",
            reply_markup=main_menu_kb(),
        )
        return
    await message.answer(
        "📍 Yaqin filiallarni topish uchun joylashuvingizni yuboring:",
        reply_markup=branch_location_kb(),
    )


@router.message(F.location)
async def branch_location_received(message: Message, state: FSMContext):
    """Joylashuv kelganda yaqin filiallarni ko'rsatish."""
    # Agar boshqa FSM oqimida bo'lsa — bu yerda ushlanmasin
    current_state = await state.get_state()
    if current_state and ("OrderFlow" in current_state or "CateringFlow" in current_state):
        return

    lat = message.location.latitude
    lon = message.location.longitude

    await message.answer("🔍 Yaqin filiallar qidirilmoqda...", reply_markup=ReplyKeyboardRemove())

    branches = await get_nearest_branches(lat, lon)
    if not branches:
        # Filial yo'q — restoran asosiy ma'lumotidan foydalanamiz
        await state.update_data(no_branches=True, branch_id=None)
        await message.answer(
            "ℹ️ Bu restoranda hozircha filiallar yo'q.\n"
            "Lekin buyurtma berishingiz mumkin — restoran sizga xizmat ko'rsatadi.",
            reply_markup=main_menu_kb(),
        )
        return

    # Foydalanuvchi koordinatalarini saqlash (delivery uchun)
    await state.update_data(user_lat=lat, user_lon=lon)

    text = "📍 <b>Yaqin filiallar:</b>\n\n"
    for b in branches[:5]:
        status = "✅ Ochiq" if b.get("is_open") else "❌ Yopiq"
        text += (
            f"🏪 <b>{b['name']}</b> — {b['distance_km']} km\n"
            f"   {status} | {b.get('work_hours_from', '09:00')} – {b.get('work_hours_until', '22:00')}\n"
        )
        if b.get("address"):
            text += f"   📍 {b['address']}\n"
        text += "\n"

    text += "Qaysi filialdan buyurtma bermoqchisiz?"
    await message.answer(text, reply_markup=branches_kb(branches[:5]), parse_mode="HTML")


@router.callback_query(F.data.startswith("branch:"))
async def branch_selected(callback: CallbackQuery, state: FSMContext):
    """Foydalanuvchi filial tanladi."""
    branch_id = int(callback.data.split(":")[1])
    branch = await get_branch(branch_id)

    if not branch:
        await callback.answer("Filial topilmadi!", show_alert=True)
        return

    if not branch.get("is_open"):
        await callback.answer(
            f"❌ {branch['name']} hozir yopiq!\n"
            f"Ish vaqti: {branch.get('work_hours_from', '09:00')} – {branch.get('work_hours_until', '22:00')}",
            show_alert=True,
        )
        return

    # Filial ID ni saqlash (FSM + DB)
    await state.update_data(branch_id=branch_id, branch_name=branch["name"])
    await set_user_branch(str(callback.from_user.id), branch_id)

    await callback.message.answer(
        f"✅ <b>{branch['name']}</b> filiali tanlandi!\n\n"
        f"📍 {branch.get('address', '')}\n"
        f"⏰ {branch.get('work_hours_from', '09:00')} – {branch.get('work_hours_until', '22:00')}\n\n"
        f"Endi menyudan buyurtma berishingiz mumkin!",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(F.text == "⬅️ Ortga")
async def back_to_main(message: Message):
    await message.answer("Asosiy menyu:", reply_markup=main_menu_kb())


# ── Profil ─────────────────────────────────────────────

@router.message(F.text == "📝 Ro'yxatdan o'tish")
@router.message(F.text == "👤 Profil")
async def profile_handler(message: Message, state: FSMContext):
    user = await get_user(str(message.from_user.id))

    if user:
        data = await state.get_data()
        branch_name = data.get("branch_name", "Tanlanmagan")
        await message.answer(
            f"👤 <b>Profilingiz</b>\n\n"
            f"Ism: {user['full_name']}\n"
            f"Telefon: {user['phone']}\n"
            f"📍 Filial: {branch_name}",
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )
    else:
        await message.answer(
            "Ro'yxatdan o'tish uchun ismingizni kiriting:",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.set_state(Registration.full_name)


# ── Ro'yxatdan o'tish FSM ─────────────────────────────

@router.message(Registration.full_name)
async def reg_name(message: Message, state: FSMContext):
    if len(message.text.strip()) < 2:
        await message.answer("Iltimos, to'liq ismingizni kiriting:")
        return

    await state.update_data(full_name=message.text.strip())
    await message.answer(
        "📞 Telefon raqamingizni yuboring:",
        reply_markup=phone_kb(),
    )
    await state.set_state(Registration.phone)


async def _finish_registration(message: Message, state: FSMContext, phone: str):
    """Ro'yxatdan o'tishni yakunlash — savatchani saqlab qolish bilan"""
    data = await state.get_data()
    cart = data.get("cart", {})
    branch_id = data.get("branch_id")
    branch_name = data.get("branch_name")

    user = await create_user(
        telegram_id=str(message.from_user.id),
        full_name=data["full_name"],
        phone=phone,
    )

    # FSM'da filial tanlangan bo'lsa, ro'yxatdan o'tgach DB'ga ham saqlaymiz
    if branch_id:
        await set_user_branch(str(message.from_user.id), branch_id)

    await state.clear()

    # Savat va filial ma'lumotlarini qayta tiklaymiz
    restore = {}
    if cart:
        restore["cart"] = cart
    if branch_id:
        restore["branch_id"] = branch_id
        restore["branch_name"] = branch_name
    if restore:
        await state.update_data(**restore)

    await message.answer(
        f"✅ Ro'yxatdan o'tdingiz!\n\nXush kelibsiz, <b>{user['full_name']}</b>!",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )

    if cart:
        total = sum(v["price"] * v["quantity"] for v in cart.values())
        count = sum(v["quantity"] for v in cart.values())
        await message.answer(
            f"🛒 Savatingizda <b>{count} ta</b> mahsulot bor ({total:,.0f} so'm)\n"
            f"Zakazni rasmiylashtirish uchun <b>🛒 Savat</b> tugmasini bosing.",
            parse_mode="HTML",
        )


@router.message(Registration.phone, F.contact)
async def reg_phone_contact(message: Message, state: FSMContext):
    phone = normalize_uz_phone(message.contact.phone_number)
    if not phone:
        await message.answer(
            "❌ Telefon raqami to'liq emas. Iltimos, to'liq raqam yuboring "
            "(masalan +998901234567)."
        )
        return
    await _finish_registration(message, state, phone)


@router.message(Registration.phone, F.text)
async def reg_phone_text(message: Message, state: FSMContext):
    phone = normalize_uz_phone(message.text)
    if not phone:
        await message.answer("❌ To'liq raqam kiriting. Masalan: +998901234567")
        return
    await _finish_registration(message, state, phone)
