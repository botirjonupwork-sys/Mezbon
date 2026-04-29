"""Super-admin REST API.

Faqat is_superuser=True bo'lgan foydalanuvchilarga ruxsat. Har bir o'zgartirish
amali `super_admin_actions` jadvaliga yoziladi (audit log).

Endpointlar:
    GET    /super-admin/stats             — umumiy statistika (revenue, restaurants, orders)
    GET    /super-admin/restaurants       — barcha restoranlar (plan + balans)
    PATCH  /super-admin/restaurants/{id}  — status / tarif o'zgartirish
    GET    /super-admin/maintenance       — joriy maintenance flag
    PUT    /super-admin/maintenance       — maintenance flag'ni o'zgartirish
    GET    /super-admin/actions           — audit log (so'nggi 100 ta)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.routes.auth import verify_super_token
from api.services import platform
from database.models import (
    Order, OrderStatus, Plan, Restaurant, SuperAdminAction,
)


router = APIRouter(prefix="/super-admin", tags=["super-admin"])


# ── Auth dependency (qisqa muddatli token majburiy) ──────────────────────

async def require_superuser(
    request: Request,
    authorization: str = Header(..., alias="Authorization"),
) -> dict:
    """Faqat qisqa muddatli super-admin tokenini qabul qiladi (eskirgan
    yoki bare-SECRET_KEY token rad etiladi).

    Qaytaradi: payload (`{"u": username, "exp": ..., "is_super": True}`).
    """
    raw = (authorization or "").replace("Bearer ", "").strip()
    payload = verify_super_token(raw)
    if not payload:
        raise HTTPException(401, "Super-admin tokeni yaroqsiz yoki muddati o'tgan")
    return payload


async def _log_action(
    db: AsyncSession,
    actor: str,
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    details: Optional[dict] = None,
    ip: Optional[str] = None,
) -> None:
    """Har bir super-admin amalini audit log'ga yozish."""
    db.add(SuperAdminAction(
        actor=actor or "unknown",
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=json.dumps(details, ensure_ascii=False, default=str) if details else None,
        ip=ip,
    ))
    await db.commit()


def _client_ip(request: Request) -> Optional[str]:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


# ── Schemas ─────────────────────────────────────────────────────────────

class RestaurantPatch(BaseModel):
    status: Optional[str] = None         # 'active' | 'blocked'
    plan_id: Optional[int] = None
    plan_expires_at: Optional[datetime] = None
    extend_days: Optional[int] = None    # plan_expires_at + days
    commission_percent: Optional[float] = None


class MaintenancePatch(BaseModel):
    maintenance_mode: bool
    maintenance_message: Optional[str] = None


# ── Endpoints ───────────────────────────────────────────────────────────

@router.get("/stats")
async def stats(
    days: int = 30,
    actor: dict = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Umumiy platforma statistikasi.

    Args:
        days: oxirgi N kunlik kesim ('series' va 'period_revenue' uchun)
    """
    # Restoranlar
    rest_total = (await db.execute(select(func.count(Restaurant.id)))).scalar() or 0
    rest_active = (await db.execute(
        select(func.count(Restaurant.id)).where(Restaurant.status == "active")
    )).scalar() or 0

    # Buyurtmalar (cancelled tashqari)
    not_cancelled = Order.status != OrderStatus.cancelled
    total_orders = (await db.execute(
        select(func.count(Order.id)).where(not_cancelled)
    )).scalar() or 0
    total_revenue = (await db.execute(
        select(func.sum(Order.total_price)).where(not_cancelled)
    )).scalar() or 0.0

    # Bugungi
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_orders = (await db.execute(
        select(func.count(Order.id)).where(not_cancelled, Order.created_at >= today_start)
    )).scalar() or 0
    today_revenue = (await db.execute(
        select(func.sum(Order.total_price)).where(not_cancelled, Order.created_at >= today_start)
    )).scalar() or 0.0

    # So'nggi N kun seriyasi (kunlik revenue + orders count)
    since = today_start - timedelta(days=max(1, min(days, 365)) - 1)
    series_q = await db.execute(
        select(
            func.date(Order.created_at).label("d"),
            func.coalesce(func.sum(Order.total_price), 0).label("revenue"),
            func.count(Order.id).label("orders"),
        )
        .where(not_cancelled, Order.created_at >= since)
        .group_by(func.date(Order.created_at))
        .order_by(func.date(Order.created_at))
    )
    series = [
        {"date": str(row.d), "revenue": float(row.revenue or 0), "orders": int(row.orders or 0)}
        for row in series_q.all()
    ]

    # Tarif bo'yicha taqsimot
    plan_q = await db.execute(
        select(Plan.slug, func.count(Restaurant.id))
        .join(Restaurant, Restaurant.plan_id == Plan.id, isouter=True)
        .group_by(Plan.slug)
    )
    plan_distribution = {row[0] or "none": int(row[1] or 0) for row in plan_q.all()}

    return {
        "restaurants": {"total": int(rest_total), "active": int(rest_active)},
        "orders": {
            "total": int(total_orders),
            "today": int(today_orders),
        },
        "revenue": {
            "total_uzs": float(total_revenue),
            "today_uzs": float(today_revenue),
        },
        "plan_distribution": plan_distribution,
        "series": series,
        "period_days": days,
    }


@router.get("/restaurants")
async def list_restaurants(
    actor: dict = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Barcha restoranlar — joriy tarif, status, plan_expires_at va tushum."""
    rows = (await db.execute(select(Restaurant).order_by(Restaurant.id))).scalars().all()

    # Har bir restoran uchun summary
    output = []
    for r in rows:
        plan_name = None
        plan_slug = None
        if r.plan_id:
            p_res = await db.execute(select(Plan).where(Plan.id == r.plan_id))
            plan = p_res.scalar_one_or_none()
            if plan:
                plan_name, plan_slug = plan.name, plan.slug

        # Restoran tushumi (cancelled emas)
        revenue = (await db.execute(
            select(func.coalesce(func.sum(Order.total_price), 0))
            .where(Order.restaurant_id == r.id, Order.status != OrderStatus.cancelled)
        )).scalar() or 0.0
        orders_count = (await db.execute(
            select(func.count(Order.id)).where(Order.restaurant_id == r.id)
        )).scalar() or 0

        output.append({
            "id": r.id,
            "name": r.name,
            "slug": r.slug,
            "phone": r.phone,
            "status": r.status or "active",
            "plan_id": r.plan_id,
            "plan_name": plan_name,
            "plan_slug": plan_slug,
            "plan_expires_at": r.plan_expires_at.isoformat() if r.plan_expires_at else None,
            "commission_percent": float(r.commission_percent or 0),
            "revenue_uzs": float(revenue),
            "orders_count": int(orders_count),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    return output


@router.patch("/restaurants/{restaurant_id}")
async def patch_restaurant(
    restaurant_id: int,
    body: RestaurantPatch,
    request: Request,
    actor: dict = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Restoran statusini, tarifini yoki muddatini o'zgartirish."""
    res = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
    rest = res.scalar_one_or_none()
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")

    # Eski qiymatlar (audit uchun)
    before = {
        "status": rest.status,
        "plan_id": rest.plan_id,
        "plan_expires_at": rest.plan_expires_at.isoformat() if rest.plan_expires_at else None,
        "commission_percent": float(rest.commission_percent or 0),
    }

    if body.status is not None:
        if body.status not in ("active", "blocked", "trial"):
            raise HTTPException(400, "Status faqat: active/blocked/trial")
        rest.status = body.status

    if body.plan_id is not None:
        plan_check = await db.execute(select(Plan).where(Plan.id == body.plan_id))
        if not plan_check.scalar_one_or_none():
            raise HTTPException(404, "Tarif topilmadi")
        rest.plan_id = body.plan_id

    if body.plan_expires_at is not None:
        rest.plan_expires_at = body.plan_expires_at

    if body.extend_days is not None:
        days = max(1, min(int(body.extend_days), 365))
        base = rest.plan_expires_at if (rest.plan_expires_at and rest.plan_expires_at > datetime.utcnow()) else datetime.utcnow()
        rest.plan_expires_at = base + timedelta(days=days)

    if body.commission_percent is not None:
        if body.commission_percent < 0 or body.commission_percent > 100:
            raise HTTPException(400, "commission_percent 0..100 oralig'ida bo'lishi kerak")
        rest.commission_percent = body.commission_percent

    await db.commit()
    await db.refresh(rest)

    after = {
        "status": rest.status,
        "plan_id": rest.plan_id,
        "plan_expires_at": rest.plan_expires_at.isoformat() if rest.plan_expires_at else None,
        "commission_percent": float(rest.commission_percent or 0),
    }
    await _log_action(
        db,
        actor=actor.get("u", "super"),
        action="restaurant.update",
        target_type="restaurant",
        target_id=rest.id,
        details={"before": before, "after": after, "patch": body.model_dump(exclude_none=True)},
        ip=_client_ip(request),
    )

    return {"success": True, "restaurant": after}


@router.get("/maintenance")
async def get_maintenance(actor: dict = Depends(require_superuser)):
    return {
        "maintenance_mode": platform.is_maintenance(),
        "maintenance_message": platform.get("maintenance_message"),
    }


@router.put("/maintenance")
async def set_maintenance(
    body: MaintenancePatch,
    request: Request,
    actor: dict = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    before = {
        "maintenance_mode": platform.is_maintenance(),
        "maintenance_message": platform.get("maintenance_message"),
    }
    updates: dict = {"maintenance_mode": bool(body.maintenance_mode)}
    if body.maintenance_message is not None:
        updates["maintenance_message"] = body.maintenance_message
    after = platform.set_many(updates)

    await _log_action(
        db,
        actor=actor.get("u", "super"),
        action="maintenance.set",
        target_type="platform",
        target_id=None,
        details={"before": before, "after": {
            "maintenance_mode": after.get("maintenance_mode"),
            "maintenance_message": after.get("maintenance_message"),
        }},
        ip=_client_ip(request),
    )
    return after


@router.get("/actions")
async def list_actions(
    limit: int = 100,
    actor: dict = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    """So'nggi audit log yozuvlari."""
    limit = max(1, min(int(limit), 500))
    rows = (await db.execute(
        select(SuperAdminAction).order_by(desc(SuperAdminAction.created_at)).limit(limit)
    )).scalars().all()
    return [
        {
            "id": a.id,
            "actor": a.actor,
            "action": a.action,
            "target_type": a.target_type,
            "target_id": a.target_id,
            "details": json.loads(a.details) if a.details else None,
            "ip": a.ip,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in rows
    ]
