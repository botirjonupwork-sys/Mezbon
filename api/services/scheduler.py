"""APScheduler wrapper — har kuni 10:00 da subscription check + boshqa task'lar.

FastAPI lifespan ichida ishga tushadi (`api/main.py:lifespan`):
    async with lifespan(app):
        scheduler.start()  # background
        yield
        scheduler.shutdown()

Cron alternative: `cron 0 10 * * * python -m scripts.check_subscriptions` ham
ishlatilishi mumkin (shu skript hali mavjud), lekin APScheduler bilan
qo'shimcha process kerak bo'lmaydi — uvicorn jarayoni ichida ishlaydi.

Multi-worker holatda ehtiyotkorlik: agar uvicorn `--workers 2` bilan
ishlasa, har worker'da scheduler ishlay boshlaydi va task 2 marta
chaqiriladi. Yechim:
   - Variant A: scheduler faqat birinchi worker'da yoqiladi (env flag bilan)
   - Variant B: APScheduler'ning DB-backed jobstore (PostgreSQL/Redis) bilan
     `coalesce=True, max_instances=1`
   - Variant C: scheduler alohida processda
Hozir Variant A ishlatamiz: `ENABLE_SCHEDULER=1` env bilan boshqariladi.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from api.logging_config import log_critical


log = logging.getLogger(__name__)

# Tashkent timezone — daily check 10:00 UZT da ishga tushadi
TZ = "Asia/Tashkent"

# Global scheduler instance — bittagina (singleton)
_scheduler: Optional[AsyncIOScheduler] = None

# Daily check serializatsiyasi: cron job (`max_instances=1`) va manual trigger
# (`trigger_daily_check_now`) bir vaqtda `charge_autopay`ni ishga tushira oladi —
# bu kartani ikki marta yechishi mumkin. Ikkala kirish nuqtasi shu lock'ni oladi.
# Lazy yaratamiz: Python 3.9'da asyncio.Lock() import paytida (loop'siz) xato beradi.
_DAILY_CHECK_LOCK: Optional[asyncio.Lock] = None


def _daily_check_lock() -> asyncio.Lock:
    global _DAILY_CHECK_LOCK
    if _DAILY_CHECK_LOCK is None:
        _DAILY_CHECK_LOCK = asyncio.Lock()
    return _DAILY_CHECK_LOCK


def is_enabled() -> bool:
    """ENABLE_SCHEDULER=1 bo'lsa scheduler ishlaydi.

    Default: production (DEBUG=False) da yoqilgan, dev'da o'chirilgan.

    Multi-worker uvicorn uchun: faqat 1 ta worker scheduler ni ishlatishi kerak
    (aks holda har worker bir xil cron job'ni chaqiradi). Buni quyidagicha
    boshqaramiz:
      - SCHEDULER_LOCK_FILE env (default: /tmp/restaurant_scheduler.lock)
        bo'lgan worker faqat scheduler'ni ishga tushiradi.
    """
    val = os.getenv("ENABLE_SCHEDULER", "").strip().lower()
    if val in {"0", "false", "no", "off"}:
        return False

    # DEBUG rejimda default o'chiq
    if val not in {"1", "true", "yes", "on"}:
        debug = os.getenv("DEBUG", "True").strip().lower()
        if debug in {"1", "true", "yes", "on"}:
            return False

    # Multi-worker: leader election fayl-lock orqali
    return _try_acquire_scheduler_lock()


def _try_acquire_scheduler_lock() -> bool:
    """Faqat birinchi worker lock olib, scheduler ishlatadi.

    fcntl flock — bir vaqtda 1 ta process'gagina yo'l ochiq.
    Boshqalar False qaytaradi (False → scheduler ishlamaydi).
    """
    import fcntl
    lock_path = os.getenv("SCHEDULER_LOCK_FILE", "/tmp/restaurant_scheduler.lock")
    try:
        fp = open(lock_path, "w")
        fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Lock'ni jarayon hayotida ushlab turamiz (close qilmaymiz)
        global _SCHEDULER_LOCK_FP
        _SCHEDULER_LOCK_FP = fp
        log.info("Scheduler lock acquired (%s) — this worker runs cron jobs", lock_path)
        return True
    except (BlockingIOError, OSError):
        log.info("Scheduler lock busy — another worker handles cron jobs (skipping)")
        return False
    except Exception as e:
        log.warning("Scheduler lock error: %s — falling back to enabled", e)
        return True


_SCHEDULER_LOCK_FP = None  # global lock file pointer


def get_scheduler() -> AsyncIOScheduler:
    """Global scheduler — bittagina yaratiladi."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(
            timezone=TZ,
            job_defaults={
                "coalesce": True,        # ko'p o'tkazib yuborilgan run'lar bittaga to'planadi
                "max_instances": 1,      # bitta task bir vaqtda 1 marta
                "misfire_grace_time": 600,   # 10 daq misfire ham hisobga olinadi
            },
        )
    return _scheduler


# ── Job: daily subscription check (10:00) ────────────────

async def _job_daily_subscription_check() -> None:
    """Har kuni 10:00 da: grace, suspend, frozen expire, queued upgrade, warning.

    Funksiya allaqachon `api/services/subscription.py:run_daily_subscription_check`
    da to'liq yozilgan — biz uni shu yerdan chaqiramiz va Telegram bilan
    notifier yuboramiz.
    """
    log.info("Daily subscription check started")
    lock = _daily_check_lock()
    if lock.locked():
        log.warning("Daily check allaqachon ishlamoqda — cron run o'tkazib yuborildi")
        return
    try:
        async with lock:
            await _run_daily_subscription_check_body()
    except Exception as e:
        log.exception("Daily subscription check xato: %s", e)


async def _run_daily_subscription_check_body() -> None:
    """Daily check'ning asl mazmuni (lock ichida chaqiriladi)."""
    try:
        from api.database import AsyncSessionLocal
        from api.services.notifier import (
            daily_summary_text, expiry_warning_text, grace_started_text,
            notify_platform_admin, notify_restaurant_owner, queued_applied_text,
            suspended_text,
        )
        from api.services.subscription import run_daily_subscription_check
        from sqlalchemy import select
        from database.models import Plan, Restaurant

        async with AsyncSessionLocal() as db:
            summary = await run_daily_subscription_check(db)
            log.info(f"Daily check summary: {summary}")

            # Notification — har holat uchun + platforma adminga umumiy hisobot
            rids = (
                list(summary.get("graced") or [])
                + list(summary.get("suspended") or [])
                + list(summary.get("warnings_3d") or [])
                + list(summary.get("warnings_1d") or [])
                + [q["rid"] for q in summary.get("queued_applied") or []]
            )
            if rids:
                rests = (await db.execute(
                    select(Restaurant).where(Restaurant.id.in_(set(rids)))
                )).scalars().all()
                by_id = {r.id: r for r in rests}

                # Grace boshlandi → platforma admin + restoran egasi
                for rid in summary.get("graced", []):
                    rest = by_id.get(rid)
                    if rest:
                        await notify_platform_admin(
                            f"🟡 Grace started: <b>{rest.name}</b> (rid={rid})"
                        )
                        await notify_restaurant_owner(rest, grace_started_text(rest))

                # 3 va 1 kun ogohlantirish → restoran egasiga
                for rid in summary.get("warnings_3d", []):
                    rest = by_id.get(rid)
                    if rest:
                        await notify_restaurant_owner(rest, expiry_warning_text(rest, 3))
                for rid in summary.get("warnings_1d", []):
                    rest = by_id.get(rid)
                    if rest:
                        await notify_restaurant_owner(rest, expiry_warning_text(rest, 1))

                # Suspended → platforma admin + restoran egasi
                for rid in summary.get("suspended", []):
                    rest = by_id.get(rid)
                    if rest:
                        await notify_platform_admin(
                            f"🔴 Suspended: <b>{rest.name}</b> (rid={rid})"
                        )
                        await notify_restaurant_owner(rest, suspended_text(rest))

            # Kunlik hisobot platforma adminga
            await notify_platform_admin(daily_summary_text(summary))
            log.info("Daily check + notifications complete")
    except Exception as e:
        log_critical(
            "scheduler", "Daily subscription check FAILED",
            error=str(e), error_type=type(e).__name__,
        )
        log.exception("Daily check failed")


# ── Job: auto-cancel stale unpaid orders (har 5 daqiqa) ──

# Qancha vaqtdan keyin pending order auto-cancel qilinadi
STALE_ORDER_MINUTES = int(os.getenv("STALE_ORDER_MINUTES", "30"))


async def _job_auto_cancel_stale_orders() -> None:
    """To'lanmagan eski pending orderlarni avtomatik bekor qilish.

    Mantiq: Order.payment_status='pending', payment_method='card',
    payment_timing='now' bo'lib STALE_ORDER_MINUTES daq oldin yaratilgan
    bo'lsa → status=cancelled, payment_status=cancelled.

    Bu mijoz to'lov widget'ini yopib qo'ygan, lekin Telegram successful_payment
    yubormagan keyslarni qamrab oladi.
    """
    from datetime import datetime, timedelta
    from api.database import AsyncSessionLocal
    from sqlalchemy import select, and_, or_
    from database.models import Order, OrderStatus

    threshold = datetime.utcnow() - timedelta(minutes=STALE_ORDER_MINUTES)
    log.info("Auto-cancel stale orders (older than %d min)", STALE_ORDER_MINUTES)

    try:
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                select(Order).where(
                    and_(
                        Order.payment_status == "pending",
                        Order.payment_timing == "now",
                        Order.payment_method.in_(("card", "telegram")),
                        Order.status == OrderStatus.pending,
                        Order.created_at < threshold,
                    )
                )
            )
            stale = res.scalars().all()
            if not stale:
                log.info("Auto-cancel: no stale orders")
                return

            for o in stale:
                o.status = OrderStatus.cancelled
                o.payment_status = "cancelled"
            await db.commit()
            log.info("Auto-cancel: %d stale order(s) cancelled", len(stale))

            # Platforma adminga ogohlantirish (juda ko'p bo'lsa)
            if len(stale) >= 5:
                try:
                    from api.services.notifier import notify_platform_admin
                    await notify_platform_admin(
                        f"⚠️ Auto-cancel: {len(stale)} ta to'lanmagan buyurtma bekor qilindi "
                        f"(timeout: {STALE_ORDER_MINUTES} daq)"
                    )
                except Exception:
                    pass
    except Exception as e:
        log_critical(
            "scheduler", "Auto-cancel stale orders FAILED",
            error=str(e), error_type=type(e).__name__,
        )


# ── Job: webhook anomaly alerter (Faza 7) — har 15 daqiqa ──

# Ko'p marta xabar qilmaslik uchun oxirgi alert vaqti (deduplication)
_last_anomaly_alert: dict[str, float] = {}
ANOMALY_ALERT_COOLDOWN_SECONDS = 900   # 15 daq


async def _job_webhook_anomaly_check() -> None:
    """Har 15 daqiqada webhook metrikalarini tekshiradi va anomaliyalar uchun alert."""
    import time as _t
    try:
        from api.services import webhook_metrics
        from api.services.notifier import notify_platform_admin

        anomalies = webhook_metrics.detect_anomalies(window_seconds=900)
        if not anomalies:
            return

        now = _t.time()
        new_alerts = []
        for an in anomalies:
            key = f"{an['endpoint']}:{an['type']}"
            last = _last_anomaly_alert.get(key, 0)
            if now - last >= ANOMALY_ALERT_COOLDOWN_SECONDS:
                _last_anomaly_alert[key] = now
                new_alerts.append(an)

        if not new_alerts:
            return

        lines = ["⚠️ <b>Webhook anomaliyalari (oxirgi 15 daq)</b>", ""]
        for an in new_alerts:
            if an["type"] == "high_failure_rate":
                lines.append(
                    f"❌ <b>{an['endpoint']}</b>: {an['value_pct']}% xatolik "
                    f"({an['samples']} so'rov, chegara: {an['threshold_pct']}%)"
                )
            elif an["type"] == "high_latency":
                lines.append(
                    f"🐢 <b>{an['endpoint']}</b>: P95={an['p95_ms']}ms "
                    f"(chegara: {an['threshold_ms']}ms)"
                )
        await notify_platform_admin("\n".join(lines))
        log.warning("Webhook anomaly alerts sent: %d", len(new_alerts))
    except Exception as e:
        log_critical(
            "scheduler", "Webhook anomaly check FAILED",
            error=str(e), error_type=type(e).__name__,
        )


# ── Job: oylik moliyaviy hisobot (Faza 7.4) — 1-kun 09:00 ──

async def _job_monthly_finance_report() -> None:
    """Har oy boshida (1-kun 09:00) o'tgan oy moliyaviy hisobotini yuboradi."""
    from datetime import datetime, timedelta
    try:
        from api.services.notifier import notify_platform_admin
        from api.database import AsyncSessionLocal
        from sqlalchemy import select, func
        from database.models import CommissionPayment, Payment, Order, Refund

        # O'tgan oy davri
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = today.replace(day=1)
        prev_month_end = month_start - timedelta(seconds=1)
        prev_month_start = prev_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        async with AsyncSessionLocal() as db:
            # Komissiya
            comm = (await db.execute(
                select(func.coalesce(func.sum(CommissionPayment.amount), 0)).where(
                    CommissionPayment.status == "confirmed",
                    CommissionPayment.paid_at >= prev_month_start,
                    CommissionPayment.paid_at < month_start,
                )
            )).scalar() or 0
            # SaaS
            saas = (await db.execute(
                select(func.coalesce(func.sum(Payment.amount_tiyin), 0)).where(
                    Payment.status == "success",
                    Payment.paid_at >= prev_month_start,
                    Payment.paid_at < month_start,
                )
            )).scalar() or 0
            # Buyurtmalar
            paid_orders = (await db.execute(
                select(func.count(Order.id)).where(
                    Order.created_at >= prev_month_start,
                    Order.created_at < month_start,
                    Order.payment_status.in_(["paid", "partial"]),
                )
            )).scalar() or 0
            # Refundlar
            refund_uzs = (await db.execute(
                select(func.coalesce(func.sum(Refund.amount_tiyin), 0)).where(
                    Refund.status == "success",
                    Refund.requested_at >= prev_month_start,
                    Refund.requested_at < month_start,
                )
            )).scalar() or 0

        period = f"{prev_month_start.date()} — {prev_month_end.date()}"
        text = (
            f"📊 <b>Oylik moliyaviy hisobot</b>\n"
            f"Davr: {period}\n\n"
            f"💵 Komissiya: <b>{float(comm):,.0f}</b> so'm\n"
            f"💎 SaaS tarif: <b>{(saas/100):,.0f}</b> so'm\n"
            f"📦 Paid buyurtmalar: <b>{paid_orders}</b>\n"
            f"💸 Refund: {(refund_uzs/100):,.0f} so'm\n"
            f"━━━━━━━━━━━━\n"
            f"💰 Jami daromad: <b>{(float(comm) + saas/100):,.0f}</b> so'm"
        )
        await notify_platform_admin(text)
        log.info("Monthly finance report sent for %s", period)
    except Exception as e:
        log_critical(
            "scheduler", "Monthly finance report FAILED",
            error=str(e), error_type=type(e).__name__,
        )


# ── Job: ertangi catering ro'yxati (Faza 9) — har kuni 20:00 ──

async def _job_catering_notifier_tomorrow() -> None:
    """Har kuni 20:00 (Asia/Tashkent) — ertangi catering buyurtmalari ro'yxatini
    har restoran o'rnatgan Telegram chat (kanal/guruh)'ga yuborish."""
    try:
        from api.database import AsyncSessionLocal
        from api.services.catering_notifier import send_tomorrow_catering_notifications

        async with AsyncSessionLocal() as db:
            stats = await send_tomorrow_catering_notifications(db)
        log.info("Catering notifier complete: %s", stats)
    except Exception as e:
        log_critical(
            "scheduler", "Catering notifier FAILED",
            error=str(e), error_type=type(e).__name__,
        )


# ── Job: Yandex balans monitoringi — har 30 daqiqa ─────

async def _job_yandex_balance_monitoring() -> None:
    """Yandex Delivery balanslarini tekshiradi va threshold bo'yicha ogohlantiradi."""
    try:
        from api.database import AsyncSessionLocal
        from api.services.yandex_balance import check_all_yandex_balances

        async with AsyncSessionLocal() as db:
            stats = await check_all_yandex_balances(db, notify=True)
        log.info("Yandex balance monitoring complete: %s", stats)
    except Exception as e:
        log_critical(
            "scheduler", "Yandex balance monitoring FAILED",
            error=str(e), error_type=type(e).__name__,
        )


# ── Job: Vaqtli Yandex zakazlarni yuborish — har 2 daqiqa ─────

async def _job_dispatch_scheduled_yandex() -> None:
    """To'langan, scheduled_for yaqinlashgan, hali claim yo'q zakazlarni Yandex'ga yuborish."""
    try:
        from api.database import AsyncSessionLocal
        from api.services.delivery import dispatch_due_scheduled_yandex_orders

        async with AsyncSessionLocal() as db:
            stats = await dispatch_due_scheduled_yandex_orders(db)
        if stats.get("checked"):
            log.info("Scheduled Yandex dispatch: %s", stats)
    except Exception as e:
        log_critical(
            "scheduler", "Scheduled Yandex dispatch FAILED",
            error=str(e), error_type=type(e).__name__,
        )


# ── Job: Yandex dastavka holatini poll qilish — har 2 daqiqa (webhook zaxirasi) ─────

async def _job_yandex_poll_active_claims() -> None:
    """Faol Yandex dastavka buyurtmalarining holatini davriy yangilab turadi.

    Webhook (push) — asosiy, darhol ishlaydigan yo'l. Bu poller esa ZAXIRA:
    agar Yandex ping'ni o'tkazib yuborsa yoki webhook sozlanmagan bo'lsa ham,
    status (kuryer topildi → keldi → yo'lda → yetkazildi) dinamik yangilanadi.
    Faqat tugamagan (delivered/cancelled emas) va claim_id bor, so'nggi 24 soatdagi
    orderlarni tekshiradi. Apply idempotent — takror xabar yuborilmaydi.
    """
    try:
        from datetime import datetime, timedelta

        from sqlalchemy import select

        from api.database import AsyncSessionLocal
        from api.routes.yandex_webhook import sync_order_status
        from database.models import Order, OrderStatus

        cutoff = datetime.utcnow() - timedelta(hours=24)
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                select(Order).where(
                    Order.yandex_claim_id.isnot(None),
                    Order.status.notin_([OrderStatus.delivered, OrderStatus.cancelled]),
                    Order.created_at >= cutoff,
                )
            )
            orders = res.scalars().all()
            checked = 0
            for o in orders:
                try:
                    await sync_order_status(db, o)
                    checked += 1
                except Exception as e:
                    log.warning("Yandex poll order #%s xato: %s", o.id, e)
        if orders:
            log.info("Yandex poll: %d ta faol dastavka holati tekshirildi", checked)
    except Exception as e:
        log_critical(
            "scheduler", "Yandex claim polling FAILED",
            error=str(e), error_type=type(e).__name__,
        )


# ── Public API ───────────────────────────────────────────

def start_scheduler() -> None:
    """FastAPI lifespan'ning startup qismida chaqiriladi."""
    if not is_enabled():
        log.info("Scheduler disabled (ENABLE_SCHEDULER=0 or DEBUG=True)")
        return

    sched = get_scheduler()
    if sched.running:
        return

    # Daily 10:00 (Asia/Tashkent) — subscription check
    sched.add_job(
        _job_daily_subscription_check,
        trigger=CronTrigger(hour=10, minute=0, timezone=TZ),
        id="daily_subscription_check",
        name="Daily subscription check (grace/suspend/frozen/warnings)",
        replace_existing=True,
    )

    # Har 5 daqiqada — eski to'lanmagan orderlarni auto-cancel (Faza 4.4)
    sched.add_job(
        _job_auto_cancel_stale_orders,
        trigger=CronTrigger(minute="*/5", timezone=TZ),
        id="auto_cancel_stale_orders",
        name=f"Auto-cancel stale pending orders (>{STALE_ORDER_MINUTES} min)",
        replace_existing=True,
    )

    # Har 15 daqiqada — webhook anomaliyalarini tekshirish (Faza 7.3)
    sched.add_job(
        _job_webhook_anomaly_check,
        trigger=CronTrigger(minute="*/15", timezone=TZ),
        id="webhook_anomaly_check",
        name="Webhook anomaly detection",
        replace_existing=True,
    )

    # Har oy 1-kun 09:00 — oylik moliyaviy hisobot (Faza 7.4)
    sched.add_job(
        _job_monthly_finance_report,
        trigger=CronTrigger(day=1, hour=9, minute=0, timezone=TZ),
        id="monthly_finance_report",
        name="Monthly finance report (1st of month, 09:00)",
        replace_existing=True,
    )

    # Har kuni 20:00 — ertangi catering ro'yxati (Faza 9)
    sched.add_job(
        _job_catering_notifier_tomorrow,
        trigger=CronTrigger(hour=20, minute=0, timezone=TZ),
        id="catering_notifier_tomorrow",
        name="Tomorrow's catering list (daily, 20:00)",
        replace_existing=True,
    )

    # Har 30 daqiqada — Yandex balans monitoringi (Faza 17)
    sched.add_job(
        _job_yandex_balance_monitoring,
        trigger=CronTrigger(minute="*/30", timezone=TZ),
        id="yandex_balance_monitoring",
        name="Yandex balance monitoring (every 30 minutes)",
        replace_existing=True,
    )

    # Har 2 daqiqada — Yandex dastavka holatini poll (webhook zaxirasi)
    sched.add_job(
        _job_yandex_poll_active_claims,
        trigger=CronTrigger(minute="*/2", timezone=TZ),
        id="yandex_poll_active_claims",
        name="Yandex delivery status poll (every 2 minutes)",
        replace_existing=True,
    )

    # Har 2 daqiqada — vaqtli Yandex zakazlarni yuborish
    sched.add_job(
        _job_dispatch_scheduled_yandex,
        trigger=CronTrigger(minute="*/2", timezone=TZ),
        id="yandex_dispatch_scheduled",
        name="Yandex scheduled order dispatch (every 2 minutes)",
        replace_existing=True,
    )

    sched.start()
    log.info(
        "Scheduler started — 8 jobs: subscription@10:00, auto-cancel/5min, "
        "anomaly/15min, monthly@1d-09:00, catering@20:00, yandex-balance/30min, "
        "yandex-poll/2min, yandex-scheduled/2min (TZ=%s)",
        TZ,
    )


def shutdown_scheduler() -> None:
    """Lifespan shutdown'da chaqiriladi."""
    global _scheduler
    if _scheduler is None or not _scheduler.running:
        return
    _scheduler.shutdown(wait=False)
    log.info("Scheduler stopped")


# ── Manual trigger (test/admin uchun) ────────────────────

async def trigger_daily_check_now() -> dict:
    """Daily check'ni darhol ishga tushirish (10:00 ni kutmasdan).

    Super-admin endpoint'idan chaqirish mumkin: `POST /super-admin/scheduler/run-now`.
    """
    from api.database import AsyncSessionLocal
    from api.services.subscription import run_daily_subscription_check
    lock = _daily_check_lock()
    if lock.locked():
        return {"skipped": "daily check already running"}
    async with lock:
        async with AsyncSessionLocal() as db:
            return await run_daily_subscription_check(db)
