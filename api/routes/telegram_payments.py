"""Telegram Native Payments API endpointlari (bot bilan FastAPI o'rtasida).

Bot ushbu endpointlarni 3 nuqtada chaqiradi:

    POST /payments/telegram/prepare
        — Invoice payload tayyorlash (LabeledPrice'lar, provider_token, total)
        — Bot send_invoice() ga bermoqdan oldin

    POST /payments/telegram/precheck
        — pre_checkout_query handler ichida
        — Mashina band emasligini oxirgi marta tekshiradi

    POST /payments/telegram/confirm
        — successful_payment handler ichida
        — Order.status = confirmed, mashina band, komissiya yoziladi

Hech qaysi endpoint super-admin yoki restaurant admin auth talab qilmaydi —
ular bot tomonidan (server↔server) chaqiriladi va ichki `BOT_API_SECRET`
header bilan himoyalanadi.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.database import get_db
from api.services.telegram_payments import (
    ProviderTokenMissing, calculate_order_payment, confirm_payment,
    precheck_invoice, prepare_invoice,
)


router = APIRouter(prefix="/payments/telegram", tags=["telegram-payments"])


def _require_bot_auth(x_bot_secret: Optional[str] = Header(None, alias="X-Bot-Secret")):
    """Bot↔FastAPI ichki autentifikatsiya.

    Production'da `BOT_API_SECRET` env'da o'rnatilishi va bot shu secret bilan
    chaqirishi kerak. Bo'sh bo'lsa — `SECRET_KEY` ga fallback (dev).
    """
    expected = os.getenv("BOT_API_SECRET", settings.SECRET_KEY)
    if not x_bot_secret or x_bot_secret != expected:
        raise HTTPException(401, "Bot auth secret yaroqsiz")


# ── Schemas ──────────────────────────────────────────────────────────────

class PrepareIn(BaseModel):
    order_id: int
    provider: str = "click"   # 'click' | 'payme'


class PrecheckIn(BaseModel):
    order_id: int


class ConfirmIn(BaseModel):
    order_id: int
    amount_tiyin: int
    provider: str
    telegram_payment_charge_id: Optional[str] = None
    provider_payment_charge_id: Optional[str] = None
    is_prepayment: bool = False
    prepayment_percent: Optional[int] = None


# ── Endpoints ────────────────────────────────────────────────────────────

@router.post("/prepare", dependencies=[Depends(_require_bot_auth)])
async def prepare(body: PrepareIn, db: AsyncSession = Depends(get_db)):
    """Bot send_invoice() uchun barcha kerakli ma'lumotlar.

    Response:
        {
          "order_id": 142,
          "title": "Buyurtma #142",
          "description": "Muhsina Dollar Somsa. Jami: 87,000 so'm",
          "currency": "UZS",
          "prices": [{"label": "Somsa × 5", "amount": 3500000}, ...],
          "payload": "order_142",
          "provider_token": "<TELEGRAM_PROVIDER_TOKEN>",
          "total_tiyin": 8700000,
          "is_prepayment": false,
          "prepayment_percent": null,
          "full_total_tiyin": 8700000
        }
    """
    try:
        payload = await prepare_invoice(db, order_id=body.order_id, provider=body.provider)
    except ProviderTokenMissing as e:
        raise HTTPException(503, {
            "code": "provider_token_missing",
            "message": str(e),
            "hint": "Restaurant.pos_config['telegram_provider_token_<provider>'] yoki .env"
                    " TELEGRAM_PROVIDER_TOKEN_<PROVIDER> sozlanmagan",
        })
    except ValueError as e:
        raise HTTPException(400, str(e))
    return payload.to_dict()


@router.post("/summary", dependencies=[Depends(_require_bot_auth)])
async def summary(body: PrepareIn, db: AsyncSession = Depends(get_db)):
    """Faqat hisoblash — chek bermasdan, mijozga ko'rsatish uchun.

    Bot mijozga "Jami: X so'm, oldindan Y so'm to'lash kerak" matnini
    ko'rsatish oldidan shu endpointni chaqiradi.
    """
    from sqlalchemy import select
    from database.models import Order, Restaurant

    order = (await db.execute(
        select(Order).where(Order.id == body.order_id)
    )).scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Buyurtma topilmadi")
    rest = (await db.execute(
        select(Restaurant).where(Restaurant.id == order.restaurant_id)
    )).scalar_one_or_none()
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")

    s = await calculate_order_payment(db, order, rest)
    return {
        "order_id": order.id,
        "items_total_uzs": s.items_total_uzs,
        "delivery_fee_uzs": s.delivery_fee_uzs,
        "catering_service_fee_uzs": s.catering_service_fee_uzs,
        "grand_total_uzs": s.grand_total_uzs,
        "is_prepayment": s.is_prepayment,
        "prepayment_percent": s.prepayment_percent,
        "prepayment_amount_uzs": s.prepayment_amount_uzs,
        "payable_now_uzs": s.payable_now_uzs,
    }


@router.post("/precheck", dependencies=[Depends(_require_bot_auth)])
async def precheck(body: PrecheckIn, db: AsyncSession = Depends(get_db)):
    """Pre-checkout — mashina hali ham bo'shmi?

    Response:
        {"ok": true} — to'lov o'tishi mumkin
        {"ok": false, "error_message": "...", "reason_code": "no_car"} — Telegram'ga rad
    """
    result = await precheck_invoice(db, order_id=body.order_id)
    return {
        "ok": result.ok,
        "error_message": result.error_message,
        "reason_code": result.reason_code,
    }


class CancelUnpaidIn(BaseModel):
    order_id: int


@router.post("/cancel-unpaid", dependencies=[Depends(_require_bot_auth)])
async def cancel_unpaid(body: CancelUnpaidIn, db: AsyncSession = Depends(get_db)):
    """To'lanmagan buyurtmani bekor qilish (foydalanuvchi pay tugmadan voz kechganda).

    Faqat `payment_status='pending'` bo'lsa bekor qiladi — paid yoki partial bo'lsa
    ehtiyotsiz refund'dan saqlash uchun rad qiladi.
    """
    from sqlalchemy import select
    from database.models import Order, OrderStatus

    order = (await db.execute(select(Order).where(Order.id == body.order_id))).scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Buyurtma topilmadi")
    if (order.payment_status or "pending") != "pending":
        raise HTTPException(409, f"Buyurtma to'lov holati: {order.payment_status} — bekor qilib bo'lmaydi")
    if order.status == OrderStatus.cancelled:
        return {"ok": True, "order_id": order.id, "already_cancelled": True}

    order.status = OrderStatus.cancelled
    order.payment_status = "cancelled"
    await db.commit()
    return {"ok": True, "order_id": order.id}


@router.post("/confirm", dependencies=[Depends(_require_bot_auth)])
async def confirm(body: ConfirmIn, db: AsyncSession = Depends(get_db)):
    """successful_payment dan keyin — order paid, car booked, commission written.

    Idempotent: bir xil `telegram_payment_charge_id` ikki marta kelsa,
    ikkinchisi mavjud yozuvni qaytaradi.
    """
    result = await confirm_payment(
        db,
        order_id=body.order_id,
        amount_tiyin=body.amount_tiyin,
        provider=body.provider,
        telegram_payment_charge_id=body.telegram_payment_charge_id,
        provider_payment_charge_id=body.provider_payment_charge_id,
        is_prepayment=body.is_prepayment,
        prepayment_percent=body.prepayment_percent,
    )
    return {
        "ok": result.ok,
        "order_id": result.order_id,
        "paid_amount_tiyin": result.paid_amount_tiyin,
        "booking_id": result.booking_id,
        "commission_id": result.commission_id,
        "error": result.error,
        "vat_amount_tiyin": result.vat_amount_tiyin,
        "fiscal_qr": result.fiscal_qr,
    }
