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


def service_block_state(rest: Restaurant) -> dict:
    """Bot/mijoz uchun xizmat holati — yagona manba (info endpoint + bot middleware).

    blocked=True bo'lsa bot xizmat ko'rsatmasligi kerak:
      * status == 'blocked'            → super-admin qo'lda bloklagan (darhol)
      * subscription_status=='suspended' → tarif + 10 kun grace tugagan
    'active' va 'grace_period' → blocked EMAS (grace ichida bot ishlaydi, lekin
    egasiga ogohlantirish boradi).

    Qaytaradi: {"blocked": bool, "reason": str|None, "message": str}
    """
    status = (getattr(rest, "status", None) or "active").lower()
    sub = (getattr(rest, "subscription_status", None) or "active").lower()
    if status == "blocked":
        reason = "admin_block"
    elif sub == "suspended":
        reason = "suspended"
    else:
        return {"blocked": False, "reason": None, "message": ""}

    phone = (getattr(rest, "phone", None) or "").strip()
    msg = (
        f"🔴 <b>{rest.name}</b> hozircha xizmat ko'rsatmayapti.\n"
        "Iltimos keyinroq qayta urinib ko'ring."
    )
    if phone:
        msg += f"\n\n📞 Aloqa: {phone}"
    return {"blocked": True, "reason": reason, "message": msg}


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


# ── Avtomatik undirish (Payme Subscribe) ───────────────

# Payme receipt holati: 4 = to'langan (sandbox'da tasdiqlanadi)
PAYME_RECEIPT_PAID = 4


async def charge_autopay(db: AsyncSession, restaurant: Restaurant) -> Optional[dict]:
    """Restoran obunasini saqlangan karta tokeni bilan avtomatik undirish.

    Faqat scheduler chaqiradi (tarif tugayotgan yoki grace'dagi, autopay yoqilgan restoranlar).
    Qaytaradi:
        None        — undirishga shart yo'q (karta yo'q / bepul tarif / yaqinda undirilgan)
        {"ok": True}  — muvaffaqiyatli, tarif uzaytirildi
        {"ok": False, "error": ...} — undirish muvaffaqiyatsiz
    """
    from api.services import payme_subscribe as ps
    from api.services.billing import (
        uzs_to_tiyin, _gen_merchant_trans_id, mark_payment_success, mark_payment_failed,
    )
    from database.models import PaymeCard

    if not restaurant.autopay_enabled or not ps.is_configured():
        return None

    card = (await db.execute(
        select(PaymeCard).where(
            PaymeCard.restaurant_id == restaurant.id,
            PaymeCard.is_active == True,   # noqa: E712
            PaymeCard.verified == True,    # noqa: E712
        )
    )).scalar_one_or_none()
    if not card:
        return None

    # To'lanadigan tarif = joriy tarif
    plan = None
    if restaurant.plan_id:
        plan = (await db.execute(select(Plan).where(Plan.id == restaurant.plan_id))).scalar_one_or_none()
    if not plan or not plan.monthly_price or plan.monthly_price <= 0:
        return None  # bepul tarif — undirish shart emas

    # Idempotency: oxirgi 1 kunda HAR QANDAY muvaffaqiyatli to'lov bo'lgan bo'lsa —
    # qayta undirmaymiz. (upgrade_type'ga tayanmaymiz: mark_payment_success uni
    # 'immediate'ga o'zgartiradi. Asosiy gate — "tugayotgan/grace" trigeri.)
    recent = (await db.execute(
        select(Payment).where(
            Payment.restaurant_id == restaurant.id,
            Payment.status == "success",
            Payment.paid_at >= datetime.utcnow() - timedelta(days=1),
        )
    )).scalar_one_or_none()
    if recent:
        return None

    # ── Rekonsiliatsiya ────────────────────────────────────────────────
    # Oldingi run'da receipts.pay javobi tarmoq xatosi tufayli yo'qolgan bo'lishi
    # mumkin (karta YECHILGAN, lekin biz buni bilmaymiz). Bunday holatda Payment
    # 'pending' + external_id (receipt_id) saqlangan holda qoladi. Yangi chek
    # yaratishdan OLDIN shu chek holatini tekshiramiz — aks holda ikki marta yechamiz.
    stale = (await db.execute(
        select(Payment).where(
            Payment.restaurant_id == restaurant.id,
            Payment.status == "pending",
            Payment.provider == "payme",
            Payment.upgrade_type == "renewal",
            Payment.external_id.isnot(None),
            Payment.created_at >= datetime.utcnow() - timedelta(days=3),
        ).order_by(Payment.created_at.desc())
    )).scalars().first()
    if stale:
        try:
            rc = await ps.receipts_check(stale.external_id)
        except ps.PaymeSubscribeError as e:
            # Holat hali ham noaniq — bu run'da undirmaymiz (keyingi run qayta tekshiradi).
            log_critical(
                "payment", "Autopay rekonsiliatsiya muvaffaqiyatsiz — undirish kechiktirildi",
                restaurant_id=restaurant.id, error=e.message,
            )
            return {"ok": False, "error": f"reconcile pending: {e.message}"}
        if int(rc.get("state", 0)) == PAYME_RECEIPT_PAID:
            # Avvalgi to'lov aslida o'tgan — tarifni uzaytirib, qayta undirmaymiz.
            await mark_payment_success(stale, external_id=stale.external_id, db=db)
            return {"ok": True, "reconciled": True}
        # Chek to'lanmagan — eski pending'ni yopamiz va odatdagidek davom etamiz.
        await mark_payment_failed(stale, "Autopay: rekonsiliatsiya — chek to'lanmagan", db)

    amount_tiyin = uzs_to_tiyin(plan.monthly_price)
    merchant_trans_id = _gen_merchant_trans_id(restaurant.id, plan.id)
    payment = Payment(
        restaurant_id=restaurant.id,
        plan_id=plan.id,
        amount_tiyin=amount_tiyin,
        status="pending",
        provider="payme",
        merchant_trans_id=merchant_trans_id,
        upgrade_type="renewal",
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)

    # 1-bosqich: chek yaratish. Bu yerdagi xato xavfsiz (hali pul yechilmagan).
    try:
        token = ps.decrypt_token(card.token_enc)
        receipt = await ps.receipts_create(
            amount_tiyin,
            account={"merchant_trans_id": merchant_trans_id},
            detail=None,
        )
        receipt_id = receipt.get("_id")
        if not receipt_id:
            raise ps.PaymeSubscribeError(-1, "receipt _id qaytmadi")
        # receipt_id ni DARHOL saqlaymiz — receipts.pay javobi yo'qolsa ham
        # keyingi run yuqoridagi rekonsiliatsiya orqali shu chekni tekshira oladi.
        payment.external_id = str(receipt_id)
        await db.commit()
    except ps.PaymeSubscribeError as e:
        await mark_payment_failed(payment, f"Autopay: {e.message}", db)
        log_critical(
            "payment", "Autopay chek yaratish muvaffaqiyatsiz",
            restaurant_id=restaurant.id, plan_id=plan.id, error=e.message,
        )
        await _notify_autopay_failed(restaurant, plan, e.message)
        return {"ok": False, "error": e.message}

    # 2-bosqich: to'lash. Bu yerdagi tarmoq xatosi NOANIQ — karta yechilgan
    # bo'lishi mumkin. Shu sabab failed qilmaymiz, balki holatni tekshiramiz.
    try:
        paid = await ps.receipts_pay(receipt_id, token)
    except ps.PaymeSubscribeError as e:
        try:
            rc = await ps.receipts_check(receipt_id)
            if int(rc.get("state", 0)) == PAYME_RECEIPT_PAID:
                await mark_payment_success(payment, external_id=str(receipt_id), db=db)
                return {"ok": True}
        except ps.PaymeSubscribeError:
            pass
        # Hali noaniq — Payment 'pending' (external_id bilan) holda QOLADI;
        # keyingi run rekonsiliatsiya qiladi. FAILED qilmaymiz (qayta yechmaslik uchun).
        log_critical(
            "payment", "Autopay to'lov javobi noaniq — pending qoldirildi",
            restaurant_id=restaurant.id, plan_id=plan.id, error=e.message,
        )
        await _notify_autopay_failed(restaurant, plan, f"to'lov holati noaniq: {e.message}")
        return {"ok": False, "error": f"ambiguous: {e.message}"}

    if int(paid.get("state", 0)) != PAYME_RECEIPT_PAID:
        reason = f"receipt state={paid.get('state')}"
        await mark_payment_failed(payment, f"Autopay: {reason}", db)
        await _notify_autopay_failed(restaurant, plan, reason)
        return {"ok": False, "error": reason}

    # Muvaffaqiyat — mavjud billing oqimi tarifni uzaytiradi + platforma adminga xabar
    await mark_payment_success(payment, external_id=str(receipt_id), db=db)
    return {"ok": True}


async def _notify_autopay_failed(restaurant: Restaurant, plan: Plan, reason: str) -> None:
    """Avtomatik undirish muvaffaqiyatsizligi — platforma adminga Telegram xabar."""
    try:
        from api.services.notifier import notify_platform_admin
        await notify_platform_admin(
            f"⚠️ Autopay muvaffaqiyatsiz\n"
            f"Restoran: {restaurant.name} (#{restaurant.id})\n"
            f"Tarif: {plan.name}\n"
            f"Sabab: {reason}\n\n"
            f"Restoran grace_period'ga o'tadi va keyingi kunlar qayta urinib ko'riladi."
        )
    except Exception:
        pass


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
        "autopay_charged": [], # avtomatik undirildi → tarif uzaytirildi
        "autopay_failed": [],  # avtomatik undirish muvaffaqiyatsiz
    }

    # Barcha aktiv restoranlarni olib chiqamiz (suspended emas)
    rows = (await db.execute(
        select(Restaurant).where(Restaurant.subscription_status != "suspended")
    )).scalars().all()

    for rest in rows:
        # 0. Avtomatik undirish — tarif tugayotgan (≤1 kun) yoki grace'dagi, autopay yoqilgan.
        #    Muvaffaqiyatли bo'lsa tarif uzayadi (status active qoladi) → grace/suspend ishlamaydi.
        if rest.autopay_enabled:
            expiring = bool(rest.plan_expires_at and rest.plan_expires_at <= now + timedelta(days=1))
            in_grace = rest.subscription_status == "grace_period"
            if expiring or in_grace:
                charged = await charge_autopay(db, rest)
                if charged and charged.get("ok"):
                    summary["autopay_charged"].append(rest.id)
                    await db.refresh(rest)   # plan_expires_at / status yangilandi
                elif charged:
                    summary["autopay_failed"].append(rest.id)

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
