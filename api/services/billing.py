"""Billing service — Click va Payme to'lov gateway'lari.

Pul birligi: tiyin (1 so'm = 100 tiyin). Float ishlatmaymiz — float'da
yumaloqlash xatoligi pul bilan ishlashda taqiqlangan.

Sandbox/Mock rejim:
- `CLICK_*_KEY` env yoki restaurant.click_secret_key bo'sh bo'lsa — mock URL qaytariladi
- Real prod uchun: kompaniya merchant.click.uz va business.paycom.uz da ro'yxatdan o'tib credentials oladi

Webhook xavfsizligi:
- Click: MD5 signature tekshiruvi + ixtiyoriy IP allowlist
- Payme: Basic Auth (merchant_id:secret) + JSON-RPC method nomlari
"""
from __future__ import annotations
import hashlib
import time
import uuid
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.models import Restaurant, Plan, Payment

# Click webhook IP allowlist (prod uchun). Bo'sh ro'yxat = tekshirilmaydi.
CLICK_ALLOWED_IPS: set[str] = set()  # masalan: {"195.158.16.140"}

# Click action enum (ularning hujjatlariga ko'ra)
CLICK_ACTION_PREPARE = 0
CLICK_ACTION_COMPLETE = 1


# ── Yordamchi ────────────────────────────────────────

def uzs_to_tiyin(uzs: float) -> int:
    """Float so'mni intger tiyinga aylantirish (suzuvchi nuqta xatosini chiqaradi)."""
    return int(round(uzs * 100))


def tiyin_to_uzs(tiyin: int) -> float:
    return tiyin / 100.0


def _gen_merchant_trans_id(restaurant_id: int, plan_id: int) -> str:
    """Bizning idempotency kalit — Click/Payme'ga merchant_trans_id sifatida yuboriladi."""
    return f"r{restaurant_id}-p{plan_id}-{uuid.uuid4().hex[:10]}"


# ── Click ────────────────────────────────────────────

def click_signature(*parts: str) -> str:
    """MD5(...) — Click prepare/complete uchun signature.

    Tartib (Click hujjati): click_trans_id + service_id + secret_key + merchant_trans_id + amount + action + sign_time
    Complete uchun yana merchant_prepare_id qo'shiladi (bizning DB'dagi prepare_id).
    """
    raw = "".join(str(p) for p in parts)
    return hashlib.md5(raw.encode()).hexdigest()


def click_invoice_url(merchant_id: str, service_id: str, amount_tiyin: int, merchant_trans_id: str) -> str:
    """Click hosted-page URL'ini qurish. Click bunday URL'ni avtomatik tan oladi.

    Prod URL: https://my.click.uz/services/pay
    """
    amount_uzs = tiyin_to_uzs(amount_tiyin)
    return (
        f"https://my.click.uz/services/pay"
        f"?service_id={service_id}"
        f"&merchant_id={merchant_id}"
        f"&amount={amount_uzs:.2f}"
        f"&transaction_param={merchant_trans_id}"
    )


def verify_click_signature(payload: dict, secret_key: str) -> bool:
    """Click webhook'dagi `sign_string` ni qayta hisoblab tekshirish.

    payload misoli (Click prepare):
      click_trans_id, service_id, click_paydoc_id, merchant_trans_id,
      amount, action, error, error_note, sign_time, sign_string
    """
    try:
        action = int(payload.get("action", -1))
        # Complete request'da merchant_prepare_id qo'shimcha
        if action == CLICK_ACTION_COMPLETE:
            calc = click_signature(
                payload["click_trans_id"], payload["service_id"], secret_key,
                payload["merchant_trans_id"], payload.get("merchant_prepare_id", ""),
                payload["amount"], payload["action"], payload["sign_time"],
            )
        else:
            calc = click_signature(
                payload["click_trans_id"], payload["service_id"], secret_key,
                payload["merchant_trans_id"],
                payload["amount"], payload["action"], payload["sign_time"],
            )
        return calc == payload.get("sign_string")
    except (KeyError, ValueError):
        return False


def is_click_ip_allowed(client_ip: Optional[str]) -> bool:
    """Agar allowlist sozlangan bo'lsa — IP shunda bo'lishi shart. Aks holda hammaga ruxsat."""
    if not CLICK_ALLOWED_IPS:
        return True
    return client_ip in CLICK_ALLOWED_IPS


# ── Mock helper ─────────────────────────────────────

def is_mock_mode(rest: Restaurant, provider: str) -> bool:
    """Restaurant credentials bo'sh bo'lsa — mock URL ishlatamiz (testlash uchun)."""
    if provider == "click":
        return not (rest.click_enabled and rest.click_merchant_id and rest.click_service_id and rest.click_secret_key)
    if provider == "payme":
        return not (rest.payme_enabled and rest.payme_merchant_id and rest.payme_secret_key)
    return True


def mock_payment_url(merchant_trans_id: str, provider: str) -> str:
    return f"https://mock.payments.local/{provider}/{merchant_trans_id}"


# ── Asosiy biznes-logika ────────────────────────────

async def create_payment_record(
    *,
    restaurant_id: int,
    plan: Plan,
    provider: str,
    db: AsyncSession,
) -> Payment:
    """DB'da pending Payment yozuvini yaratadi va to'lov URL'ni payment_url ga yozadi."""
    if provider not in ("click", "payme"):
        raise HTTPException(400, f"Noma'lum provider: {provider}")
    if not plan.monthly_price or plan.monthly_price <= 0:
        raise HTTPException(400, f"'{plan.name}' tarifi to'lovsiz — to'lov yaratib bo'lmaydi")

    # Restaurant
    rest_result = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
    rest = rest_result.scalar_one_or_none()
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")

    amount_tiyin = uzs_to_tiyin(plan.monthly_price)
    merchant_trans_id = _gen_merchant_trans_id(restaurant_id, plan.id)

    # URL yaratish
    if is_mock_mode(rest, provider):
        url = mock_payment_url(merchant_trans_id, provider)
    elif provider == "click":
        url = click_invoice_url(
            merchant_id=rest.click_merchant_id,
            service_id=rest.click_service_id,
            amount_tiyin=amount_tiyin,
            merchant_trans_id=merchant_trans_id,
        )
    else:  # payme
        # Payme hosted page (oddiy variant). Real flow: server-side checkout API
        cashbox = rest.payme_merchant_id
        url = (
            f"https://checkout.paycom.uz/"
            f"?m={cashbox}&ac.merchant_trans_id={merchant_trans_id}&a={amount_tiyin}"
        )

    payment = Payment(
        restaurant_id=restaurant_id,
        plan_id=plan.id,
        amount_tiyin=amount_tiyin,
        status="pending",
        provider=provider,
        merchant_trans_id=merchant_trans_id,
        payment_url=url,
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    return payment


async def mark_payment_success(payment: Payment, external_id: Optional[str], db: AsyncSession) -> None:
    """Payment status='success' va restaurantning plan_id+plan_expires_at ni yangilash."""
    payment.status = "success"
    payment.external_id = external_id
    payment.paid_at = datetime.utcnow()

    # Restaurant tarifini yangilash
    rest_result = await db.execute(select(Restaurant).where(Restaurant.id == payment.restaurant_id))
    rest = rest_result.scalar_one_or_none()
    if rest:
        # Mavjud expires_at kelajakda bo'lsa — uning ustiga 30 kun qo'shamiz, aks holda hozirdan +30 kun
        from datetime import timedelta
        base = rest.plan_expires_at if (rest.plan_expires_at and rest.plan_expires_at > datetime.utcnow()) else datetime.utcnow()
        rest.plan_id = payment.plan_id
        rest.plan_expires_at = base + timedelta(days=30)

    await db.commit()


async def mark_payment_failed(payment: Payment, reason: str, db: AsyncSession) -> None:
    payment.status = "failed"
    payment.error_message = reason
    await db.commit()


async def get_payment_by_merchant_trans(merchant_trans_id: str, db: AsyncSession) -> Optional[Payment]:
    res = await db.execute(select(Payment).where(Payment.merchant_trans_id == merchant_trans_id))
    return res.scalar_one_or_none()


# ── Click webhook handler (qayta foydalaniladigan) ──

async def handle_click_webhook(payload: dict, client_ip: Optional[str], db: AsyncSession) -> dict:
    """Click prepare va complete so'rovlarini qayta ishlash.

    Click hujjatiga ko'ra javob shakli:
      {
        "click_trans_id": ...,
        "merchant_trans_id": ...,
        "merchant_prepare_id": ...,  # complete uchun
        "merchant_confirm_id": ...,  # complete uchun
        "error": 0,                   # 0 = OK, manfiy = xato
        "error_note": "Success"
      }
    """
    if not is_click_ip_allowed(client_ip):
        raise HTTPException(403, "IP allowlist'da yo'q")

    try:
        merchant_trans_id = payload["merchant_trans_id"]
        action = int(payload["action"])
        amount_uzs = float(payload["amount"])
    except (KeyError, ValueError):
        return {"error": -8, "error_note": "Invalid request"}

    payment = await get_payment_by_merchant_trans(merchant_trans_id, db)
    if not payment:
        return {"error": -5, "error_note": "Order not found"}

    # Restaurant'ni topib secret_key ni olamiz
    rest_res = await db.execute(select(Restaurant).where(Restaurant.id == payment.restaurant_id))
    rest = rest_res.scalar_one_or_none()
    if not rest or not rest.click_secret_key:
        return {"error": -9, "error_note": "Merchant not configured"}

    if not verify_click_signature(payload, rest.click_secret_key):
        from api.logging_config import log_critical
        log_critical(
            "payment", "Click webhook signature mismatch",
            payment_id=payment.id, restaurant_id=rest.id,
            merchant_trans_id=merchant_trans_id, client_ip=client_ip,
        )
        return {"error": -1, "error_note": "Bad sign"}

    # Sumalar mos kelishi
    if uzs_to_tiyin(amount_uzs) != payment.amount_tiyin:
        from api.logging_config import log_critical
        log_critical(
            "payment", "Click webhook amount mismatch",
            payment_id=payment.id, restaurant_id=rest.id,
            expected_tiyin=payment.amount_tiyin, got_uzs=amount_uzs,
        )
        await mark_payment_failed(payment, f"Amount mismatch: {amount_uzs} vs {tiyin_to_uzs(payment.amount_tiyin)}", db)
        return {"error": -2, "error_note": "Amount mismatch"}

    if payment.status == "success":
        # Idempotent — qayta tasdiqlash so'ralgan
        return {
            "click_trans_id": payload.get("click_trans_id"),
            "merchant_trans_id": merchant_trans_id,
            "merchant_prepare_id": payment.id,
            "error": 0,
            "error_note": "Already paid",
        }

    if action == CLICK_ACTION_PREPARE:
        return {
            "click_trans_id": payload.get("click_trans_id"),
            "merchant_trans_id": merchant_trans_id,
            "merchant_prepare_id": payment.id,
            "error": 0,
            "error_note": "Success",
        }
    if action == CLICK_ACTION_COMPLETE:
        await mark_payment_success(payment, external_id=str(payload.get("click_trans_id")), db=db)
        return {
            "click_trans_id": payload.get("click_trans_id"),
            "merchant_trans_id": merchant_trans_id,
            "merchant_confirm_id": payment.id,
            "error": 0,
            "error_note": "Success",
        }

    return {"error": -3, "error_note": "Unknown action"}
