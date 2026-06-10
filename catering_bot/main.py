"""Catering Notifier Bot.

Vazifasi:
1. `/start` bosgan foydalanuvchi yoki qo'shilgan guruhni DB'ga saqlash
2. Har kuni soat 20:00 da ertangi kun catering buyurtmalarini obunachilarga yuborish
3. Har buyurtma alohida xabarda: lokatsiya + ma'lumot bitta xabarda
4. Oxirida umumiy ro'yxat yuboriladi

BOT_TOKEN: CATERING_BOT_TOKEN .env dan olinadi
"""
import asyncio
import html
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, ChatMemberUpdated
from dotenv import load_dotenv
from sqlalchemy import select

from api.database import AsyncSessionLocal
from database.models import CateringSubscriber, Order, OrderItem, Product, User, OrderStatus

load_dotenv()

UZ_TZ = ZoneInfo("Asia/Tashkent")

# Multi-tenant izolyatsiya: bu catering bot QAYSI restoranga tegishli.
# Buyurtmalar ham, obunachilar ham FAQAT shu restoran bo'yicha filtrlanadi —
# aks holda bir restoran buyurtmalari (mijoz ismi/telefoni) boshqa restoran
# obunachilariga oqib ketadi. Bot manager BOT_RESTAURANT_ID ni o'rnatadi;
# standalone deploy uchun CATERING_RESTAURANT_ID, default 1.
CATERING_RESTAURANT_ID = int(
    os.getenv("CATERING_RESTAURANT_ID") or os.getenv("BOT_RESTAURANT_ID") or "1"
)


def build_dispatcher(bot: Bot) -> Dispatcher:
    """Dispatcher va handler'larni bitta joyda ishga tushirish."""
    dp = Dispatcher(storage=MemoryStorage())

    @dp.message(CommandStart())
    async def start_handler(message: Message):
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(CateringSubscriber).where(CateringSubscriber.chat_id == str(message.chat.id))
            )
            sub = result.scalar_one_or_none()
            if sub:
                sub.is_active = True
            else:
                sub = CateringSubscriber(
                    restaurant_id=CATERING_RESTAURANT_ID,
                    chat_id=str(message.chat.id),
                    chat_type=message.chat.type,
                    title=message.chat.title or message.from_user.full_name,
                    is_active=True,
                )
                db.add(sub)
            await db.commit()

        chat_label = "guruh" if message.chat.type in ("group", "supergroup") else "shaxsiy"
        await message.answer(
            f"✅ <b>Catering bildirishnomalariga ulanildi!</b>\n\n"
            f"📬 Kunlik soat 20:00 da ertangi kun uchun qabul qilingan catering "
            f"buyurtmalari shu {chat_label} chatga yuboriladi.\n\n"
            f"Har buyurtma alohida xabar bo'ladi — ma'lumotlar va lokatsiya bir joyda.\n\n"
            f"📞 Qo'shimcha: <b>+998 98 000 06 04</b>"
        )

    @dp.message(Command("stop"))
    async def stop_handler(message: Message):
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(CateringSubscriber).where(CateringSubscriber.chat_id == str(message.chat.id))
            )
            sub = result.scalar_one_or_none()
            if sub:
                sub.is_active = False
                await db.commit()
                await message.answer("❌ Bildirishnomalar o'chirildi. Qaytadan yoqish uchun /start")
            else:
                await message.answer("Siz obunada emassiz. /start bosing.")

    @dp.message(Command("test"))
    async def test_handler(message: Message):
        await message.answer("⏳ Test uchun ertangi kun buyurtmalari yuborilmoqda...")
        await send_daily_orders(bot, target_chat_id=str(message.chat.id))

    @dp.my_chat_member()
    async def bot_added_to_group(event: ChatMemberUpdated):
        if event.new_chat_member.status in ("member", "administrator"):
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(CateringSubscriber).where(CateringSubscriber.chat_id == str(event.chat.id))
                )
                sub = result.scalar_one_or_none()
                if not sub:
                    sub = CateringSubscriber(
                        restaurant_id=CATERING_RESTAURANT_ID,
                        chat_id=str(event.chat.id),
                        chat_type=event.chat.type,
                        title=event.chat.title,
                        is_active=True,
                    )
                    db.add(sub)
                    await db.commit()

    return dp


# ── Buyurtmalarni yuborish ────────────────────────────

DELIVERY_LABELS = {
    "onsite": "🏠 Joyiga borib yopish",
    "pickup": "🛍 Saboy (olib ketish)",
    "delivery": "🚗 Dastavka",
}
GROUP_LABELS = {"somsa": "🥟 Somsa", "nan": "🍞 Non"}
PAY_LABELS = {"cash": "💵 Naqd", "card": "💳 Karta"}
TIME_LABELS = {"now": "hozir", "later": "buyurtma olganda"}


async def send_daily_orders(bot: Bot, target_chat_id: str = None):
    """Ertangi kun catering buyurtmalarini yuborish.

    target_chat_id berilsa — faqat shu chatga, aks holda barcha obunachilarga.
    """
    tomorrow = (datetime.now(UZ_TZ) + timedelta(days=1)).date().isoformat()

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Order).where(
                Order.restaurant_id == CATERING_RESTAURANT_ID,
                Order.order_kind == "catering",
                Order.schedule_date == tomorrow,
                Order.status != OrderStatus.cancelled,
            ).order_by(Order.schedule_time)
        )
        orders = result.scalars().all()

        if not orders:
            if target_chat_id:
                try:
                    await bot.send_message(target_chat_id, f"ℹ️ {tomorrow} sanasiga buyurtma yo'q.")
                except Exception:
                    pass
            return

        if target_chat_id:
            subs_ids = [target_chat_id]
        else:
            subs_result = await db.execute(
                select(CateringSubscriber).where(
                    CateringSubscriber.is_active == True,
                    CateringSubscriber.restaurant_id == CATERING_RESTAURANT_ID,
                )
            )
            subs = subs_result.scalars().all()
            subs_ids = [s.chat_id for s in subs]

        if not subs_ids:
            return

        for chat_id in subs_ids:
            await _send_orders_to_chat(bot, db, chat_id, orders, tomorrow)


async def _send_orders_to_chat(bot: Bot, db, chat_id: str, orders, date_str: str):
    try:
        await bot.send_message(
            chat_id,
            f"📅 <b>{date_str} — Catering buyurtmalari ({len(orders)} ta)</b>\n\n"
            f"Har bir buyurtma alohida yuboriladi. Ketma-ket ko'rib chiqing.",
        )
    except Exception as e:
        print(f"[catering_bot] header send error: {e}")
        return

    order_refs = []
    for idx, order in enumerate(orders, start=1):
        u_res = await db.execute(select(User).where(User.id == order.user_id))
        user = u_res.scalar_one_or_none()

        i_res = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
        items = i_res.scalars().all()
        items_text_parts = []
        for oi in items:
            p_res = await db.execute(select(Product).where(Product.id == oi.product_id))
            p = p_res.scalar_one_or_none()
            name = p.name_uz if p else f"#{oi.product_id}"
            items_text_parts.append(f"  • {name}: <b>{oi.quantity} ta</b>")
        items_text = "\n".join(items_text_parts) if items_text_parts else "—"

        group = "?"
        if items:
            p_res = await db.execute(select(Product).where(Product.id == items[0].product_id))
            first_p = p_res.scalar_one_or_none()
            if first_p and first_p.catering_group:
                group = first_p.catering_group

        if order.latitude and order.longitude:
            try:
                await bot.send_location(
                    chat_id,
                    latitude=float(order.latitude),
                    longitude=float(order.longitude),
                )
            except Exception as e:
                print(f"[catering_bot] location send error: {e}")

        total_quantity = sum(i.quantity for i in items)
        text = (
            f"🎉 <b>Buyurtma #{order.id}</b> ({idx}/{len(orders)})\n\n"
            f"👥 Guruh: {GROUP_LABELS.get(group, group)}\n"
            f"📦 Jami: <b>{total_quantity} ta</b>\n"
            f"{items_text}\n\n"
            f"⏰ Vaqt: <b>{order.schedule_time}</b>\n"
            f"🚗 Turi: {DELIVERY_LABELS.get(order.delivery_subtype, order.delivery_subtype)}\n"
        )
        if user:
            text += (
                f"👤 Mijoz: <b>{html.escape(user.full_name or '')}</b>\n"
                f"📞 Tel: <code>{html.escape(user.phone or '')}</code>\n"
            )
        if order.address:
            text += f"📍 Manzil: {html.escape(order.address)}\n"
        if order.total_price_usd:
            text += f"\n💰 Narx: <b>{order.total_price:,.0f} so'm</b> (${order.total_price_usd:.2f})\n"
        else:
            text += f"\n💰 Narx: <b>{order.total_price:,.0f} so'm</b>\n"
        text += (
            f"💳 To'lov: {PAY_LABELS.get(order.payment_method, '—')} "
            f"({TIME_LABELS.get(order.payment_timing, '—')})\n"
        )
        if order.comment:
            text += f"\n💬 Izoh: {html.escape(order.comment)}"

        try:
            await bot.send_message(chat_id, text)
            order_refs.append({
                "id": order.id, "time": order.schedule_time,
                "name": user.full_name if user else "Mijoz",
                "quantity": total_quantity, "group": group,
            })
        except Exception as e:
            print(f"[catering_bot] order send error: {e}")

    if order_refs:
        list_text = f"📋 <b>Ro'yxat — {date_str} ({len(order_refs)} buyurtma):</b>\n\n"
        for r in order_refs:
            list_text += (
                f"• {r['time']} — {GROUP_LABELS.get(r['group'], r['group'])} "
                f"{r['quantity']} ta — {r['name']} (#{r['id']})\n"
            )
        list_text += "\n<i>Har buyurtma yuqorida alohida xabarda ko'rsatilgan.</i>"
        try:
            await bot.send_message(chat_id, list_text)
        except Exception as e:
            print(f"[catering_bot] list send error: {e}")


# ── Scheduler ─────────────────────────────────────────

async def scheduler_loop(bot: Bot):
    """Soat 20:00 da ertangi kun buyurtmalarini yuborish."""
    while True:
        now = datetime.now(UZ_TZ)
        next_run = now.replace(hour=20, minute=0, second=0, microsecond=0)
        if now >= next_run:
            next_run += timedelta(days=1)
        wait_sec = (next_run - now).total_seconds()
        print(f"[catering_bot] Scheduler: next run at {next_run.isoformat()} (in {wait_sec/60:.0f} min)")
        await asyncio.sleep(wait_sec)
        try:
            await send_daily_orders(bot)
            print(f"[catering_bot] Daily send completed at {datetime.now(UZ_TZ).isoformat()}")
        except Exception as e:
            print(f"[catering_bot] Scheduler error: {e}")


async def main():
    bot_token = os.getenv("CATERING_BOT_TOKEN", "").strip()
    if not bot_token:
        raise SystemExit("CATERING_BOT_TOKEN .env faylida yo'q!")
    bot = Bot(token=bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher(bot)
    print(f"[catering_bot] Starting (restaurant_id={CATERING_RESTAURANT_ID})...")
    asyncio.create_task(scheduler_loop(bot))
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
