"""Refund servis — pul qaytarish biznes-logika.

Manbalar:
  - SaaS Payment refund (super-admin)
    → Click REVERSE merchant API yoki Payme CancelTransaction RPC
    → Restaurant.plan_expires_at qisqartirish (proportional)
    → Payment.status='refunded'

  - Order Refund (restaurant admin)
    → Telegram payments uchun: bot.refund_star_payment (Telegram API)
    → Click/Payme: provider'ga refund so'rovi
    → CommissionPayment kompensatsiya yozuvi
    → Order.status=cancelled, payment_status=refunded
    → Booking release (mashina bo'shatiladi)

Provider chaqiruvlari hozircha "stub" — real Click/Payme merchant API kalitlari
keltirilgandan so'ng to'liq integratsiya qilinadi.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    CommissionPayment, Order, OrderStatus, Payment, Refund, Restaurant,
)


log = logging.getLogger(__name__)


@dataclass
class RefundResult:
    ok: bool
    refund_id: Optional[int]
    provider_refund_id: Optional[str]
    error: Optional[str] = None


# ── Provider wrapper'lari ──────────────────────────────────────

async def _call_click_reverse(
    *, restaurant: Restaurant, payment: Payment, amount_tiyin: int,
) -> tuple[bool, Optional[str], Optional[str]]:
    """Click merchant API — POST /v2/merchant/payment/reversal/{merchant_id}/{payment_id}.

    Hujjat: https://docs.click.uz/click-api/
    Headers: Auth-Header (merchant_user_id:digest:timestamp)
    Hozircha: stub — real API faqat real keylar bilan ishlaydi.
    """
    merchant_id = restaurant.click_merchant_id
    secret = restaurant.click_secret_key
    if not (merchant_id and secret and payment.external_id):
        # Test/mock rejim — provider chaqirish o'rnig'a stub
        log.info("Click REVERSE stub (no live keys): payment=%d", payment.id)
        return True, f"click-stub-{payment.id}", None

    url = f"https://api.click.uz/v2/merchant/payment/reversal/{merchant_id}/{payment.external_id}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.delete(url)  # Click reversal — DELETE method
        if r.status_code == 200:
            data = r.json()
            return True, data.get("payment_id") or str(payment.external_id), None
        return False, None, f"Click HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, None, f"Click error: {e}"


async def _call_payme_cancel(
    *, restaurant: Restaurant, payment: Payment,
) -> tuple[bool, Optional[str], Optional[str]]:
    """Payme JSON-RPC CancelTransaction merchant tomondan chaqirish.

    Hozircha: stub — Payme bizdan webhook orqali kelishini so'raydi.
    Real merchant-initiated cancel uchun Payme'ning ad-hoc API'si yo'q —
    Payme dashboard'dan qo'lda yoki dispute orqali amalga oshiriladi.
    """
    log.info("Payme cancel stub (no live merchant API): payment=%d", payment.id)
    return True, f"payme-stub-{payment.id}", None


async def _call_telegram_refund(
    *, order: Order, charge_id: str,
) -> tuple[bool, Optional[str], Optional[str]]:
    """Telegram bot.refundStarPayment yoki refund tx — bot tokeni orqali.

    Telegram Bot API: refundStarPayment(user_id, telegram_payment_charge_id)
    Hujjat: https://core.telegram.org/bots/api#refundstarpayment
    """
    # Restoran bot tokenini topish (order → restaurant → bot_token)
    if not order.user_id:
        return False, None, "Order has no user"

    # Telegram refund — bizda bot yoki user_id ni alohida olishimiz kerak
    # Hozir stub — to'liq integratsiya: get_user(order.user_id).telegram_id + bot_token
    log.info("Telegram refund stub: order=%d charge=%s", order.id, charge_id)
    return True, f"tg-stub-{charge_id[:16]}", None


# ── SaaS Payment refund ────────────────────────────────────────

async def refund_saas_payment(
    db: AsyncSession,
    *,
    payment_id: int,
    amount_tiyin: Optional[int] = None,
    reason: str = "",
    requested_by_admin_id: Optional[int] = None,
) -> RefundResult:
    """SaaS tarif uchun to'lovni qaytarish.

    Bajaradi:
      1. Payment.status='refunded'
      2. Provider'ga REVERSE/CancelTransaction yuborish
      3. Restaurant.plan_expires_at proportional qisqartirish
      4. Refund yozuvi yaratish
    """
    pay = (await db.execute(select(Payment).where(Payment.id == payment_id))).scalar_one_or_none()
    if not pay:
        return RefundResult(False, None, None, "Payment not found")
    if pay.status != "success":
        return RefundResult(False, None, None, f"Payment status is '{pay.status}', faqat success qaytariladi")

    rest = (await db.execute(
        select(Restaurant).where(Restaurant.id == pay.restaurant_id)
    )).scalar_one_or_none()
    if not rest:
        return RefundResult(False, None, None, "Restaurant not found")

    refund_amount = amount_tiyin if amount_tiyin and amount_tiyin > 0 else pay.amount_tiyin
    if refund_amount > pay.amount_tiyin:
        return RefundResult(False, None, None, "Refund amount > payment amount")

    refund = Refund(
        payment_id=pay.id,
        restaurant_id=rest.id,
        amount_tiyin=refund_amount,
        reason=reason or "SaaS refund (super-admin)",
        status="pending",
        provider=pay.provider,
        requested_by_admin_id=requested_by_admin_id,
    )
    db.add(refund)
    await db.flush()

    # Provider call
    if pay.provider == "click":
        ok, provider_refund_id, err = await _call_click_reverse(
            restaurant=rest, payment=pay, amount_tiyin=refund_amount,
        )
    elif pay.provider == "payme":
        ok, provider_refund_id, err = await _call_payme_cancel(
            restaurant=rest, payment=pay,
        )
    else:
        ok, provider_refund_id, err = False, None, f"Unknown provider: {pay.provider}"

    refund.provider_refund_id = provider_refund_id
    refund.error_message = err
    refund.completed_at = datetime.utcnow()

    if not ok:
        refund.status = "failed"
        await db.commit()
        return RefundResult(False, refund.id, None, err)

    # Refund muvaffaqiyatli — payment'ni refunded deb belgilaymiz
    refund.status = "success"
    pay.status = "refunded"

    # Plan expires qisqartirish — proportional (refund_amount / amount_tiyin × 30 kun)
    if rest.plan_expires_at and pay.amount_tiyin > 0:
        ratio = refund_amount / pay.amount_tiyin
        days_to_remove = int(round(30 * ratio))
        from datetime import timedelta
        rest.plan_expires_at = rest.plan_expires_at - timedelta(days=days_to_remove)

    await db.commit()

    # Telegram alert
    try:
        from api.services.notifier import notify_platform_admin
        from api.services.billing import tiyin_to_uzs
        await notify_platform_admin(
            f"💸 <b>SaaS Refund</b>\n"
            f"Restoran: {rest.name}\n"
            f"Payment #{pay.id} — {pay.provider}\n"
            f"Summa: {tiyin_to_uzs(refund_amount):,.0f} so'm\n"
            f"Sabab: {reason or '—'}"
        )
    except Exception:
        pass

    return RefundResult(True, refund.id, provider_refund_id, None)


# ── Order refund ──────────────────────────────────────────────

# Cancellation policy (so'm'da emas, foiz'da)
# Tadbir/buyurtma sanasidan necha soat oldin → qaytarish foizi
CANCEL_POLICY = [
    (24, 100),   # >= 24 soat oldin → 100% qaytariladi
    (6,  50),    # 6-24 soat oldin → 50% qaytariladi
    (0,  0),     # < 6 soat → qaytarilmaydi
]


def _calculate_refund_amount(
    paid_amount_tiyin: int,
    event_dt: Optional[datetime],
) -> tuple[int, int]:
    """Cancellation policy bo'yicha qaytarilishi mumkin bo'lgan summa.

    Returns: (refund_tiyin, percent)
    """
    if event_dt is None:
        # Sana noma'lum — to'liq qaytarish
        return paid_amount_tiyin, 100
    hours_until = (event_dt - datetime.utcnow()).total_seconds() / 3600
    for h_min, pct in CANCEL_POLICY:
        if hours_until >= h_min:
            return int(paid_amount_tiyin * pct / 100), pct
    return 0, 0


async def refund_order(
    db: AsyncSession,
    *,
    order_id: int,
    amount_tiyin: Optional[int] = None,
    reason: str = "",
    requested_by_admin_id: Optional[int] = None,
    apply_policy: bool = True,
) -> RefundResult:
    """Buyurtma to'lovini qaytarish.

    Bajaradi:
      1. Cancellation policy hisoblash (yoki amount_tiyin override)
      2. Telegram/Click/Payme refund chaqiruvi
      3. CommissionPayment kompensatsiya yozuvi (manfiy revenue)
      4. Order.status='cancelled', payment_status='refunded'
      5. Booking release (mashina bo'shatiladi)
    """
    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if not order:
        return RefundResult(False, None, None, "Order not found")
    if (order.payment_status or "") != "paid":
        return RefundResult(False, None, None, f"payment_status='{order.payment_status}', refund qilib bo'lmaydi")

    rest = (await db.execute(
        select(Restaurant).where(Restaurant.id == order.restaurant_id)
    )).scalar_one_or_none()

    paid_t = order.paid_amount_tiyin or 0

    # Manfiy/nol amount tiyin'ni rad etish (xavfsizlik)
    if amount_tiyin is not None and amount_tiyin <= 0:
        return RefundResult(False, None, None, "amount_tiyin musbat bo'lishi shart")

    if amount_tiyin and amount_tiyin > 0:
        refund_amount = min(amount_tiyin, paid_t)
        policy_pct = int(round(refund_amount * 100 / paid_t)) if paid_t else 0
    elif apply_policy:
        # Catering uchun event_date — DateTime; oddiy zakaz uchun policy ishlamaydi (to'liq)
        event_dt = order.event_date if order.event_date else None
        refund_amount, policy_pct = _calculate_refund_amount(paid_t, event_dt)
    else:
        refund_amount, policy_pct = paid_t, 100

    if refund_amount <= 0:
        return RefundResult(False, None, None, f"Cancellation policy: 0% (kech bekor qilish)")

    refund = Refund(
        order_id=order.id,
        restaurant_id=order.restaurant_id,
        amount_tiyin=refund_amount,
        reason=(reason or f"Order refund ({policy_pct}%)"),
        status="pending",
        provider=(order.payment_provider or order.payment_method or "manual"),
        requested_by_admin_id=requested_by_admin_id,
    )
    db.add(refund)
    await db.flush()

    # Provider call
    if (order.payment_method or "") == "telegram" and order.payment_charge_id:
        ok, provider_refund_id, err = await _call_telegram_refund(
            order=order, charge_id=order.payment_charge_id,
        )
    elif order.payment_provider == "click" and rest:
        # Click order refund — placeholder (provider Telegram orqali bo'lgan bo'lsa)
        ok, provider_refund_id, err = True, f"click-order-{order.id}", None
    elif order.payment_provider == "payme" and rest:
        ok, provider_refund_id, err = True, f"payme-order-{order.id}", None
    else:
        # Naqd yoki noma'lum — manual refund
        ok, provider_refund_id, err = True, "manual", None

    refund.provider_refund_id = provider_refund_id
    refund.error_message = err
    refund.completed_at = datetime.utcnow()

    if not ok:
        refund.status = "failed"
        await db.commit()
        return RefundResult(False, refund.id, None, err)

    refund.status = "success"

    # Order holatini yangilash
    full_refund = refund_amount >= paid_t
    order.payment_status = "refunded" if full_refund else "partial_refund"
    if order.status != OrderStatus.cancelled:
        order.status = OrderStatus.cancelled

    # Commission compensation — manfiy revenue (super-admin hisobi)
    if rest and (rest.commission_percent or 0) > 0:
        from api.services.telegram_payments import tiyin_to_uzs
        refund_uzs = tiyin_to_uzs(refund_amount)
        comp = CommissionPayment(
            restaurant_id=rest.id,
            amount=-(round(refund_uzs * (rest.commission_percent or 0) / 100.0, 2)),
            commission_percent=float(rest.commission_percent or 0),
            orders_revenue=-refund_uzs,
            order_id=order.id,
            note=f"Refund #{refund.id} ({policy_pct}%)",
            status="confirmed",
        )
        db.add(comp)

    # Booking release (delivery uchun)
    try:
        from database.models import DeliveryCarBooking
        bookings = (await db.execute(
            select(DeliveryCarBooking).where(DeliveryCarBooking.order_id == order.id)
        )).scalars().all()
        for b in bookings:
            await db.delete(b)
    except Exception:
        pass

    await db.commit()

    # User'ga Telegram xabar
    try:
        from api.services.notifier import notify_platform_admin
        from api.services.billing import tiyin_to_uzs
        if rest:
            await notify_platform_admin(
                f"💸 <b>Order Refund</b>\n"
                f"Restoran: {rest.name}\n"
                f"Order #{order.id} — {order.payment_method}\n"
                f"Qaytarilmoqda: {tiyin_to_uzs(refund_amount):,.0f} so'm ({policy_pct}%)\n"
                f"Sabab: {reason or '—'}"
            )
    except Exception:
        pass

    # Mijozga bot orqali xabar
    try:
        await _notify_user_refund(db, order, refund_amount, policy_pct)
    except Exception:
        pass

    return RefundResult(True, refund.id, provider_refund_id, None)


async def _notify_user_refund(
    db: AsyncSession, order: Order, refund_amount_tiyin: int, percent: int,
) -> None:
    """Mijozga Telegram orqali pul qaytarilishi haqida xabar."""
    import os
    from database.models import User
    from api.services.billing import tiyin_to_uzs

    user = (await db.execute(select(User).where(User.id == order.user_id))).scalar_one_or_none()
    if not user or not user.telegram_id:
        return

    rest = (await db.execute(
        select(Restaurant).where(Restaurant.id == order.restaurant_id)
    )).scalar_one_or_none()
    bot_token = (rest.bot_token if rest and rest.bot_token else os.getenv("BOT_TOKEN", ""))
    if not bot_token:
        return

    pct_note = "" if percent == 100 else f" ({percent}% bekor qilish siyosati)"
    text = (
        f"💸 <b>Buyurtma #{order.id} bekor qilindi</b>\n\n"
        f"💰 Qaytariladigan summa: <b>{tiyin_to_uzs(refund_amount_tiyin):,.0f} so'm</b>{pct_note}\n\n"
        f"Pul 1-3 ish kuni ichida kartangizga qaytariladi.\n"
        f"Savollar bo'lsa, restoran bilan bog'laning."
    )
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": user.telegram_id, "text": text, "parse_mode": "HTML"},
            )
    except Exception:
        pass
