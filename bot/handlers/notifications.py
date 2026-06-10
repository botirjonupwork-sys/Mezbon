"""Bildirishnomalar: adminga yangi zakaz, mijozga status yangilanishi"""
import html

from aiogram import Bot

STATUS_MSG = {
    "confirmed":  "✅ Zakazingiz qabul qilindi! Tayyorlanishni boshlaymiz.",
    "preparing":  "👨‍🍳 Zakazingiz tayyorlanmoqda...",
    "ready":      "📦 Zakazingiz tayyor! Kuryer tez orada jo'naydi.",
    "delivering": "🚗 Kuryeringiz yo'lda! Tez orada yetib keladi.",
    "delivered":  "✅ Zakazingiz yetkazildi! Ishtahangiz chog' bo'lsin! 🥟\n\n⭐ Bizni baholashni unutmang: /review",
    "cancelled":  "❌ Afsuski zakazingiz bekor qilindi. Boshqa savollarga javob berishga tayyormiz.",
}


async def notify_user(bot: Bot, telegram_id: str, order_id: int, new_status: str):
    """Mijozga zakaz holati haqida xabar yuborish"""
    msg = STATUS_MSG.get(new_status)
    if not msg:
        return
    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=f"📦 <b>Zakaz #{order_id}</b>\n\n{msg}",
            parse_mode="HTML",
        )
    except Exception:
        pass


async def notify_admin(
    bot: Bot,
    admin_chat_id: str,
    order: dict,
    cart: dict = None,
    user_name: str = "—",
    user_phone: str = "—",
):
    """Adminga yangi zakaz haqida xabar — mahsulot nomlari bilan"""
    if not admin_chat_id:
        return

    delivery = "🚗 Dastavka" if order.get("delivery_type") == "delivery" else "🏪 Saboy"

    if cart:
        items_text = "\n".join(
            f"  • {html.escape(str(v['name']))} x{v['quantity']} — {v['price'] * v['quantity']:,.0f} so'm"
            for v in cart.values()
        )
    else:
        items_text = "\n".join(
            f"  • #{i['product_id']} x{i['quantity']}"
            for i in order.get("items", [])
        )

    address_line = (
        f"\n📍 {html.escape(str(order.get('address', '—')))}"
        if order.get("delivery_type") == "delivery" else ""
    )
    comment_line = f"\n💬 {html.escape(str(order['comment']))}" if order.get("comment") else ""

    try:
        await bot.send_message(
            chat_id=admin_chat_id,
            text=(
                f"🔔 <b>Yangi zakaz #{order['id']}</b>\n\n"
                f"👤 {html.escape(str(user_name))}\n"
                f"📞 {html.escape(str(user_phone))}\n"
                f"{delivery}"
                f"{address_line}"
                f"{comment_line}\n\n"
                f"🛒 <b>Mahsulotlar:</b>\n{items_text}\n\n"
                f"💰 Jami: <b>{order.get('total_price', 0):,.0f} so'm</b>"
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass
