"""Daily subscription check — har kuni soat 10:00 da ishlaydi.

Vazifalar:
    1. Tarif tugagan restoranlarni grace_period'ga o'tkazish
    2. 10 kun grace tugaganlarni suspended ga
    3. Frozen kunlari muddati tugaganlarni tozalash
    4. Navbatdagi tarifni faollashtirish
    5. Tarif tugayotganlarga (3 va 1 kun qoldi) Telegram ogohlantirish
    6. Platforma adminga kunlik hisobot

Cron sozlash:
    crontab -e:
    0 10 * * * cd /opt/restaurant && .venv/bin/python -m scripts.check_subscriptions >> logs/subscriptions.log 2>&1

Yoki APScheduler bilan FastAPI lifespan ichida (TODO).

Manual ishga tushirish (test uchun):
    python -m scripts.check_subscriptions
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime

# Loyiha ildizini sys.path ga
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import select

from api.database import AsyncSessionLocal
from api.services.notifier import (
    daily_summary_text, expiry_warning_text, grace_started_text,
    notify_platform_admin, notify_restaurant_admin, queued_applied_text,
    suspended_text,
)
from api.services.subscription import (
    _days_left, run_daily_subscription_check,
)
from database.models import Plan, Restaurant


# ── Asosiy daily oqim ────────────────────────────────────

async def main():
    print(f"[check_subscriptions] Started at {datetime.utcnow().isoformat()}")

    async with AsyncSessionLocal() as db:
        # 1. Subscription holatini yangilash (grace, suspend, frozen, queued apply)
        summary = await run_daily_subscription_check(db)
        print(f"[check_subscriptions] Summary: {summary}")

        # 2. Telegram ogohlantirishlar (har holat uchun)
        await _send_notifications(db, summary)

        # 3. Platforma adminga kunlik hisobot
        admin_text = daily_summary_text(summary)
        await notify_platform_admin(admin_text)
        print(f"[check_subscriptions] Platform admin notified")

    print(f"[check_subscriptions] Finished at {datetime.utcnow().isoformat()}")


async def _send_notifications(db, summary: dict):
    """Har bir o'zgargan restoranga shaxsiy Telegram xabari."""
    rids = (
        list(summary.get("graced") or [])
        + list(summary.get("suspended") or [])
        + list(summary.get("warnings_3d") or [])
        + list(summary.get("warnings_1d") or [])
        + [q["rid"] for q in summary.get("queued_applied") or []]
    )
    if not rids:
        return

    # Restoranlar batchda olib chiqamiz
    rests = (await db.execute(
        select(Restaurant).where(Restaurant.id.in_(set(rids)))
    )).scalars().all()
    by_id = {r.id: r for r in rests}

    # 1. Grace boshlandi
    for rid in summary.get("graced", []):
        rest = by_id.get(rid)
        if not rest:
            continue
        text = grace_started_text(rest)
        await _notify_one(rest, text)
        # Platforma admin ham bilsin
        await notify_platform_admin(f"🟡 Grace started: <b>{rest.name}</b> (rid={rid})")

    # 2. Suspended
    for rid in summary.get("suspended", []):
        rest = by_id.get(rid)
        if not rest:
            continue
        text = suspended_text(rest)
        await _notify_one(rest, text)
        await notify_platform_admin(f"🔴 Suspended: <b>{rest.name}</b> (rid={rid})")

    # 3. Queued upgrade qo'llandi
    for q in summary.get("queued_applied", []):
        rest = by_id.get(q["rid"])
        if not rest:
            continue
        plan = (await db.execute(
            select(Plan).where(Plan.id == q["applied_plan_id"])
        )).scalar_one_or_none()
        if plan:
            await _notify_one(rest, queued_applied_text(rest, plan.name))

    # 4. Ogohlantirishlar (3 va 1 kun)
    for rid in summary.get("warnings_3d", []):
        rest = by_id.get(rid)
        if rest:
            await _notify_one(rest, expiry_warning_text(rest, 3))
    for rid in summary.get("warnings_1d", []):
        rest = by_id.get(rid)
        if rest:
            await _notify_one(rest, expiry_warning_text(rest, 1))


async def _notify_one(rest: Restaurant, text: str) -> None:
    """Restoran admin'iga Telegram xabar yuborish (sokin fail).

    Hozircha admin chat ID maydoni Restaurant modelida yo'q — TODO:
    `admin_telegram_chat_id` qo'shish va deeplinking flow.
    """
    # Bot tokeni mavjud bo'lsa, restoranning o'z bot orqali yuboramiz
    # (admin chat ID hali yo'q — kelajakda)
    admin_chat = getattr(rest, "admin_telegram_chat_id", None)
    if rest.bot_token and admin_chat:
        await notify_restaurant_admin(
            restaurant_bot_token=rest.bot_token,
            admin_chat_id=admin_chat,
            text=text,
        )


if __name__ == "__main__":
    asyncio.run(main())
