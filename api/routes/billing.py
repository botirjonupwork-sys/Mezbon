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
from api.auth_deps import require_restaurant_admin, require_super_admin
from api.services.audit import client_ip, log_security
from api.services.billing import (
    create_payment_record, handle_click_webhook,
    get_payment_by_merchant_trans, mark_payment_success, mark_payment_failed,
    tiyin_to_uzs, uzs_to_tiyin,
)
from api.services.subscription import (
    get_billing_status, upgrade_immediate, upgrade_queued,
)
from database.models import Plan, Restaurant, Payment, Order

router = APIRouter(tags=["billing"])


# ── Schemas ──────────────────────────────────────────

class CreateInvoiceRequest(BaseModel):
    plan_id: int
    provider: str  # "click" | "payme"


class UpgradeRequest(BaseModel):
    plan_id: int
    upgrade_type: str   # "immediate" | "queued"
    provider: str = "click"   # Click | Payme — to'lov yaratish uchun


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
        "plans": [_plan_to_dict(p) for p in plans],
    }


def _plan_to_dict(p: Plan) -> dict:
    """Plan obyektni JSON'ga, ochiq/yopiq imkoniyatlar bilan to'liq ro'yxat.

    Frontend `features` arrayni `{label, enabled}` shaklida ko'rsatadi —
    har tarifda nimaga ruxsat bor/yo'qligi vizual ko'rinsin.
    """
    features = [
        {"key": "catering",     "label": "Catering (tadbir)",        "enabled": bool(p.has_catering)},
        {"key": "ai_agent",     "label": "AI Call Operator",         "enabled": bool(p.has_ai_agent)},
        {"key": "yandex",       "label": "Yandex Delivery",          "enabled": bool(p.has_yandex)},
        {"key": "multi_branch", "label": "Bir nechta filial",        "enabled": bool(p.has_multi_branch)},
    ]
    return {
        "id": p.id,
        "name": p.name,
        "slug": p.slug,
        "description": p.description,
        "monthly_price": p.monthly_price,
        "monthly_price_tiyin": uzs_to_tiyin(p.monthly_price or 0),
        "commission_percent": p.commission_percent,
        # Boolean flag'lar (eski frontend uchun backward compat)
        "has_catering": bool(p.has_catering),
        "has_ai_agent": bool(p.has_ai_agent),
        "has_yandex": bool(p.has_yandex),
        "has_multi_branch": bool(p.has_multi_branch),
        # Limitlar
        "order_limit": p.order_limit,             # 0 = cheksiz
        "max_branches_limit": p.max_branches_limit,  # 0 = cheksiz
        # Features array — UI uchun yagona format
        "features": features,
        "is_active": bool(p.is_active),
    }


# ── Billing status (frozen + grace + next plan) ────────

@router.get("/admin/billing/status")
async def billing_status(
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Restoranning to'liq billing holati — joriy tarif, frozen kunlari, navbat,
    grace_period soni, va h.k.

    Frontend Tariflar sahifasida ushbu ma'lumotlarni ko'rsatadi.
    """
    if not restaurant_id:
        raise HTTPException(400, "restaurant_id kerak")
    rest = (await db.execute(
        select(Restaurant).where(Restaurant.id == restaurant_id)
    )).scalar_one_or_none()
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")
    return await get_billing_status(db, restaurant=rest)


# ── Tarifni yangilash (Variant A / Variant B) ──────────

@router.post("/admin/billing/upgrade")
async def upgrade_plan(
    body: UpgradeRequest,
    request: Request,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Tarifni yangilash — 2 variant.

    **Variant A "immediate"**: joriy tarif qolgan kunlari `frozen_days` ga
    saqlanadi, yangi tarif darhol boshlanadi.

    **Variant B "queued"**: yangi tarif uchun to'lov, lekin u eski tarif
    tugagandan keyin avtomatik faollashadi.

    Talablar:
        - Restoran INN tasdiqlangan bo'lishi kerak (`is_verified=True`)
        - Yangi tarif Free emas (Free uchun to'lov yo'q)
        - Yangi tarif joriy tarif bilan bir xil bo'lmasligi kerak
    """
    if not restaurant_id:
        raise HTTPException(400, "restaurant_id kerak")
    if body.upgrade_type not in ("immediate", "queued"):
        raise HTTPException(400, "upgrade_type faqat 'immediate' yoki 'queued'")
    if body.provider not in ("click", "payme"):
        raise HTTPException(400, "provider faqat 'click' yoki 'payme'")

    rest = (await db.execute(
        select(Restaurant).where(Restaurant.id == restaurant_id)
    )).scalar_one_or_none()
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")

    # ── Xavfsizlik: faqat tasdiqlangan restoranlar ────
    if not rest.is_verified:
        await log_security(
            db, action="plan.change", restaurant_id=rest.id,
            actor_username=rest.admin_username,
            ip_address=client_ip(request),
            details={"reason": "not_verified", "requested_plan_id": body.plan_id},
            success=False,
        )
        raise HTTPException(403, {
            "code": "verification_required",
            "message": "Tarif sotib olish uchun INN tasdiqlangan bo'lishi kerak. "
                       "Super-admin bilan bog'laning.",
        })

    # Suspended restoranlar yangilash huquqiga ega — bu ularning yagona yo'li!
    # (Lekin ular allaqachon API'ga kira olmasligi mumkin — middleware'da exception
    # qo'shamiz: /admin/billing/* har doim ochiq.)

    new_plan = (await db.execute(
        select(Plan).where(Plan.id == body.plan_id)
    )).scalar_one_or_none()
    if not new_plan:
        raise HTTPException(404, "Tarif topilmadi")
    if not new_plan.is_active:
        raise HTTPException(400, "Bu tarif faol emas")
    if new_plan.monthly_price <= 0:
        raise HTTPException(400, "Free tarif uchun to'lov talab qilinmaydi")
    if rest.plan_id == new_plan.id and body.upgrade_type == "immediate":
        raise HTTPException(400, "Joriy tarifda allaqachon turibsiz")

    # ── 1. Invoice yaratish ───────────────────────────
    payment = await create_payment_record(
        db,
        restaurant=rest,
        plan=new_plan,
        provider=body.provider,
    )

    # ── 2. Mock rejimda — to'lovni darhol qo'llash ────
    # Real provayder uchun: webhook keldi → mark_payment_success → biz upgrade'ni
    # shu yerga emas, billing.py:mark_payment_success() ichida chaqiramiz (TODO).
    # Hozircha invoice URL qaytaradi va frontend mijozni to'lov sahifasiga jo'natadi.

    # Payment.upgrade_type ni saqlash
    payment.upgrade_type = body.upgrade_type
    await db.commit()

    # ── 3. Audit log ──────────────────────────────────
    await log_security(
        db, action="plan.change", restaurant_id=rest.id,
        actor_username=rest.admin_username,
        ip_address=client_ip(request),
        details={
            "from_plan_id": rest.plan_id,
            "to_plan_id": new_plan.id,
            "upgrade_type": body.upgrade_type,
            "payment_id": payment.id,
            "amount_tiyin": payment.amount_tiyin,
        },
        success=True,
    )

    return {
        "ok": True,
        "payment_id": payment.id,
        "merchant_trans_id": payment.merchant_trans_id,
        "amount_tiyin": payment.amount_tiyin,
        "amount_uzs": tiyin_to_uzs(payment.amount_tiyin),
        "payment_url": payment.payment_url,
        "upgrade_type": body.upgrade_type,
        "message": (
            "To'lov muvaffaqiyatli o'tgach: "
            + ("yangi tarif darhol boshlanadi (joriy kunlari muzlatiladi)."
               if body.upgrade_type == "immediate"
               else "yangi tarif joriy muddat tugagach faollashadi.")
        ),
    }


# ── To'lov muvaffaqiyatli bo'lgach upgrade'ni qo'llash ──
# Bu funksiya billing.py:mark_payment_success() dan keyin chaqiriladi
# (Click/Payme webhook trigger qiladi).

async def apply_upgrade_after_payment(
    db: AsyncSession, payment: Payment,
) -> Optional[dict]:
    """To'lov muvaffaqiyatli bo'lganidan keyin tarif upgrade'ni qo'llash.

    Bu helper'ni `billing.py:mark_payment_success()` ichidan chaqirish kerak
    (kelajakda integratsiya qilamiz). Hozir bu funksiya alohida endpointdan
    yoki test'dan ishlatilishi mumkin.
    """
    if payment.status != "success":
        return None
    rest = (await db.execute(
        select(Restaurant).where(Restaurant.id == payment.restaurant_id)
    )).scalar_one_or_none()
    if not rest:
        return None
    new_plan = (await db.execute(
        select(Plan).where(Plan.id == payment.plan_id)
    )).scalar_one_or_none()
    if not new_plan:
        return None

    if payment.upgrade_type == "queued":
        return await upgrade_queued(
            db, restaurant=rest, new_plan=new_plan, payment_id=payment.id,
        )
    # 'immediate', 'initial', 'renewal' — barchasi darhol qo'llanadi
    return await upgrade_immediate(
        db, restaurant=rest, new_plan=new_plan, payment_id=payment.id,
    )


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


# ── Settlement (restoran moliya) ─────────────────────


@router.get("/admin/billing/settlement")
async def settlement_report(
    date_from: Optional[str] = None,   # YYYY-MM-DD
    date_to: Optional[str] = None,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Restoran moliyaviy hisoboti — bu davrda qancha pul olgan, komissiya qancha.

    Manbalar:
      - Order.payment_status='paid' (Order.paid_amount_tiyin) — to'g'ridan-to'g'ri tushum
      - CommissionPayment — bizning platformaga to'lov hisobi
      - Refund — qaytarib berilgan summa (manfiy)
    """
    from datetime import datetime, timedelta
    from sqlalchemy import func
    from database.models import CommissionPayment, Refund

    if not restaurant_id:
        raise HTTPException(400, "restaurant_id kerak")

    # Davr — default oxirgi 30 kun
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(400, "date_from format: YYYY-MM-DD")
    else:
        dt_from = today - timedelta(days=30)
    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
        except ValueError:
            raise HTTPException(400, "date_to format: YYYY-MM-DD")
    else:
        dt_to = today + timedelta(days=1)

    # Buyurtmalar tushumi (faqat to'langan)
    paid_orders_q = await db.execute(
        select(
            func.count(Order.id),
            func.coalesce(func.sum(Order.paid_amount_tiyin), 0),
        ).where(
            Order.restaurant_id == restaurant_id,
            Order.payment_status.in_(["paid", "partial"]),
            Order.created_at >= dt_from,
            Order.created_at < dt_to,
        )
    )
    orders_count, paid_sum_tiyin = paid_orders_q.one()
    orders_count = int(orders_count or 0)
    paid_sum_uzs = (paid_sum_tiyin or 0) / 100.0

    # Provider taqsimoti
    provider_q = await db.execute(
        select(
            Order.payment_provider,
            func.count(Order.id),
            func.coalesce(func.sum(Order.paid_amount_tiyin), 0),
        ).where(
            Order.restaurant_id == restaurant_id,
            Order.payment_status.in_(["paid", "partial"]),
            Order.created_at >= dt_from,
            Order.created_at < dt_to,
        ).group_by(Order.payment_provider)
    )
    by_provider = [
        {"provider": row[0] or "manual", "count": int(row[1] or 0), "amount_uzs": (row[2] or 0) / 100.0}
        for row in provider_q.all()
    ]

    # Komissiya (bizning platformaga to'lanadigan)
    comm_q = await db.execute(
        select(func.coalesce(func.sum(CommissionPayment.amount), 0)).where(
            CommissionPayment.restaurant_id == restaurant_id,
            CommissionPayment.status == "confirmed",
            CommissionPayment.paid_at >= dt_from,
            CommissionPayment.paid_at < dt_to,
        )
    )
    commission_total_uzs = float(comm_q.scalar() or 0)

    # Refund'lar
    refund_q = await db.execute(
        select(
            func.count(Refund.id),
            func.coalesce(func.sum(Refund.amount_tiyin), 0),
        ).where(
            Refund.restaurant_id == restaurant_id,
            Refund.status == "success",
            Refund.requested_at >= dt_from,
            Refund.requested_at < dt_to,
        )
    )
    refunds_count, refunds_sum_tiyin = refund_q.one()
    refunds_count = int(refunds_count or 0)
    refunds_sum_uzs = (refunds_sum_tiyin or 0) / 100.0

    net_uzs = paid_sum_uzs - refunds_sum_uzs - commission_total_uzs

    return {
        "period": {"from": dt_from.date().isoformat(), "to": (dt_to - timedelta(days=1)).date().isoformat()},
        "orders": {
            "count": orders_count,
            "paid_total_uzs": paid_sum_uzs,
            "by_provider": by_provider,
        },
        "refunds": {
            "count": refunds_count,
            "total_uzs": refunds_sum_uzs,
        },
        "commission_uzs": commission_total_uzs,
        "net_uzs": net_uzs,
    }


@router.get("/admin/billing/settlement.csv")
async def settlement_csv(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Settlement davrida buyurtmalar CSV (har qator: order, summa, komissiya)."""
    from datetime import datetime, timedelta
    from io import StringIO
    import csv
    from fastapi.responses import StreamingResponse
    from database.models import CommissionPayment

    if not restaurant_id:
        raise HTTPException(400, "restaurant_id kerak")

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    dt_from = datetime.strptime(date_from, "%Y-%m-%d") if date_from else today - timedelta(days=30)
    dt_to = (datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)) if date_to else today + timedelta(days=1)

    res = await db.execute(
        select(Order).where(
            Order.restaurant_id == restaurant_id,
            Order.payment_status.in_(["paid", "partial", "refunded", "partial_refund"]),
            Order.created_at >= dt_from,
            Order.created_at < dt_to,
        ).order_by(Order.id)
    )
    orders = res.scalars().all()

    # Commission lookup
    comm_res = await db.execute(
        select(CommissionPayment.order_id, func.coalesce(func.sum(CommissionPayment.amount), 0)).where(
            CommissionPayment.restaurant_id == restaurant_id,
            CommissionPayment.order_id.in_([o.id for o in orders] or [0]),
        ).group_by(CommissionPayment.order_id)
    )
    comm_by_order = {row[0]: float(row[1] or 0) for row in comm_res.all()}

    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(["order_id", "created_at", "payment_method", "payment_provider",
                "payment_status", "paid_uzs", "commission_uzs", "net_uzs"])
    for o in orders:
        paid_uzs = (o.paid_amount_tiyin or 0) / 100.0
        comm = comm_by_order.get(o.id, 0.0)
        w.writerow([
            o.id,
            o.created_at.isoformat() if o.created_at else "",
            o.payment_method or "",
            o.payment_provider or "",
            o.payment_status or "",
            f"{paid_uzs:.2f}",
            f"{comm:.2f}",
            f"{paid_uzs - comm:.2f}",
        ])
    buf.seek(0)
    filename = f"settlement_{dt_from.date()}_{(dt_to - timedelta(days=1)).date()}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Refund endpoints ──────────────────────────────────


class RefundRequest(BaseModel):
    payment_id: Optional[int] = None
    order_id: Optional[int] = None
    amount_tiyin: Optional[int] = None  # None → to'liq
    reason: Optional[str] = ""
    apply_policy: bool = True            # order uchun cancellation policy qo'llaymizmi


@router.post("/admin/billing/refund")
async def refund_payment_endpoint(
    body: RefundRequest,
    db: AsyncSession = Depends(get_db),
    ctx = Depends(require_super_admin),
):
    """Super-admin: SaaS Payment refund yoki Order refund."""
    from api.services.refunds import refund_saas_payment, refund_order

    admin_id = getattr(ctx, "admin_id", None)
    if body.payment_id:
        result = await refund_saas_payment(
            db, payment_id=body.payment_id,
            amount_tiyin=body.amount_tiyin,
            reason=body.reason or "",
            requested_by_admin_id=admin_id,
        )
    elif body.order_id:
        result = await refund_order(
            db, order_id=body.order_id,
            amount_tiyin=body.amount_tiyin,
            reason=body.reason or "",
            requested_by_admin_id=admin_id,
            apply_policy=body.apply_policy,
        )
    else:
        raise HTTPException(400, "payment_id yoki order_id ko'rsatish shart")

    if not result.ok:
        raise HTTPException(400, result.error or "Refund failed")

    return {
        "ok": True,
        "refund_id": result.refund_id,
        "provider_refund_id": result.provider_refund_id,
    }


@router.post("/admin/orders/{order_id}/refund")
async def refund_order_endpoint(
    order_id: int,
    body: RefundRequest,
    db: AsyncSession = Depends(get_db),
    restaurant_id: int = Depends(require_restaurant_admin),
):
    """Restoran admini: o'z buyurtmasini bekor qilish + pul qaytarish."""
    from api.services.refunds import refund_order

    # IDOR himoyasi — order shu restorannikimi
    order = (await db.execute(
        select(Order).where(Order.id == order_id, Order.restaurant_id == restaurant_id)
    )).scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Buyurtma topilmadi")

    result = await refund_order(
        db, order_id=order_id,
        amount_tiyin=body.amount_tiyin,
        reason=body.reason or "",
        apply_policy=body.apply_policy,
    )
    if not result.ok:
        raise HTTPException(400, result.error or "Refund failed")
    return {"ok": True, "refund_id": result.refund_id}


@router.get("/admin/refunds")
async def list_refunds(
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Joriy restoran refund tarixi."""
    from database.models import Refund
    if not restaurant_id:
        return []
    res = await db.execute(
        select(Refund).where(Refund.restaurant_id == restaurant_id).order_by(desc(Refund.requested_at)).limit(100)
    )
    refunds = res.scalars().all()
    return [
        {
            "id": r.id,
            "payment_id": r.payment_id,
            "order_id": r.order_id,
            "amount_uzs": tiyin_to_uzs(r.amount_tiyin),
            "reason": r.reason,
            "status": r.status,
            "provider": r.provider,
            "provider_refund_id": r.provider_refund_id,
            "error_message": r.error_message,
            "requested_at": r.requested_at.isoformat() if r.requested_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in refunds
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

WEBHOOK_MAX_BODY_BYTES = 10 * 1024  # 10KB — webhook payloadlari kichik bo'lishi shart


async def _enforce_webhook_body_size(request: Request) -> None:
    """Webhook body hajmini cheklash (replay/DoS himoyasi)."""
    cl = request.headers.get("content-length")
    if cl:
        try:
            if int(cl) > WEBHOOK_MAX_BODY_BYTES:
                raise HTTPException(413, "Webhook body too large")
        except ValueError:
            pass


@router.post("/payments/click/webhook")
async def click_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Click prepare/complete/reverse webhook handler.

    Click application/x-www-form-urlencoded yuboradi.
    Rate-limit: SlowAPI default (300/min/IP). Body limit: 10KB.
    """
    await _enforce_webhook_body_size(request)
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
    request: Request,
    body: PaymeRPCRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
):
    await _enforce_webhook_body_size(request)
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

    account = params.get("account") or {}

    # ── Dispatch: order vs subscription ──
    # Bizning URL builderlarda:
    #   Subscription: ac.merchant_trans_id=r-...
    #   Order:        ac.order_id=<id>
    # Webhook'da account ichida qaysi field bo'lsa, shu yo'lga ketamiz.
    if account.get("order_id") is not None:
        from database.models import Order
        from api.services.order_webhook import handle_payme_order_method
        try:
            order_id = int(account.get("order_id"))
        except (TypeError, ValueError):
            return _payme_error(-31050, "order_id invalid", rid)
        order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
        if not order:
            return _payme_error(-31050, "Order not found", rid)
        rest_res = await db.execute(select(Restaurant).where(Restaurant.id == order.restaurant_id))
        rest = rest_res.scalar_one_or_none()
        if not rest or not rest.payme_secret_key:
            return _payme_error(-32504, "Merchant not configured", rid)
        if not _check_payme_basic_auth(authorization, rest.payme_secret_key):
            return _payme_error(-32504, "Auth failed", rid)
        return await handle_payme_order_method(method, params, rid, db)

    # ── Subscription oqimi (mavjud) ──
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
        # Allaqachon to'langan bo'lsa — yangi to'lovga ruxsat berma
        if payment.status == "success":
            return _payme_error(-31008, "Already paid", rid)
        if payment.status not in ("pending",):
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
        # Idempotent — agar allaqachon bekor qilingan bo'lsa, ayni javobni qaytaramiz
        if payment.status in ("failed", "refunded"):
            return {
                "jsonrpc": "2.0", "id": rid,
                "result": {
                    "transaction": str(payment.id),
                    "cancel_time": int(payment.created_at.timestamp() * 1000) if payment.created_at else 0,
                    "state": -2 if payment.status == "refunded" else -1,
                },
            }
        # success → refunded (Faza 3 to'liq refund flow)
        was_success = payment.status == "success"
        if was_success:
            payment.status = "refunded"
            await db.commit()
            from api.logging_config import log_critical
            log_critical(
                "payment", "Payme CancelTransaction — payment refunded",
                payment_id=payment.id, restaurant_id=payment.restaurant_id,
                reason=reason,
            )
            try:
                from api.services.notifier import notify_platform_admin
                await notify_platform_admin(
                    f"⚠️ Payme cancel — Payment #{payment.id} qaytarildi (sabab: {reason})"
                )
            except Exception:
                pass
        else:
            await mark_payment_failed(payment, f"Payme cancel: {reason}", db)
        return {
            "jsonrpc": "2.0", "id": rid,
            "result": {
                "transaction": str(payment.id),
                "cancel_time": int(__import__("time").time() * 1000),
                "state": -2 if was_success else -1,  # -2 = paid then cancel, -1 = canceled before perform
            },
        }

    if method == "CheckTransaction":
        # CheckTransaction faqat external_id orqali keladi
        ext_id = params.get("id")
        res = await db.execute(select(Payment).where(Payment.external_id == ext_id))
        p = res.scalar_one_or_none()
        if not p:
            return _payme_error(-31003, "Transaction not found", rid)
        state_map = {"pending": 1, "success": 2, "failed": -1, "refunded": -2}
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

    Faqat development / sandbox uchun. Production'da o'chirilgan
    (ENABLE_MOCK_PAYMENTS=1 env bilan ochiladi).
    """
    import os
    if (os.getenv("ENABLE_MOCK_PAYMENTS", "").lower() not in ("1", "true", "yes")):
        raise HTTPException(403, "Mock to'lov endpointi ishlab chiqarishda o'chirilgan")

    payment = await get_payment_by_merchant_trans(merchant_trans_id, db)
    if not payment:
        raise HTTPException(404, "Payment topilmadi")
    if payment.status == "success":
        return {"already": True, "payment_id": payment.id}
    # SaaS izolatsiya: faqat o'z restoranining payment'ini mark qilsa bo'ladi
    if restaurant_id and payment.restaurant_id != restaurant_id:
        raise HTTPException(403, "Bu to'lov sizning restoraningizniki emas")
    await mark_payment_success(payment, external_id=f"mock-{payment.id}", db=db)
    return {"success": True, "payment_id": payment.id}
