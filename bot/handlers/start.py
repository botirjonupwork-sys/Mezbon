from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from bot.states import Registration
from bot.api_client import get_user, create_user
from bot.keyboards.main import main_menu_kb, phone_kb

router = Router()


@router.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "🥟 <b>Muhsina Dollar Somsa</b> ga xush kelibsiz!\n\n"
        "Bizning mazali taomlarimizdan buyurtma bering!",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )


@router.message(F.text == "📝 Ro'yxatdan o'tish")
@router.message(F.text == "👤 Profil")
async def profile_handler(message: Message, state: FSMContext):
    user = await get_user(str(message.from_user.id))

    if user:
        await message.answer(
            f"👤 <b>Profilingiz</b>\n\n"
            f"Ism: {user['full_name']}\n"
            f"Telefon: {user['phone']}",
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
    cart = data.get("cart", {})  # Savatchani saqlab olamiz

    user = await create_user(
        telegram_id=str(message.from_user.id),
        full_name=data["full_name"],
        phone=phone,
    )

    await state.clear()

    # Savat bo'sh bo'lmasa — qayta tiklaymiz
    if cart:
        await state.update_data(cart=cart)

    await message.answer(
        f"✅ Ro'yxatdan o'tdingiz!\n\nXush kelibsiz, <b>{user['full_name']}</b>!",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )

    # Agar savatda mahsulot bo'lsa — davom etishni taklif qilamiz
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
    phone = message.contact.phone_number
    await _finish_registration(message, state, phone)


@router.message(Registration.phone, F.text)
async def reg_phone_text(message: Message, state: FSMContext):
    phone = message.text.strip()
    if not phone.startswith("+") or len(phone) < 10:
        await message.answer("❌ Noto'g'ri format. Masalan: +998901234567")
        return
    await _finish_registration(message, state, phone)
