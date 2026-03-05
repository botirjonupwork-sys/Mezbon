import os
import httpx
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

API_URL = os.getenv("API_URL", "http://localhost:8000")


def accept_kb(order_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"accept:{order_id}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject:{order_id}"),
        ]
    ])


def delivered_kb(order_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yetkazildi", callback_data=f"delivered:{order_id}")]
    ])


@router.message(F.text == "📦 Faol zakazlar")
async def active_orders(message: Message):
    tg_id = str(message.from_user.id)
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{API_URL}/couriers/{tg_id}/orders")
            if r.status_code == 200:
                orders = r.json()
                if not orders:
                    await message.answer("📭 Hozircha faol zakazlar yo'q.")
                    return
                for o in orders:
                    text = (
                        f"📦 <b>Zakaz #{o['id']}</b>\n"
                        f"📍 Manzil: {o.get('address', '—')}\n"
                        f"💰 Summa: {o.get('total_price', 0):,.0f} so'm\n"
                        f"📊 Holat: {o.get('status', '—')}"
                    )
                    if o.get("status") == "delivering":
                        await message.answer(text, reply_markup=delivered_kb(o["id"]))
                    else:
                        await message.answer(text)
            else:
                await message.answer("⚠️ Zakazlarni olishda xato.")
    except Exception:
        await message.answer("⚠️ Server bilan bog'lanishda xato!")


@router.message(F.text == "📊 Mening statistikam")
async def my_stats(message: Message):
    tg_id = str(message.from_user.id)
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{API_URL}/couriers/{tg_id}/stats")
            if r.status_code == 200:
                data = r.json()
                await message.answer(
                    f"📊 <b>Statistika</b>\n\n"
                    f"📦 Jami yetkazilgan: {data.get('total_delivered', 0)}\n"
                    f"📦 Hozir faol: {data.get('active_orders', 0)}"
                )
            else:
                await message.answer("⚠️ Statistikani olishda xato.")
    except Exception:
        await message.answer("⚠️ Server bilan bog'lanishda xato!")


# Zakazni qabul qilish
@router.callback_query(F.data.startswith("accept:"))
async def accept_order(callback: CallbackQuery):
    order_id = int(callback.data.split(":")[1])
    tg_id = str(callback.from_user.id)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{API_URL}/couriers/{tg_id}/accept/{order_id}"
            )
            print(f"[CourierBot] Accept order #{order_id}: {r.status_code} {r.text[:200]}")
            if r.status_code == 200:
                order = r.json()
                await callback.answer("✅ Zakaz qabul qilindi!")
                try:
                    await callback.message.edit_reply_markup(reply_markup=delivered_kb(order_id))
                except Exception:
                    pass

                # Lokatsiyani yuborish
                lat = order.get("latitude")
                lon = order.get("longitude")
                if lat and lon:
                    await callback.message.answer("📍 Mijoz joylashuvi:")
                    await callback.message.answer_location(latitude=lat, longitude=lon)
            else:
                try:
                    err = r.json()
                except Exception:
                    err = {}
                detail = err.get("detail", "⚠️ Zakazni qabul qilib bo'lmadi!")
                await callback.answer(detail, show_alert=True)
    except Exception as e:
        print(f"[CourierBot] Accept error: {e}")
        await callback.answer("⚠️ Server xatosi!", show_alert=True)


# Zakazni rad etish
@router.callback_query(F.data.startswith("reject:"))
async def reject_order(callback: CallbackQuery):
    order_id = int(callback.data.split(":")[1])
    await callback.answer("Zakaz rad etildi.")
    try:
        await callback.message.edit_text(
            callback.message.text + "\n\n❌ <b>Rad etildi</b>",
            reply_markup=None,
            parse_mode="HTML",
        )
    except Exception:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass


# Yetkazildi
@router.callback_query(F.data.startswith("delivered:"))
async def mark_delivered(callback: CallbackQuery):
    order_id = int(callback.data.split(":")[1])
    tg_id = str(callback.from_user.id)

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{API_URL}/couriers/{tg_id}/delivered/{order_id}"
            )
            if r.status_code == 200:
                await callback.answer("✅ Yetkazildi deb belgilandi!")
                try:
                    await callback.message.edit_text(
                        callback.message.text + "\n\n✅ <b>Yetkazildi!</b>",
                        reply_markup=None,
                    )
                except Exception:
                    pass
            else:
                await callback.answer("⚠️ Xatolik!", show_alert=True)
    except Exception:
        await callback.answer("⚠️ Server xatosi!", show_alert=True)
