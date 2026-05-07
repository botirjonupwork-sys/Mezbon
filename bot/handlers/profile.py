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

PAYMENT_STATUS_TEXT = {
    "pending":         "💳 To'lov kutilmoqda",
    "paid":            "✅ To'langan",
    "partial":         "💰 Qisman",
    "refunded":        "💸 Qaytarilgan",
    "partial_refund":  "💸 Qisman qaytarilgan",
    "cancelled":       "❌ Bekor",
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
        ps = (order.get("payment_status") or "pending")
        ps_text = PAYMENT_STATUS_TEXT.get(ps, ps)
        line = (
            f"#{order['id']} — <b>{order['total_price']:,.0f} so'm</b>\n"
            f"   📋 {status}    {ps_text}"
        )
        # Telegram orqali to'langan bo'lsa, charge_id qisqartirib ko'rsatamiz
        ch = order.get("payment_charge_id")
        if ch and ps == "paid":
            line += f"\n   💳 tx: <code>{str(ch)[:12]}…</code>"
        text += line + "\n\n"

    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "📞 Bog'lanish")
async def contact_handler(message: Message):
    s = await get_settings()
    if not s:
        await message.answer(
            "⚠️ Hozircha kompaniya ma'lumotlari mavjud emas.\n"
            "Iltimos, keyinroq urinib ko'ring yoki administratorga murojaat qiling."
        )
        return

    name = s.get("restaurant_name") or s.get("name") or "Muhsina Dollar"
    phone = s.get("phone")
    address = s.get("address")
    work_from = s.get("work_hours_from")
    work_until = s.get("work_hours_until")

    lines = [f"📞 <b>Bog'lanish</b>\n", f"🏪 <b>{name}</b>"]
    if phone:
        lines.append(f"📱 Telefon: <a href='tel:{phone}'>{phone}</a>")
    if address:
        lines.append(f"📍 Manzil: {address}")
    if work_from and work_until:
        lines.append(f"🕐 Ish vaqti: {work_from} – {work_until}")

    if len(lines) <= 2:
        lines.append("\n<i>Qo'shimcha ma'lumotlar tez orada qo'shiladi.</i>")

    await message.answer("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)
