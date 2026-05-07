"""Catering notifier — har kuni 20:00 ertangi catering buyurtmalarini xabar qiladi.

Har restoran admin Settings'da `catering_notifier_chat_id` ni o'rnatgan bo'lsa
(kanal/guruh ID), shu chatga yuboriladi. Yagona bot tokeni env'da:
`CATERING_NOTIFIER_BOT_TOKEN`.

Cron: APScheduler orqali har kuni 20:00 (Asia/Tashkent).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Order, OrderStatus, Restaurant, User


log = logging.getLogger(__name__)

WEEKDAYS_UZ = {
    0: "Dushanba", 1: "Seshanba", 2: "Chorshanba", 3: "Payshanba",
    4: "Juma", 5: "Shanba", 6: "Yakshanba",
}

SUBTYPE_LABEL = {
    "onsite":   "🏠 Joyiga borib yopish",
    "pickup":   "🛍 Olib ketish",
    "delivery": "🚗 Dastavka",
}


def _format_uzs(v: float) -> str:
    return f"{int(v):,}".replace(",", " ")


async def _send_telegram(token: str, chat_id: str, text: str) -> bool:
    """Telegram'ga xabar yuborish (HTML formatida, web preview o'chirilgan)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
        if r.status_code == 200:
            return True
        log.warning("Telegram send failed: HTTP %d, body: %s", r.status_code, r.text[:300])
        return False
    except Exception as e:
        log.warning("Telegram send exception: %s", e)
        return False


def _format_orders_message(date: datetime, orders: list) -> str:
    """Buyurtmalar ro'yxatini formatlash."""
    weekday = WEEKDAYS_UZ[date.weekday()]
    title = f"📅 <b>{date.strftime('%d.%m.%Y')} ({weekday}) catering buyurtmalari</b>"

    if not orders:
        return f"{title}\n\n<i>Bu kunda buyurtma yo'q.</i>"

    # Vaqt bo'yicha tartiblash (schedule_time yoki event_date)
    def sort_key(o):
        return (o.schedule_time or "00:00", o.id)

    orders_sorted = sorted(orders, key=sort_key)
    lines = [title, ""]

    for i, o in enumerate(orders_sorted, 1):
        time_part = o.schedule_time or "—"
        # Service turi
        subtype = SUBTYPE_LABEL.get(o.delivery_subtype or "", o.delivery_subtype or "—")
        # Mahsulotlar soni (items_count)
        item_count = sum(it.quantity for it in (o.items or [])) if o.items else 0

        lines.append(f"<b>{i}. {time_part}</b> — Buyurtma #{o.id}")
        lines.append(f"   {subtype} · {item_count} ta · {_format_uzs(o.total_price or 0)} so'm")

        if o.user:
            lines.append(f"   👤 {o.user.full_name or '—'}")
            if o.user.phone:
                lines.append(f"   📞 {o.user.phone}")

        if o.address:
            addr_short = (o.address[:80] + "…") if len(o.address) > 80 else o.address
            lines.append(f"   📍 {addr_short}")

        if o.comment:
            comment_short = (o.comment[:100] + "…") if len(o.comment) > 100 else o.comment
            lines.append(f"   💬 {comment_short}")

        lines.append("")

    lines.append(f"━━━━━━━━━━━━")
    lines.append(f"Jami: <b>{len(orders_sorted)} ta buyurtma</b>")
    return "\n".join(lines)


async def send_tomorrow_catering_notifications(db: AsyncSession) -> dict:
    """Asosiy funksiya — har restoran uchun ertangi catering ro'yxatini yuborish.

    Returns: {sent: int, skipped: int, errors: int, restaurants: int}
    """
    bot_token = (os.getenv("CATERING_NOTIFIER_BOT_TOKEN") or "").strip()
    if not bot_token:
        log.warning("CATERING_NOTIFIER_BOT_TOKEN env'da o'rnatilmagan — skip")
        return {"sent": 0, "skipped": 0, "errors": 0, "restaurants": 0, "no_token": True}

    # Ertangi sana (Tashkent timezone)
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Asia/Tashkent")
    tomorrow = (datetime.now(tz) + timedelta(days=1)).date()
    tomorrow_str = tomorrow.isoformat()

    log.info("Catering notifier: ertangi sana = %s", tomorrow_str)

    # Notifier sozlangan restoranlarni topish
    rests_q = await db.execute(
        select(Restaurant).where(
            Restaurant.catering_notifier_chat_id.isnot(None),
            Restaurant.catering_notifier_chat_id != "",
        )
    )
    rests = rests_q.scalars().all()
    log.info("Catering notifier: %d ta restoran sozlangan", len(rests))

    stats = {"sent": 0, "skipped": 0, "errors": 0, "restaurants": len(rests)}

    for rest in rests:
        # Ertangi catering buyurtmalari (bekor qilinmagan)
        from sqlalchemy.orm import selectinload
        orders_q = await db.execute(
            select(Order)
            .options(selectinload(Order.items), selectinload(Order.user))
            .where(
                Order.restaurant_id == rest.id,
                Order.order_kind == "catering",
                Order.status != OrderStatus.cancelled,
                Order.schedule_date == tomorrow_str,
            )
            .order_by(Order.schedule_time)
        )
        orders = orders_q.scalars().all()

        text = _format_orders_message(datetime.combine(tomorrow, datetime.min.time()), list(orders))

        ok = await _send_telegram(bot_token, rest.catering_notifier_chat_id, text)
        if ok:
            stats["sent"] += 1
            log.info("Sent for restaurant #%d (%s) — %d orders", rest.id, rest.name, len(orders))
        else:
            stats["errors"] += 1
            log.error("Failed for restaurant #%d (%s)", rest.id, rest.name)

    return stats
