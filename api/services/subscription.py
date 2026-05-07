"""Subscription / Billing logikasi — tarif yangilash, freeze, grace, suspend.

Asosiy holatlar:
    active        → tarif amal qiladi, hammasi ishlaydi
    grace_period  → tarif tugagan, 10 kun davomida hali ham ishlaydi (ogohlantirish)
    suspended     → grace tugagan, hammasi 402 Payment Required (super-admin tashqari)

Upgrade variantlari:
    Variant A "Hozir o'tish" (immediate):
        - Joriy tarif qolgan kunlar `frozen_days` ga saqlanadi
        - frozen_until = now + 30 days (muddat)
        - Yangi tarif darhol boshlanadi, plan_expires_at = now + 30 days
        - 30 kun ichida orqaga qaytarish mumkin (frozen_days qo'llanadi)

    Variant B "Navbat bilan o'tish" (queued):
        - Yangi tarif uchun to'lov qilinadi (Payment.upgrade_type='queued')
        - next_plan_id, next_plan_starts_at = (joriy plan_expires_at) saqlanadi
        - Joriy tarif 30 kun ichida tugagach, scheduler avtomatik o'tkazadi

Daily check (scheduler 10:00):
    1. plan_expires_at < now va status='active' bo'lganlarni grace_period'ga
    2. grace_started_at + 10 days < now bo'lganlarni suspended ga
    3. frozen_until < now bo'lganlarning frozen_days = 0
    4. next_plan_starts_at <= now bo'lganlarni active'ga ko'chirish (queued apply)
    5. Tarif tugayotganlarga (3 va 1 kun qoldi) Telegram ogohlantirish
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.logging_config import log_critical
from database.models import Payment, Plan, Restaurant


# ── Konstantalar ─────────────────────────────────────────
GRACE_PERIOD_DAYS = 10
FROZEN_RETENTION_DAYS = 30
PLAN_PERIOD_DAYS = 30
WARNING_DAYS_BEFORE_EXPIRY = (3, 1)   # 3 kun va 1 kun oldin xabar

VALID_SUBSCRIPTION_STATUSES = ("active", "grace_period", "suspended")


# ── Yordamchi funksiyalar ───────────────────────────────

def _is_plan_active(rest: Restaurant, now: Optional[datetime] = None) -> bool:
    """Tarif hali amal qiladimi (muddati o'tmaganmi)."""
    if not rest.plan_expires_at:
        return False
    return rest.plan_expires_at > (now or datetime.utcnow())


def _days_left(rest: Restaurant, now: Optional[datetime] = None) -> int:
    """Tarif muddati oxirigacha kunlar (0 yoki manfiy bo'lsa tugagan)."""
    if not rest.plan_expires_at:
        return 0
    delta = rest.plan_expires_at - (now or datetime.utcnow())
    return max(0, delta.days + (1 if delta.seconds else 0))


# ── Variant A: hozir o'tish + freeze ─────────────────────

async def upgrade_immediate(
    db: AsyncSession,
    *,
    restaurant: Restaurant,
    new_plan: Plan,
    payment_id: Optional[int] = None,
) -> dict:
    """Hozirgi tarifni muzlatadi, yangi tarifni darhol boshlaydi.

    Logika:
        1. Joriy tarif qolgan kunlar = days_left(restaurant)
        2. frozen_days += days_left
        3. frozen_until = now + 30 days
        4. plan_id = new_plan.id
        5. plan_expires_at = now + 30 days
        6. subscription_status = 'active'

    Eski frozen_days mavjud bo'lsa — qo'shamiz (kumulyativ saqlanadi).
    """
    now = datetime.utcnow()
    qoldiq = _days_left(restaurant, now)

    if qoldiq > 0:
        restaurant.frozen_days = (restaurant.frozen_days or 0) + qoldiq
        restaurant.frozen_until = now + timedelta(days=FROZEN_RETENTION_DAYS)

    # Yangi tarif
    restaurant.plan_id = new_plan.id
    restaurant.plan_expires_at = now + timedelta(days=PLAN_PERIOD_DAYS)
    restaurant.subscription_status = "active"
    restaurant.grace_started_at = None

    # Eski queued upgrade'ni bekor qilish (mavjud bo'lsa)
    restaurant.next_plan_id = None
    restaurant.next_plan_starts_at = None

    # Payment yozuvini yangilash
    if payment_id:
        pay = (await db.execute(select(Payment).where(Payment.id == payment_id))).scalar_one_or_none()
        if pay:
            pay.upgrade_type = "immediate"
            pay.applied_at = now

    await db.commit()
    return {
        "type": "immediate",
        "frozen_days": restaurant.frozen_days,
        "frozen_until": restaurant.frozen_until.isoformat() if restaurant.frozen_until else None,
        "plan_id": restaurant.plan_id,
        "plan_expires_at": restaurant.plan_expires_at.isoformat(),
    }


# ── Variant B: navbat bilan o'tish ──────────────────────

async def upgrade_queued(
    db: AsyncSession,
    *,
    restaurant: Restaurant,
    new_plan: Plan,
    payment_id: Optional[int] = None,
) -> dict:
    """Yangi tarif uchun to'lov, lekin u faqat eski tarif tugashi bilan boshlanadi.

    Eski tarif tugagan bo'lsa (yoki yo'q bo'lsa), ushbu funksiya `upgrade_immediate`
    kabi ishlaydi (yangi tarif darhol boshlanadi). Bu UX sababli — mijoz
    "navbat" tanlasa ham, tarifi yo'q bo'lsa kutib turish noto'g'ri.
    """
    now = datetime.utcnow()
    if not _is_plan_active(restaurant, now):
        # Eski tarif tugagan → darhol qo'llanadi (queued mantiqi keraksiz)
        result = await upgrade_immediate(
            db, restaurant=restaurant, new_plan=new_plan, payment_id=payment_id,
        )
        result["type"] = "queued_applied_immediately"
        return result

    # Eski tarif hali amal qiladi — navbatga qo'yamiz
    restaurant.next_plan_id = new_plan.id
    restaurant.next_plan_starts_at = restaurant.plan_expires_at

    if payment_id:
        pay = (await db.execute(select(Payment).where(Payment.id == payment_id))).scalar_one_or_none()
        if pay:
            pay.upgrade_type = "queued"
            # applied_at NULL qoladi — scheduler keyinroq to'ldiradi

    await db.commit()
    return {
        "type": "queued",
        "next_plan_id": restaurant.next_plan_id,
        "next_plan_starts_at": restaurant.next_plan_starts_at.isoformat(),
        "current_plan_expires_at": restaurant.plan_expires_at.isoformat(),
    }


# ── Daily scheduler operatsiyalari ──────────────────────

async def enter_grace_period(
    db: AsyncSession, *, restaurant: Restaurant,
) -> bool:
    """Tarif muddati tugagan → grace_period.

    Faqat status 'active' va plan_expires_at < now bo'lganda chaqiriladi.
    """
    if restaurant.subscription_status != "active":
        return False
    if restaurant.plan_expires_at and restaurant.plan_expires_at > datetime.utcnow():
        return False  # Hali amal qiladi

    restaurant.subscription_status = "grace_period"
    restaurant.grace_started_at = datetime.utcnow()
    await db.commit()
    return True


async def suspend_restaurant(
    db: AsyncSession, *, restaurant: Restaurant,
) -> bool:
    """Grace muddati tugagan → suspended (barcha API/bot 402)."""
    if restaurant.subscription_status != "grace_period":
        return False
    if not restaurant.grace_started_at:
        return False
    grace_end = restaurant.grace_started_at + timedelta(days=GRACE_PERIOD_DAYS)
    if grace_end > datetime.utcnow():
        return False   # Hali grace ichida

    restaurant.subscription_status = "suspended"
    await db.commit()
    log_critical(
        "subscription", "Restaurant suspended (grace tugadi)",
        restaurant_id=restaurant.id, name=restaurant.name,
        grace_started_at=restaurant.grace_started_at.isoformat(),
    )
    return True


async def expire_frozen_days(
    db: AsyncSession, *, restaurant: Restaurant,
) -> bool:
    """frozen_until o'tgan bo'lsa, frozen_days = 0 qiladi (30 kun saqlanish muddati)."""
    if not restaurant.frozen_until:
        return False
    if restaurant.frozen_until > datetime.utcnow():
        return False

    if restaurant.frozen_days > 0:
        restaurant.frozen_days = 0
        restaurant.frozen_until = None
        await db.commit()
        return True
    return False


async def apply_queued_upgrade(
    db: AsyncSession, *, restaurant: Restaurant,
) -> Optional[dict]:
    """next_plan_starts_at vaqti yetganda navbatdagi tarifni faollashtirish."""
    if not restaurant.next_plan_id or not restaurant.next_plan_starts_at:
        return None
    if restaurant.next_plan_starts_at > datetime.utcnow():
        return None  # Hali vaqti emas

    new_plan = (await db.execute(
        select(Plan).where(Plan.id == restaurant.next_plan_id)
    )).scalar_one_or_none()
    if not new_plan:
        # Plan o'chirilgan — queue ni tozalaymiz
        restaurant.next_plan_id = None
        restaurant.next_plan_starts_at = None
        await db.commit()
        return None

    # Plan'ni faollashtirish
    now = datetime.utcnow()
    restaurant.plan_id = new_plan.id
    # Yangi tarif boshlangan vaqtdan 30 kun
    base = max(restaurant.plan_expires_at or now, now)
    restaurant.plan_expires_at = base + timedelta(days=PLAN_PERIOD_DAYS)
    restaurant.subscription_status = "active"
    restaurant.grace_started_at = None
    restaurant.next_plan_id = None
    restaurant.next_plan_starts_at = None

    # Queued payment ni belgilab qo'yamiz
    queued_pay = (await db.execute(
        select(Payment).where(
            Payment.restaurant_id == restaurant.id,
            Payment.plan_id == new_plan.id,
            Payment.upgrade_type == "queued",
            Payment.applied_at.is_(None),
        ).order_by(Payment.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if queued_pay:
        queued_pay.applied_at = now

    await db.commit()
    return {
        "applied_plan_id": new_plan.id,
        "plan_expires_at": restaurant.plan_expires_at.isoformat(),
    }


# ── Holatni hisoblash (GET /admin/billing/status uchun) ─

async def get_billing_status(
    db: AsyncSession, *, restaurant: Restaurant,
) -> dict:
    """Restoranning to'liq billing holati."""
    now = datetime.utcnow()
    current_plan = None
    if restaurant.plan_id:
        current_plan = (await db.execute(
            select(Plan).where(Plan.id == restaurant.plan_id)
        )).scalar_one_or_none()

    next_plan = None
    if restaurant.next_plan_id:
        next_plan = (await db.execute(
            select(Plan).where(Plan.id == restaurant.next_plan_id)
        )).scalar_one_or_none()

    days_left = _days_left(restaurant, now)
    grace_days_left = 0
    if restaurant.subscription_status == "grace_period" and restaurant.grace_started_at:
        used = (now - restaurant.grace_started_at).days
        grace_days_left = max(0, GRACE_PERIOD_DAYS - used)

    frozen_days_left = 0
    if restaurant.frozen_until and restaurant.frozen_until > now:
        delta = restaurant.frozen_until - now
        frozen_days_left = delta.days + (1 if delta.seconds else 0)

    return {
        "subscription_status": restaurant.subscription_status,
        "is_verified": bool(restaurant.is_verified),
        "current_plan": (
            {"id": current_plan.id, "slug": current_plan.slug, "name": current_plan.name}
            if current_plan else None
        ),
        "plan_expires_at": (
            restaurant.plan_expires_at.isoformat() if restaurant.plan_expires_at else None
        ),
        "days_left": days_left,
        "grace_days_left": grace_days_left,
        "frozen_days": int(restaurant.frozen_days or 0),
        "frozen_days_left_to_expire": frozen_days_left,
        "frozen_until": restaurant.frozen_until.isoformat() if restaurant.frozen_until else None,
        "next_plan": (
            {"id": next_plan.id, "slug": next_plan.slug, "name": next_plan.name}
            if next_plan else None
        ),
        "next_plan_starts_at": (
            restaurant.next_plan_starts_at.isoformat() if restaurant.next_plan_starts_at else None
        ),
    }


# ── Daily check (har kuni 10:00 da chaqiriladi) ─────────

async def run_daily_subscription_check(
    db: AsyncSession,
) -> dict:
    """Har kuni 10:00 da scheduler/cron tomonidan chaqiriladi.

    1. plan_expires_at < now → enter_grace_period
    2. grace_started_at + 10 days < now → suspend
    3. frozen_until < now → expire frozen_days
    4. next_plan_starts_at <= now → apply queued upgrade
    5. plan_expires_at - now in (3, 1) days → notify

    Qaytaradi: summary dict.
    """
    now = datetime.utcnow()
    summary = {
        "started_at": now.isoformat(),
        "graced": [],          # rid'lar grace'ga o'tdi
        "suspended": [],       # rid'lar suspended bo'ldi
        "frozen_expired": [],  # frozen_days 0 ga tushdi
        "queued_applied": [],  # navbatdagi tarif faollashdi
        "warnings_3d": [],     # 3 kun qolgani haqida xabar
        "warnings_1d": [],     # 1 kun qolgani haqida xabar
    }

    # Barcha aktiv restoranlarni olib chiqamiz (suspended emas)
    rows = (await db.execute(
        select(Restaurant).where(Restaurant.subscription_status != "suspended")
    )).scalars().all()

    for rest in rows:
        # 1. Tarif tugadi → grace
        if rest.subscription_status == "active":
            if rest.plan_expires_at and rest.plan_expires_at <= now:
                if await enter_grace_period(db, restaurant=rest):
                    summary["graced"].append(rest.id)

        # 2. Grace tugadi → suspend
        if rest.subscription_status == "grace_period":
            if await suspend_restaurant(db, restaurant=rest):
                summary["suspended"].append(rest.id)

        # 3. Frozen muddati tugadi
        if await expire_frozen_days(db, restaurant=rest):
            summary["frozen_expired"].append(rest.id)

        # 4. Navbatdagi tarifni qo'llash
        applied = await apply_queued_upgrade(db, restaurant=rest)
        if applied:
            summary["queued_applied"].append({"rid": rest.id, **applied})

        # 5. Ogohlantirish (3 va 1 kun qoldi)
        if rest.subscription_status == "active" and rest.plan_expires_at:
            d = _days_left(rest, now)
            if d == 3:
                summary["warnings_3d"].append(rest.id)
            elif d == 1:
                summary["warnings_1d"].append(rest.id)

    summary["finished_at"] = datetime.utcnow().isoformat()
    return summary
