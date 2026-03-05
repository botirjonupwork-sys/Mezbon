from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from bot.api_client import get_user, get_user_orders, get_addresses, get_settings
from bot.keyboards.main import main_menu_kb

router = Router()

STATUS_TEXT = {
    "pending":    "⏳ Kutilmoqda",
    "confirmed":  "✅ Qabul qilindi",
    "preparing":  "👨‍🍳 Tayyorlanmoqda",
    "ready":      "📦 Tayyor",
    "delivering": "🚗 Yo'lda",
    "delivered":  "✅ Yetkazildi",
    "cancelled":  "❌ Bekor qilindi",
}


@router.message(F.text == "📦 Zakazlarim")
async def my_orders(message: Message):
    user = await get_user(str(message.from_user.id))
    if not user:
        await message.answer("Avval ro'yxatdan o'ting!")
        return

    orders = await get_user_orders(str(message.from_user.id))
    if not orders:
        await message.answer("Siz hali zakaz bermagansiz.")
        return

    text = "📦 <b>Zakazlaringiz:</b>\n\n"
    for order in orders[:10]:
        status = STATUS_TEXT.get(order["status"], order["status"])
        text += (
            f"#{order['id']} — {order['total_price']:,.0f} so'm — {status}\n"
        )

    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "📞 Bog'lanish")
async def contact_handler(message: Message):
    s = await get_settings()
    name       = s.get("restaurant_name", "Muhsina Dollar Somsa")
    phone      = s.get("phone", "—")
    address    = s.get("address", "—")
    work_from  = s.get("work_hours_from", "09:00")
    work_until = s.get("work_hours_until", "22:00")

    await message.answer(
        f"📞 <b>Bog'lanish</b>\n\n"
        f"🏪 <b>{name}</b>\n"
        f"📱 Telefon: {phone}\n"
        f"📍 Manzil: {address}\n"
        f"🕐 Ish vaqti: {work_from} – {work_until}",
        parse_mode="HTML",
    )
