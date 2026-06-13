from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from bot.states import ReviewFlow
from bot.api_client import create_review, get_user
from bot.keyboards.review import rating_kb

router = Router()

STARS = {1: "⭐", 2: "⭐⭐", 3: "⭐⭐⭐", 4: "⭐⭐⭐⭐", 5: "⭐⭐⭐⭐⭐"}


@router.message(Command("review"))
@router.message(F.text == "⭐ Baho berish")
async def start_review(message: Message, state: FSMContext):
    user = await get_user(str(message.from_user.id))
    if not user:
        await message.answer("Baho berish uchun avval ro'yxatdan o'ting!")
        return

    await message.answer(
        "⭐ Restoranımızni baholang:\n\n"
        "1 ⭐ — Yomon\n"
        "2 ⭐⭐ — Qoniqarsiz\n"
        "3 ⭐⭐⭐ — O'rtacha\n"
        "4 ⭐⭐⭐⭐ — Yaxshi\n"
        "5 ⭐⭐⭐⭐⭐ — Ajoyib!",
        reply_markup=rating_kb(),
    )
    await state.set_state(ReviewFlow.rating)


@router.callback_query(F.data.startswith("rate_order:"))
async def rate_order_inline(callback: CallbackQuery, state: FSMContext):
    """Buyurtma yetkazilgach yuborilgan inline yulduzlar (holatsiz boshlanadi)."""
    parts = callback.data.split(":")
    try:
        order_id = parts[1]
        rating = int(parts[2])
    except (IndexError, ValueError):
        await callback.answer()
        return
    user = await get_user(str(callback.from_user.id))
    if not user:
        await callback.answer("Avval ro'yxatdan o'ting", show_alert=True)
        return
    await state.update_data(rating=rating, review_order_id=order_id)
    await state.set_state(ReviewFlow.comment)
    # Tugmalarni olib tashlaymiz (qayta bosilmasin)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer(
        f"Siz {STARS[rating]} baho berdingiz. Rahmat! 🙏\n\n"
        f"💬 Izoh qoldiring (ixtiyoriy)\nYoki /skip yozing:"
    )
    await callback.answer("Bahoyingiz qabul qilindi")


@router.callback_query(ReviewFlow.rating, F.data.startswith("rate:"))
async def choose_rating(callback: CallbackQuery, state: FSMContext):
    rating = int(callback.data.split(":")[1])
    await state.update_data(rating=rating)

    await callback.message.answer(
        f"Siz {STARS[rating]} baho berdingiz.\n\n"
        f"💬 Izoh qoldiring (ixtiyoriy)\nYoki /skip yozing:"
    )
    await state.set_state(ReviewFlow.comment)
    await callback.answer()


@router.message(ReviewFlow.comment)
async def submit_review(message: Message, state: FSMContext):
    data = await state.get_data()
    comment = "" if message.text == "/skip" else message.text.strip()

    await create_review(
        telegram_id=str(message.from_user.id),
        rating=data["rating"],
        comment=comment,
    )
    await state.clear()

    await message.answer(
        f"✅ Rahmat! Sizning {STARS[data['rating']]} bahongiz qabul qilindi!\n\n"
        "Fikringiz bizga juda muhim 🙏",
    )
