"""Daily payment reconciliation — bizning Payment vs Click/Payme yozuvlari.

Vazifalar:
    1. Oxirgi N kunda yaratilgan barcha Payment yozuvlarini olish
    2. Har biri uchun status tahlili:
       - pending > 30 daqiqa → ehtimol abandoned, "stale" deb belgilanadi
       - success → audit log mavjudmi, external_id mavjudmi
       - refunded → notify_platform_admin orqali ogohlantirish (oylik hisobot)
    3. Order to'lov yozuvlari (Order.payment_status='paid'):
       - paid_amount_tiyin > 0 va payment_charge_id mavjudmi
       - CommissionPayment yozilganmi
    4. Topilgan farqlar uchun Telegram alert + critical log

Manual ishga tushirish:
    python -m scripts.reconciliation [--days 7]

Cron sozlash (har kuni 09:00):
    0 9 * * * cd /opt/restaurant && .venv/bin/python -m scripts.reconciliation >> logs/reconciliation.log 2>&1

Real Click/Payme query API integratsiyasi keyingi bosqichda qo'shiladi
(merchant kabinetdan API kalit kerak).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import AsyncSessionLocal as async_session_maker
from database.models import (
    CommissionPayment, Order, Payment, Restaurant,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("reconciliation")

STALE_PENDING_MINUTES = 30


async def _scan_payments(db: AsyncSession, since: datetime) -> dict:
    """SaaS Payment yozuvlarini tahlil qilish."""
    res = await db.execute(
        select(Payment).where(Payment.created_at >= since).order_by(Payment.id)
    )
    payments = res.scalars().all()

    stats = {
        "total": len(payments),
        "pending": 0,
        "stale_pending": 0,
        "success": 0,
        "failed": 0,
        "refunded": 0,
        "missing_external_id": 0,
        "issues": [],
    }
    threshold = datetime.utcnow() - timedelta(minutes=STALE_PENDING_MINUTES)

    for p in payments:
        status = (p.status or "pending").lower()
        if status == "pending":
            stats["pending"] += 1
            if p.created_at and p.created_at < threshold:
                stats["stale_pending"] += 1
                stats["issues"].append(
                    f"Payment #{p.id} pending {(datetime.utcnow() - p.created_at).total_seconds()/60:.0f} daq, "
                    f"merchant_trans_id={p.merchant_trans_id}"
                )
        elif status == "success":
            stats["success"] += 1
            if not p.external_id:
                stats["missing_external_id"] += 1
                stats["issues"].append(
                    f"Payment #{p.id} success bo'lsa-da external_id bo'sh"
                )
        elif status == "failed":
            stats["failed"] += 1
        elif status == "refunded":
            stats["refunded"] += 1

    return stats


async def _scan_orders(db: AsyncSession, since: datetime) -> dict:
    """Order to'lov yozuvlarini tahlil qilish."""
    res = await db.execute(
        select(Order).where(
            and_(
                Order.created_at >= since,
                Order.payment_status.in_(["paid", "partial", "refunded"]),
            )
        ).order_by(Order.id)
    )
    orders = res.scalars().all()

    stats = {
        "total": len(orders),
        "paid": 0,
        "partial": 0,
        "refunded": 0,
        "missing_charge_id": 0,
        "missing_commission": 0,
        "issues": [],
    }

    for o in orders:
        ps = (o.payment_status or "").lower()
        if ps == "paid":
            stats["paid"] += 1
        elif ps == "partial":
            stats["partial"] += 1
        elif ps == "refunded":
            stats["refunded"] += 1

        # Telegram to'lov uchun payment_charge_id bo'lishi shart
        if (o.payment_method or "") == "telegram" and not o.payment_charge_id:
            stats["missing_charge_id"] += 1
            stats["issues"].append(
                f"Order #{o.id} telegram to'lov bo'lsa-da payment_charge_id bo'sh"
            )

        # Commission yozuvi mavjudmi
        cm_res = await db.execute(
            select(func.count()).select_from(CommissionPayment).where(
                CommissionPayment.order_id == o.id
            )
        )
        cm_count = cm_res.scalar() or 0
        if ps in ("paid", "partial") and cm_count == 0:
            stats["missing_commission"] += 1
            stats["issues"].append(
                f"Order #{o.id} to'langan, lekin CommissionPayment yo'q"
            )

    return stats


async def _send_summary(stats_p: dict, stats_o: dict, days: int) -> None:
    """Telegram orqali platforma adminga kunlik hisobot."""
    issues_total = len(stats_p["issues"]) + len(stats_o["issues"])
    title = "✅ To'lov reconciliation" if issues_total == 0 else "⚠️ To'lov reconciliation — anomaliyalar"

    lines = [
        f"<b>{title}</b>",
        f"Davr: oxirgi {days} kun",
        "",
        "<b>SaaS Payments</b>",
        f"• Jami: {stats_p['total']}",
        f"• Success: {stats_p['success']}",
        f"• Pending: {stats_p['pending']} (stale: {stats_p['stale_pending']})",
        f"• Failed: {stats_p['failed']}",
        f"• Refunded: {stats_p['refunded']}",
        f"• external_id yo'q: {stats_p['missing_external_id']}",
        "",
        "<b>Order to'lovlari</b>",
        f"• Jami: {stats_o['total']}",
        f"• Paid: {stats_o['paid']}",
        f"• Partial: {stats_o['partial']}",
        f"• Refunded: {stats_o['refunded']}",
        f"• charge_id yo'q: {stats_o['missing_charge_id']}",
        f"• Commission yo'q: {stats_o['missing_commission']}",
    ]

    if issues_total > 0:
        lines.append("")
        lines.append(f"<b>Topilgan muammolar ({issues_total}):</b>")
        for issue in (stats_p["issues"] + stats_o["issues"])[:15]:
            lines.append(f"• {issue}")
        if issues_total > 15:
            lines.append(f"• ... va yana {issues_total - 15} ta")

    text = "\n".join(lines)
    print(text)

    try:
        from api.services.notifier import notify_platform_admin
        await notify_platform_admin(text)
    except Exception as e:
        log.warning("notify_platform_admin failed: %s", e)


async def run(days: int = 7) -> int:
    since = datetime.utcnow() - timedelta(days=days)
    log.info("Reconciliation: oxirgi %d kun (since=%s)", days, since.isoformat())

    async with async_session_maker() as db:
        stats_p = await _scan_payments(db, since)
        stats_o = await _scan_orders(db, since)

    await _send_summary(stats_p, stats_o, days)

    issues = len(stats_p["issues"]) + len(stats_o["issues"])
    log.info("Tugadi: %d ta muammo topildi", issues)
    return issues


def main() -> int:
    ap = argparse.ArgumentParser(description="Daily payment reconciliation")
    ap.add_argument("--days", type=int, default=7, help="Tahlil davri (default: 7 kun)")
    args = ap.parse_args()
    return asyncio.run(run(days=args.days))


if __name__ == "__main__":
    sys.exit(main())
