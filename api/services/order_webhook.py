"""Mijoz buyurtmasi to'lov webhook'lari uchun ichki handler'lar.

Click va Payme webhook'lari `api/routes/billing.py` ichida yagona endpoint orqali
keladi. merchant_trans_id prefiksiga qarab dispatch qilinadi:
  * "r-..." → tarif (subscription) to'lovi → mavjud Payment yozuvi
  * "o-..." → mijoz buyurtmasi → Order modeli

Bu modul `o-` prefiksli to'lovlarni qayta ishlaydi.
"""
from __future__ import annotations

import os
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Order, OrderStatus, Restaurant, User
from api.services.order_payments import parse_order_id


log = logging.getLogger(__name__)


# ── Bot orqali mijozga xabar ─────────────────────────────────────────

async def _notify_customer(
    db: AsyncSession,
    order: Order,
    success: bool,
    error_reason: Optional[str] = None,
) -> None:
    """To'lov muvaffaqiyatli/muvaffaqiyatsizligi haqida mijozga Telegram xabar."""
    user = (await db.execute(select(User).where(User.id == order.user_id))).scalar_one_or_none()
    if not user or not user.telegram_id:
        return

    rest = (await db.execute(
        select(Restaurant).where(Restaurant.id == order.restaurant_id)
    )).scalar_one_or_none()
    bot_token = (rest.bot_token if rest else "") or os.getenv("BOT_TOKEN", "")
    if not bot_token:
        return

    if success:
        text = (
            f"✅ <b>To'lov qabul qilindi</b>\n"
            f"Buyurtma #{order.id}\n\n"
            f"Buyurtmangiz tayyorlanmoqda 🍽"
        )
    else:
        reason = error_reason or "noma'lum sabab"
        text = (
            f"❌ <b>To'lov amalga oshmadi</b>\n"
            f"Buyurtma #{order.id}\n\n"
            f"Sabab: {reason}\n\n"
            f"Qayta urinib ko'ring yoki boshqa to'lov usuli tanlang."
        )

    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": user.telegram_id,
                    "text": text,
                    "parse_mode": "HTML",
                },
            )
    except Exception as e:
        log.warning("Order webhook notify failed: %s", e)


async def _mark_order_paid(
    db: AsyncSession,
    order: Order,
    provider: str,
    provider_tx_id: str,
    amount_tiyin: int,
) -> None:
    """Buyurtmani to'langan deb belgilash + Yandex dispatch (delivery bo'lsa)."""
    if order.payment_status == "paid":
        return  # idempotent
    order.payment_status = "paid"
    order.payment_provider = provider
    order.payment_method = provider
    order.provider_tx_id = provider_tx_id
    order.paid_amount_tiyin = amount_tiyin
    order.payment_paid_at = datetime.utcnow()
    if order.status == OrderStatus.pending:
        order.status = OrderStatus.preparing
    await db.commit()

    # To'lov tasdiqlandi → endi Yandex Delivery'ga dispatch qilamiz
    try:
        from api.services.delivery import dispatch_order_to_provider
        await dispatch_order_to_provider(order, db)
    except Exception as e:
        log.warning("Yandex dispatch xato (to'lov OK, lekin dispatch fail): %s", e)


async def _mark_order_failed(
    db: AsyncSession,
    order: Order,
    error: str,
) -> None:
    """Buyurtma to'lovini muvaffaqiyatsiz deb belgilash."""
    order.payment_status = "failed"
    order.payment_error = error
    await db.commit()


# ── Click order webhook (prepare + complete) ────────────────────────

CLICK_ACTION_PREPARE = 0
CLICK_ACTION_COMPLETE = 1
CLICK_ACTION_REVERSE = -1


async def handle_click_order_webhook(
    payload: dict,
    db: AsyncSession,
) -> dict:
    """Click order webhook — merchant_trans_id 'o-<order_id>-...' bo'lganda chaqiriladi.

    Authentication va signature billing.py'da tekshirib bo'lingan deb taxmin qilamiz.
    """
    merchant_trans_id = payload.get("merchant_trans_id", "")
    order_id = parse_order_id(merchant_trans_id)
    if not order_id:
        return {"error": -5, "error_note": "Invalid order trans_id"}

    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if not order:
        return {"error": -5, "error_note": "Order not found"}

    try:
        action = int(payload["action"])
        amount_uzs = float(payload["amount"])
        click_trans_id = str(payload["click_trans_id"])
    except (KeyError, ValueError):
        return {"error": -8, "error_note": "Invalid request"}

    expected_uzs = float(order.total_price or 0)
    if abs(amount_uzs - expected_uzs) > 0.5:
        await _mark_order_failed(db, order, f"Sum mos kelmadi: kelgan {amount_uzs}, kutilgan {expected_uzs}")
        await _notify_customer(db, order, success=False, error_reason="To'lov summasi mos kelmadi")
        return {"error": -2, "error_note": "Incorrect amount"}

    # Click'ning client-side bekor qilishi
    err = int(payload.get("error", 0))
    if err < 0:
        reason = payload.get("error_note") or "to'lov bekor qilindi"
        await _mark_order_failed(db, order, reason)
        await _notify_customer(db, order, success=False, error_reason=reason)
        return {
            "click_trans_id": payload.get("click_trans_id"),
            "merchant_trans_id": merchant_trans_id,
            "error": -9,
            "error_note": "Transaction cancelled",
        }

    if action == CLICK_ACTION_PREPARE:
        # Prepare bosqichi — biz hali to'lovni "qabul qilamiz" deb tasdiqlaymiz
        if order.payment_status == "paid":
            return {"error": -4, "error_note": "Already paid"}
        order.provider_tx_id = click_trans_id
        order.click_prepare_id = order.id  # merchant_prepare_id = bizning order ID
        await db.commit()
        return {
            "click_trans_id": click_trans_id,
            "merchant_trans_id": merchant_trans_id,
            "merchant_prepare_id": order.id,
            "error": 0,
            "error_note": "Success",
        }

    if action == CLICK_ACTION_COMPLETE:
        # Complete — to'lov muvaffaqiyatli o'tdi
        if order.payment_status == "paid":
            # Idempotent — qaytarib beramiz
            return {
                "click_trans_id": click_trans_id,
                "merchant_trans_id": merchant_trans_id,
                "merchant_confirm_id": order.id,
                "error": 0,
                "error_note": "Success",
            }
        amount_tiyin = int(round(amount_uzs * 100))
        await _mark_order_paid(db, order, "click", click_trans_id, amount_tiyin)
        await _notify_customer(db, order, success=True)
        return {
            "click_trans_id": click_trans_id,
            "merchant_trans_id": merchant_trans_id,
            "merchant_confirm_id": order.id,
            "error": 0,
            "error_note": "Success",
        }

    if action == CLICK_ACTION_REVERSE:
        # Reverse — to'lov qaytarildi
        if order.payment_status == "paid":
            order.payment_status = "refunded"
            await db.commit()
            await _notify_customer(db, order, success=False, error_reason="To'lov qaytarildi")
        return {
            "click_trans_id": click_trans_id,
            "merchant_trans_id": merchant_trans_id,
            "error": 0,
            "error_note": "Success",
        }

    return {"error": -3, "error_note": "Action not found"}


# ── Payme order webhook (JSON-RPC method handler) ───────────────────

# Payme state codes
PAYME_STATE_CREATED = 1
PAYME_STATE_PERFORMED = 2
PAYME_STATE_CANCELLED_BEFORE_PERFORM = -1
PAYME_STATE_CANCELLED_AFTER_PERFORM = -2


def _payme_error(code: int, msg_uz: str, request_id: Optional[int] = None) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": {"uz": msg_uz, "ru": msg_uz, "en": msg_uz}},
    }


def _payme_ok(result: dict, request_id: Optional[int] = None) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


async def handle_payme_order_method(
    method: str,
    params: dict,
    request_id: Optional[int],
    db: AsyncSession,
) -> dict:
    """Payme JSON-RPC method'ini Order kontekstida qayta ishlash.

    Payme URL'imizda `ac.order_id=<id>` deb yuborganmiz, shuning uchun
    `params.account.order_id` bizga keladi.
    """
    account = params.get("account") or {}
    order_id_raw = account.get("order_id")
    if order_id_raw is None:
        return _payme_error(-31050, "order_id required", request_id)
    try:
        order_id = int(order_id_raw)
    except (TypeError, ValueError):
        return _payme_error(-31050, "order_id invalid", request_id)

    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if not order:
        return _payme_error(-31050, "Order not found", request_id)

    if method == "CheckPerformTransaction":
        expected_tiyin = int(round((order.total_price or 0) * 100))
        if params.get("amount") != expected_tiyin:
            return _payme_error(-31001, "Wrong amount", request_id)
        if order.payment_status == "paid":
            return _payme_error(-31008, "Already paid", request_id)
        return _payme_ok({"allow": True}, request_id)

    if method == "CreateTransaction":
        if order.payment_status == "paid":
            return _payme_error(-31008, "Already paid", request_id)
        # Idempotency: agar shu Payme tranzaksiya ID allaqachon yozilgan bo'lsa
        payme_tx = params.get("id")
        if order.provider_tx_id and order.provider_tx_id != payme_tx:
            return _payme_error(-31008, "Another transaction in progress", request_id)
        if not order.provider_tx_id:
            order.provider_tx_id = payme_tx
            order.payment_provider = "payme"
            await db.commit()
        return _payme_ok({
            "create_time": int(datetime.utcnow().timestamp() * 1000),
            "transaction": str(order.id),
            "state": PAYME_STATE_CREATED,
        }, request_id)

    if method == "PerformTransaction":
        payme_tx = params.get("id")
        if order.provider_tx_id != payme_tx:
            return _payme_error(-31003, "Transaction not found", request_id)
        if order.payment_status == "paid":
            # Idempotent
            return _payme_ok({
                "transaction": str(order.id),
                "perform_time": int(order.payment_paid_at.timestamp() * 1000) if order.payment_paid_at else 0,
                "state": PAYME_STATE_PERFORMED,
            }, request_id)

        amount_tiyin = int(round((order.total_price or 0) * 100))
        await _mark_order_paid(db, order, "payme", payme_tx, amount_tiyin)
        await _notify_customer(db, order, success=True)
        return _payme_ok({
            "transaction": str(order.id),
            "perform_time": int(order.payment_paid_at.timestamp() * 1000),
            "state": PAYME_STATE_PERFORMED,
        }, request_id)

    if method == "CancelTransaction":
        payme_tx = params.get("id")
        if order.provider_tx_id != payme_tx:
            return _payme_error(-31003, "Transaction not found", request_id)
        was_paid = order.payment_status == "paid"
        state = PAYME_STATE_CANCELLED_AFTER_PERFORM if was_paid else PAYME_STATE_CANCELLED_BEFORE_PERFORM
        order.payment_status = "refunded" if was_paid else "failed"
        order.payment_error = "Cancelled by Payme"
        await db.commit()
        await _notify_customer(db, order, success=False, error_reason="To'lov bekor qilindi")
        return _payme_ok({
            "transaction": str(order.id),
            "cancel_time": int(datetime.utcnow().timestamp() * 1000),
            "state": state,
        }, request_id)

    if method == "CheckTransaction":
        payme_tx = params.get("id")
        if order.provider_tx_id != payme_tx:
            return _payme_error(-31003, "Transaction not found", request_id)
        state = PAYME_STATE_PERFORMED if order.payment_status == "paid" else PAYME_STATE_CREATED
        return _payme_ok({
            "transaction": str(order.id),
            "create_time": int((order.created_at or datetime.utcnow()).timestamp() * 1000),
            "perform_time": int(order.payment_paid_at.timestamp() * 1000) if order.payment_paid_at else 0,
            "cancel_time": 0,
            "state": state,
            "reason": None,
        }, request_id)

    return _payme_error(-32601, "Method not found", request_id)


# ── Uzum order webhook ──────────────────────────────────────────────

async def handle_uzum_order_webhook(
    action: str,
    payload: dict,
    db: AsyncSession,
) -> dict:
    """Uzum Bank Merchant API webhook handler.

    Uzum methodlari: check, create, confirm, reverse, status.
    Body shape (taxminan):
      {
        "serviceId": "...",
        "transactionId": "uzum-side-tx-id",
        "order_id": "42",   # bizning order_id (URL'da yuborgan)
        "amount": 60000,    # tiyin
      }
    """
    order_id_raw = payload.get("order_id") or payload.get("orderId")
    if not order_id_raw:
        return {"status": "ERROR", "errorCode": 1, "errorMessage": "order_id required"}
    try:
        order_id = int(order_id_raw)
    except (TypeError, ValueError):
        return {"status": "ERROR", "errorCode": 1, "errorMessage": "order_id invalid"}

    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if not order:
        return {"status": "ERROR", "errorCode": 2, "errorMessage": "Order not found"}

    uzum_tx_id = payload.get("transactionId") or payload.get("transaction_id")
    amount_tiyin = int(payload.get("amount") or 0)

    if action == "check":
        expected = int(round((order.total_price or 0) * 100))
        if amount_tiyin != expected:
            return {"status": "ERROR", "errorCode": 3, "errorMessage": "Amount mismatch"}
        if order.payment_status == "paid":
            return {"status": "ERROR", "errorCode": 4, "errorMessage": "Already paid"}
        return {"status": "OK", "errorCode": 0}

    if action == "create":
        if order.payment_status == "paid":
            return {"status": "ERROR", "errorCode": 4, "errorMessage": "Already paid"}
        order.provider_tx_id = uzum_tx_id
        order.payment_provider = "uzum"
        await db.commit()
        return {
            "status": "OK",
            "errorCode": 0,
            "transactionId": uzum_tx_id,
            "merchantTransactionId": str(order.id),
        }

    if action == "confirm":
        if order.payment_status == "paid":
            return {"status": "OK", "errorCode": 0}  # idempotent
        await _mark_order_paid(db, order, "uzum", uzum_tx_id, amount_tiyin)
        await _notify_customer(db, order, success=True)
        return {"status": "OK", "errorCode": 0}

    if action == "reverse":
        was_paid = order.payment_status == "paid"
        order.payment_status = "refunded" if was_paid else "failed"
        order.payment_error = "Cancelled by Uzum"
        await db.commit()
        await _notify_customer(db, order, success=False, error_reason="To'lov bekor qilindi")
        return {"status": "OK", "errorCode": 0}

    if action == "status":
        return {
            "status": "OK",
            "errorCode": 0,
            "paymentStatus": order.payment_status,
            "transactionId": order.provider_tx_id,
        }

    return {"status": "ERROR", "errorCode": 5, "errorMessage": f"Unknown action: {action}"}
