"""Billing endpoints — tariflar ro'yxati, invoice yaratish, webhooks.

Tashqi yo'llar:
  GET  /admin/billing/plans         — barcha tariflar
  GET  /admin/billing/payments      — joriy restoran to'lovlari (tarix)
  POST /payments/create-invoice     — Click yoki Payme invoice yaratish
  POST /payments/click/webhook      — Click webhook (signature + IP allowlist)
  POST /payments/payme/webhook      — Payme JSON-RPC webhook (Basic auth)
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
import base64

from api.database import get_db
from api.auth_deps import require_restaurant_admin
from api.services.billing import (
    create_payment_record, handle_click_webhook,
    get_payment_by_merchant_trans, mark_payment_success, mark_payment_failed,
    tiyin_to_uzs, uzs_to_tiyin,
)
from database.models import Plan, Restaurant, Payment

router = APIRouter(tags=["billing"])


# ── Schemas ──────────────────────────────────────────

class CreateInvoiceRequest(BaseModel):
    plan_id: int
    provider: str  # "click" | "payme"


# ── Plans ─────────────────────────────────────────────

@router.get("/admin/billing/plans")
async def list_plans(
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Barcha faol tariflar + joriy restoran tarifi.

    Frontend bularni "tariff cards" sifatida ko'rsatadi.
    """
    result = await db.execute(
        select(Plan).where(Plan.is_active == True).order_by(Plan.monthly_price)
    )
    plans = result.scalars().all()

    current = None
    expires_at = None
    if restaurant_id:
        rest_res = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
        rest = rest_res.scalar_one_or_none()
        if rest:
            current = rest.plan_id
            expires_at = rest.plan_expires_at.isoformat() if rest.plan_expires_at else None

    return {
        "current_plan_id": current,
        "current_plan_expires_at": expires_at,
        "plans": [
            {
                "id": p.id,
                "name": p.name,
                "slug": p.slug,
                "description": p.description,
                "monthly_price": p.monthly_price,
                "monthly_price_tiyin": uzs_to_tiyin(p.monthly_price or 0),
                "commission_percent": p.commission_percent,
                "has_catering": bool(p.has_catering),
                "has_ai_agent": bool(p.has_ai_agent),
                "has_yandex": bool(p.has_yandex),
                "order_limit": p.order_limit,
            }
            for p in plans
        ],
    }


@router.get("/admin/billing/payments")
async def list_payments(
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Joriy restoran to'lov tarixi."""
    if not restaurant_id:
        return []
    result = await db.execute(
        select(Payment)
        .where(Payment.restaurant_id == restaurant_id)
        .order_by(desc(Payment.created_at))
        .limit(50)
    )
    payments = result.scalars().all()
    return [
        {
            "id": p.id,
            "amount_uzs": tiyin_to_uzs(p.amount_tiyin),
            "status": p.status,
            "provider": p.provider,
            "external_id": p.external_id,
            "merchant_trans_id": p.merchant_trans_id,
            "payment_url": p.payment_url,
            "error_message": p.error_message,
            "plan_id": p.plan_id,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "paid_at": p.paid_at.isoformat() if p.paid_at else None,
        }
        for p in payments
    ]


# ── Create invoice ────────────────────────────────────

@router.post("/payments/create-invoice")
async def create_invoice(
    data: CreateInvoiceRequest,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Tanlangan tarif uchun to'lov linkini yaratadi."""
    if not restaurant_id:
        raise HTTPException(400, "restaurant_id kerak")
    if data.provider not in ("click", "payme"):
        raise HTTPException(400, f"Provider 'click' yoki 'payme' bo'lishi kerak, kelgan: {data.provider}")

    # Plan
    plan_res = await db.execute(select(Plan).where(Plan.id == data.plan_id, Plan.is_active == True))
    plan = plan_res.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Tariff topilmadi")
    if (plan.monthly_price or 0) <= 0:
        raise HTTPException(400, "Bu tariff bepul — to'lov shart emas")

    payment = await create_payment_record(
        restaurant_id=restaurant_id, plan=plan, provider=data.provider, db=db,
    )
    return {
        "payment_id": payment.id,
        "merchant_trans_id": payment.merchant_trans_id,
        "amount_uzs": tiyin_to_uzs(payment.amount_tiyin),
        "amount_tiyin": payment.amount_tiyin,
        "provider": payment.provider,
        "payment_url": payment.payment_url,
        "status": payment.status,
    }


# ── Click webhook ─────────────────────────────────────

@router.post("/payments/click/webhook")
async def click_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Click prepare/complete webhook handler.

    Click application/x-www-form-urlencoded yuboradi.
    """
    form = await request.form()
    payload = {k: v for k, v in form.items()}
    client_ip = request.client.host if request.client else None
    return await handle_click_webhook(payload, client_ip, db)


# ── Payme JSON-RPC webhook ────────────────────────────

class PaymeRPCRequest(BaseModel):
    method: str
    params: dict
    id: Optional[int] = None


def _check_payme_basic_auth(authorization: Optional[str], merchant_key: str) -> bool:
    """Payme Basic auth — login `Paycom`, parol = merchant key."""
    if not authorization or not authorization.startswith("Basic "):
        return False
    try:
        encoded = authorization.split(" ", 1)[1]
        decoded = base64.b64decode(encoded).decode()
        login, password = decoded.split(":", 1)
        # Payme docs: login = "Paycom"
        return password == merchant_key
    except Exception:
        return False


def _payme_error(code: int, message: str, request_id: Optional[int] = None) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


@router.post("/payments/payme/webhook")
async def payme_webhook(
    body: PaymeRPCRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Payme JSON-RPC webhook.

    Methodlar:
      CheckPerformTransaction — to'lov mumkinligini tekshirish (sumdan,
                                  account ma'lumotidan foydalanuvchi mavjudligini)
      CreateTransaction       — tranzaksiya yaratish (DB Payment.external_id ni saqlaymiz)
      PerformTransaction      — to'lovni yakunlash (status=success + plan extension)
      CancelTransaction       — bekor qilish
      CheckTransaction        — tranzaksiya holatini qaytarish
    """
    method = body.method
    params = body.params or {}
    rid = body.id

    # Account ichidan merchant_trans_id ni topish
    account = params.get("account") or {}
    merchant_trans_id = account.get("merchant_trans_id")
    if method != "CheckTransaction" and not merchant_trans_id:
        return _payme_error(-31050, "merchant_trans_id required", rid)

    payment = None
    if merchant_trans_id:
        payment = await get_payment_by_merchant_trans(merchant_trans_id, db)
        if not payment:
            return _payme_error(-31050, "Order not found", rid)

    # Restaurant credentials → Basic auth tekshiruvi
    if payment:
        rest_res = await db.execute(select(Restaurant).where(Restaurant.id == payment.restaurant_id))
        rest = rest_res.scalar_one_or_none()
        if not rest or not rest.payme_secret_key:
            return _payme_error(-32504, "Merchant not configured", rid)
        if not _check_payme_basic_auth(authorization, rest.payme_secret_key):
            return _payme_error(-32504, "Auth failed", rid)

    # Method routing
    if method == "CheckPerformTransaction":
        amount = params.get("amount")
        if amount != payment.amount_tiyin:
            return _payme_error(-31001, "Wrong amount", rid)
        if payment.status not in ("pending", "success"):
            return _payme_error(-31008, "Already processed", rid)
        return {"jsonrpc": "2.0", "id": rid, "result": {"allow": True}}

    if method == "CreateTransaction":
        if payment.status == "success":
            return _payme_error(-31008, "Already paid", rid)
        payment.external_id = params.get("id")
        await db.commit()
        return {
            "jsonrpc": "2.0", "id": rid,
            "result": {
                "create_time": int(__import__("time").time() * 1000),
                "transaction": str(payment.id),
                "state": 1,  # 1 = creating
            },
        }

    if method == "PerformTransaction":
        await mark_payment_success(payment, external_id=params.get("id"), db=db)
        return {
            "jsonrpc": "2.0", "id": rid,
            "result": {
                "transaction": str(payment.id),
                "perform_time": int(__import__("time").time() * 1000),
                "state": 2,  # 2 = perform success
            },
        }

    if method == "CancelTransaction":
        reason = params.get("reason", "user_cancelled")
        await mark_payment_failed(payment, f"Payme cancel: {reason}", db)
        return {
            "jsonrpc": "2.0", "id": rid,
            "result": {
                "transaction": str(payment.id),
                "cancel_time": int(__import__("time").time() * 1000),
                "state": -1,
            },
        }

    if method == "CheckTransaction":
        # CheckTransaction faqat external_id orqali keladi
        ext_id = params.get("id")
        res = await db.execute(select(Payment).where(Payment.external_id == ext_id))
        p = res.scalar_one_or_none()
        if not p:
            return _payme_error(-31003, "Transaction not found", rid)
        state_map = {"pending": 1, "success": 2, "failed": -1}
        return {
            "jsonrpc": "2.0", "id": rid,
            "result": {
                "transaction": str(p.id),
                "state": state_map.get(p.status, 0),
                "create_time": int(p.created_at.timestamp() * 1000) if p.created_at else 0,
                "perform_time": int(p.paid_at.timestamp() * 1000) if p.paid_at else 0,
                "cancel_time": 0,
            },
        }

    return _payme_error(-32601, f"Method not found: {method}", rid)


# ── Test/Mock endpoint ────────────────────────────────

@router.post("/payments/mock/complete")
async def mock_complete_payment(
    merchant_trans_id: str,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Test rejimida to'lovni qo'lda muvaffaqiyatli deb belgilash.

    Faqat development / sandbox uchun. Prod'da bu endpointni o'chirib qo'yish kerak.
    """
    payment = await get_payment_by_merchant_trans(merchant_trans_id, db)
    if not payment:
        raise HTTPException(404, "Payment topilmadi")
    if payment.status == "success":
        return {"already": True, "payment_id": payment.id}
    await mark_payment_success(payment, external_id=f"mock-{payment.id}", db=db)
    return {"success": True, "payment_id": payment.id}
