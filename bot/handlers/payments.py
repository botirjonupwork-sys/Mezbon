"""Mijoz buyurtmasi to'lov handlerlari (Faza 11).

To'lov flow'i:
  1. Mijoz buyurtmani tasdiqlaydi (bot/handlers/order.py).
  2. Bot 3 ta inline tugma yuboradi (Click/Payme/Uzum). Har biri URL tugma —
     bosilganda foydalanuvchi qurilmasidagi mos app ochiladi.
  3. App ichida to'lov amalga oshadi → Yandex serverdan webhook'imizga
     keladi (api/services/order_webhook.py).
  4. Webhook handler order.payment_status'ni yangilaydi va mijozga
     "✅ To'lov qabul qilindi" yoki "❌ To'lov amalga oshmadi" xabarini yuboradi.

Bu fayl faqat **bekor qilish** uchun callback handler saqlaydi (tugma URL emas).
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot import api_client


router = Router(name="payments")
log = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("tgpay_cancel:"))
async def on_pay_cancel(callback: CallbackQuery) -> None:
    """To'lashdan oldin buyurtmani bekor qilish."""
    parts = (callback.data or "").split(":")
    if len(parts) != 2:
        await callback.answer("Noto'g'ri ma'lumot", show_alert=True)
        return
    try:
        order_id = int(parts[1])
    except ValueError:
        await callback.answer("Order ID xato", show_alert=True)
        return

    try:
        await api_client.cancel_unpaid_order(order_id)
    except Exception as e:
        log.exception("cancel unpaid failed")
        await callback.answer(f"Bekor qilishda xato: {e}", show_alert=True)
        return

    from bot.keyboards.main import main_menu_kb
    try:
        await callback.message.edit_text(
            f"❌ <b>Buyurtma #{order_id} bekor qilindi</b>\n\n"
            f"To'lov amalga oshirilmadi. Yangi buyurtma berishingiz mumkin.",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await callback.message.answer("Asosiy menyuga qaytdik.", reply_markup=main_menu_kb())
    await callback.answer("Buyurtma bekor qilindi")
