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
    """Super-admin tokenini qabul qiladi.

    Qo'llab-quvvatlanadi (faza 1+):
        - JWT (yangi format) — `auth_service.verify_token()`
        - HMAC qisqa muddatli (avvalgi format) — `verify_super_token`

    Bare-SECRET_KEY (legacy) — rad etiladi.

    Qaytaradi: payload `{"u": username, ...}`.
    """
    raw = (authorization or "").replace("Bearer ", "").strip()

    # 1. JWT
    if raw.count(".") == 2:
        from api.services.auth_service import verify_token
        ctx = verify_token(raw, expected_type="access")
        if ctx and ctx.is_super:
            return {"u": ctx.username or "super", "exp": ctx.expires_at, "is_super": True}

    # 2. HMAC qisqa muddatli
    payload = verify_super_token(raw)
    if payload:
        return payload

    raise HTTPException(401, "Super-admin tokeni yaroqsiz yoki muddati o'tgan")


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


# Faza 9: super-admin tomonidan restoran admin login/parol o'zgartirish
class RestaurantAdminCreds(BaseModel):
    admin_username: Optional[str] = None
    admin_password: Optional[str] = None  # eski parolsiz to'g'ridan-to'g'ri yangilanadi


class _RestaurantCreateConfig:
    extra = "ignore"  # form'dan kelgan extra fieldlarni e'tiborsiz qoldirish


class RestaurantCreate(BaseModel):
    model_config = {"extra": "ignore"}
    name: str
    inn: Optional[str] = None     # ixtiyoriy
    phone: Optional[str] = None
    address: Optional[str] = None
    admin_username: str
    admin_password: str
    plan_id: Optional[int] = None
    bot_token: Optional[str] = None
    courier_bot_token: Optional[str] = None
    is_verified: bool = True   # super-admin yaratgani uchun avtomatik tasdiqlangan


# Faza 9: super-admin tomonidan restoran ma'lumotlarini tahrirlash (mahsulotsiz)
class RestaurantInfoPatch(BaseModel):
    model_config = {"extra": "ignore"}
    name: Optional[str] = None
    inn: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    logo_url: Optional[str] = None
    catering_payment_card: Optional[str] = None
    catering_payment_owner: Optional[str] = None
    is_verified: Optional[bool] = None
    # Bot tokenlari va lokatsiya/ish vaqti — to'liq tahrir uchun
    bot_token: Optional[str] = None
    courier_bot_token: Optional[str] = None
    restaurant_lat: Optional[float] = None
    restaurant_lon: Optional[float] = None
    work_hours_from: Optional[str] = None
    work_hours_until: Optional[str] = None
    min_order: Optional[float] = None
    delivery_base_fee: Optional[float] = None
    delivery_per_km: Optional[float] = None
    # Admin login (parolsiz) — admin_password alohida endpoint orqali
    admin_username: Optional[str] = None


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
            # Faza 9: ma'lumotlar tahriri va credentials uchun
            "admin_username": r.admin_username,
            "inn": r.inn,
            "address": r.address,
            "logo_url": r.logo_url,
            "is_verified": bool(r.is_verified),
            "catering_payment_card": r.catering_payment_card,
            "catering_payment_owner": r.catering_payment_owner,
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

    plan_changed_propagation: dict = {}
    if body.plan_id is not None:
        new_plan = (await db.execute(
            select(Plan).where(Plan.id == body.plan_id)
        )).scalar_one_or_none()
        if not new_plan:
            raise HTTPException(404, "Tarif topilmadi")
        old_plan_id = rest.plan_id
        rest.plan_id = body.plan_id
        # Tarif o'zgarganda filiallar va featurelarni avtomatik moslashtirish
        plan_changed_propagation = await _propagate_plan_change(
            db, restaurant=rest, new_plan=new_plan,
        )
        plan_changed_propagation["from_plan_id"] = old_plan_id
        plan_changed_propagation["to_plan_id"] = new_plan.id

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
        details={
            "before": before, "after": after,
            "patch": body.model_dump(exclude_none=True),
            "plan_propagation": plan_changed_propagation or None,
        },
        ip=_client_ip(request),
    )

    return {
        "success": True,
        "restaurant": after,
        "plan_propagation": plan_changed_propagation or None,
    }


# ── Plan → branch/feature propagation ────────────────────────────────────

async def _propagate_plan_change(
    db: AsyncSession,
    *,
    restaurant: Restaurant,
    new_plan: Plan,
) -> dict:
    """Tarif o'zgarganda restoranning filial va featurelarini moslashtirish.

    Qoidalar:
        - Yangi tarif `has_multi_branch=False` va `max_branches_limit < N` bo'lsa
          → ortiqcha filiallar deactivate qilinadi (eng yangidan boshlab)
        - Yangi tarif `has_catering=False` bo'lsa → restoran sozlamasidagi
          catering bayroqchalari (mavjud bo'lsa) o'chiriladi (UX uchun emas, faqat audit)
        - Yangi tarif `has_ai_agent=False` bo'lsa → `ai_agent_enabled=False`
        - Yangi tarif `has_yandex=False` bo'lsa → `delivery_provider`'ni `own`'ga qaytarish

    Audit log uchun har propagation aksiyasini detalsiz emas, summary'da qaytaradi.
    """
    from database.models import Branch
    summary: dict[str, list[int] | bool] = {}

    # ── 1. Multi-branch limit ─────────────────────────────
    branches = (await db.execute(
        select(Branch).where(Branch.restaurant_id == restaurant.id)
        .order_by(Branch.created_at.desc())
    )).scalars().all()
    active_branches = [b for b in branches if b.is_active]

    limit = int(new_plan.max_branches_limit or 0)
    # has_multi_branch False → faqat 1 ta filial qoladi
    if not new_plan.has_multi_branch:
        limit = 1
    # 0 = cheksiz, qolganda chegaraga moslashtirish
    deactivated: list[int] = []
    if limit > 0 and len(active_branches) > limit:
        # Eng yangi yaratilgan filiallarni deactivate (eng eskilari saqlanadi)
        # Reverse — eng yangidan boshlab limit'gacha
        keep_count = limit
        sorted_old_first = sorted(active_branches, key=lambda b: b.created_at or datetime.min)
        for i, b in enumerate(sorted_old_first):
            if i >= keep_count:
                b.is_active = False
                deactivated.append(b.id)
    summary["branches_deactivated"] = deactivated
    summary["multi_branch_allowed"] = bool(new_plan.has_multi_branch)
    summary["max_branches_limit"] = limit

    # ── 2. AI Operator ───────────────────────────────────
    if not new_plan.has_ai_agent and restaurant.ai_agent_enabled:
        restaurant.ai_agent_enabled = False
        summary["ai_agent_disabled"] = True

    # ── 3. Yandex Delivery ───────────────────────────────
    if not new_plan.has_yandex and (restaurant.delivery_provider or "").lower() == "yandex":
        restaurant.delivery_provider = "own"
        summary["yandex_disabled"] = True

    # 4. Catering — restaurant level'da alohida bayroq yo'q,
    # _ensure_catering_enabled barcha endpointlarda to'g'ridan-to'g'ri tekshiradi
    summary["catering_allowed"] = bool(new_plan.has_catering)

    await db.commit()
    return summary


@router.get("/restaurants/{restaurant_id}")
async def get_restaurant_full(
    restaurant_id: int,
    actor: dict = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Bitta restoran to'liq ma'lumotlari (super-admin tahriri uchun)."""
    rest = await db.get(Restaurant, restaurant_id)
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")
    return {
        "id": rest.id,
        "name": rest.name,
        "slug": rest.slug,
        "inn": rest.inn,
        "phone": rest.phone,
        "address": rest.address,
        "logo_url": rest.logo_url,
        "admin_username": rest.admin_username,
        "is_verified": bool(rest.is_verified),
        "status": rest.status,
        "subscription_status": rest.subscription_status,
        "plan_id": rest.plan_id,
        "commission_percent": float(rest.commission_percent or 0),
        "plan_expires_at": rest.plan_expires_at.isoformat() if rest.plan_expires_at else None,
        "bot_token": rest.bot_token,
        "courier_bot_token": rest.courier_bot_token,
        "catering_payment_card": rest.catering_payment_card,
        "catering_payment_owner": rest.catering_payment_owner,
        "restaurant_lat": rest.restaurant_lat,
        "restaurant_lon": rest.restaurant_lon,
        "work_hours_from": rest.work_hours_from,
        "work_hours_until": rest.work_hours_until,
        "min_order": rest.min_order,
        "delivery_base_fee": rest.delivery_base_fee,
        "delivery_per_km": rest.delivery_per_km,
    }


# ── Yangi restoran yaratish (Faza 10) ────────────────


@router.post("/restaurants")
async def create_restaurant(
    body: RestaurantCreate,
    actor: dict = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Super-admin: yangi restoran qo'shish (registration emas, manual).

    - INN va admin_username unique bo'lishi shart
    - Avtomatik `is_verified=True` (super-admin yaratayapti)
    - Default plan: Free (yoki ko'rsatilgan)
    - Bot tokeni ixtiyoriy (keyin Settings'dan ham qo'shish mumkin)
    """
    import hashlib, re
    from database.models import Plan

    # 1) INN unique (agar berilgan bo'lsa)
    if body.inn and body.inn.strip():
        existing_inn = (await db.execute(
            select(Restaurant).where(Restaurant.inn == body.inn.strip())
        )).scalar_one_or_none()
        if existing_inn:
            raise HTTPException(409, "Bu INN bilan restoran allaqachon mavjud")

    # 2) Username unique
    existing_user = (await db.execute(
        select(Restaurant).where(Restaurant.admin_username == body.admin_username)
    )).scalar_one_or_none()
    if existing_user:
        raise HTTPException(409, "Bu admin login allaqachon band")

    # 3) Slug yaratish (nomdan)
    base_slug = re.sub(r'[^a-z0-9-]', '', body.name.lower().replace(' ', '-'))[:40] or "restaurant"
    slug = base_slug
    suffix = 1
    while True:
        e = (await db.execute(select(Restaurant).where(Restaurant.slug == slug))).scalar_one_or_none()
        if not e: break
        suffix += 1
        slug = f"{base_slug}-{suffix}"

    # 4) Plan default: Free
    plan_id = body.plan_id
    if not plan_id:
        free_plan = (await db.execute(select(Plan).where(Plan.slug == "free"))).scalar_one_or_none()
        plan_id = free_plan.id if free_plan else None

    # 5) Yaratish
    rest = Restaurant(
        name=body.name,
        slug=slug,
        inn=(body.inn.strip() if (body.inn and body.inn.strip()) else None),
        phone=body.phone,
        address=body.address,
        admin_username=body.admin_username,
        admin_password_hash=hashlib.sha256(body.admin_password.encode()).hexdigest(),
        plan_id=plan_id,
        bot_token=body.bot_token or None,
        courier_bot_token=body.courier_bot_token or None,
        is_verified=body.is_verified,
        status="active",
        subscription_status="active",
    )
    db.add(rest)
    await db.commit()
    await db.refresh(rest)

    await _log_action(
        db, actor=actor.get("username") or "super",
        action="restaurant.created",
        target_type="restaurant", target_id=rest.id,
        details={
            "name": rest.name, "inn": rest.inn, "slug": rest.slug,
            "admin_username": rest.admin_username,
            "has_bot_token": bool(rest.bot_token),
        },
    )

    return {
        "success": True,
        "restaurant": {
            "id": rest.id, "name": rest.name, "slug": rest.slug,
            "inn": rest.inn, "admin_username": rest.admin_username,
            "is_verified": rest.is_verified,
        },
        "next_steps": [
            "Filial qo'shing (har restoranda kamida 1 ta filial bo'lishi shart)",
            "Bot tokenini sozlang (BotFather'dan oling)",
            "Bots service'ni qayta ishga tushiring (yangi tokenlarni o'qish uchun)",
        ],
    }


# ── Restoran admin login/parol (Faza 9) ──────────────


@router.put("/restaurants/{restaurant_id}/credentials")
async def set_restaurant_credentials(
    restaurant_id: int,
    body: RestaurantAdminCreds,
    actor: dict = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Super-admin: restoran admin login va parolini to'g'ridan-to'g'ri o'zgartirish.

    Eski parol so'ralmaydi (super-admin huquqi). Audit log'ga yozuv tushadi.
    """
    import hashlib
    res = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
    rest = res.scalar_one_or_none()
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")

    changes = []
    if body.admin_username:
        # Username unique tekshirish
        existing = (await db.execute(
            select(Restaurant).where(
                Restaurant.admin_username == body.admin_username,
                Restaurant.id != rest.id,
            )
        )).scalar_one_or_none()
        if existing:
            raise HTTPException(409, "Bu login band — boshqa nom tanlang")
        rest.admin_username = body.admin_username
        changes.append("admin_username")

    if body.admin_password:
        rest.admin_password_hash = hashlib.sha256(body.admin_password.encode()).hexdigest()
        changes.append("admin_password")

    if not changes:
        raise HTTPException(400, "admin_username yoki admin_password ko'rsatish shart")

    await db.commit()
    await _log_action(
        db, actor=actor.get("username") or "super",
        action="restaurant.credentials_changed",
        target_type="restaurant", target_id=rest.id,
        details={"changes": changes, "username": rest.admin_username},
    )
    return {"success": True, "changed": changes, "username": rest.admin_username}


@router.delete("/restaurants/{restaurant_id}")
async def soft_delete_restaurant(
    restaurant_id: int,
    actor: dict = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Restoranni "blocked" qilish (soft delete).

    DB'dan o'chirilmaydi (audit, moliyaviy tarix saqlanadi). status='blocked'
    qo'yiladi, bot tokenlari tozalanadi (bot to'xtaydi). Tiklash uchun
    PATCH /restaurants/{id} bilan status='active' qilish mumkin.
    """
    rest = await db.get(Restaurant, restaurant_id)
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")

    rest.status = "blocked"
    # Bot tokenlarini saqlash, lekin bot service o'qiganda blocked'larni o'tkazib yuboradi
    await db.commit()

    await _log_action(
        db, actor=actor.get("username") or "super",
        action="restaurant.soft_deleted",
        target_type="restaurant", target_id=rest.id,
        details={"name": rest.name, "inn": rest.inn},
    )
    return {"success": True, "message": f"Restoran #{restaurant_id} bloklandi (tiklash mumkin)"}


@router.put("/restaurants/{restaurant_id}/info")
async def update_restaurant_info(
    restaurant_id: int,
    body: RestaurantInfoPatch,
    actor: dict = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Super-admin: restoran asosiy ma'lumotlarini tahrirlash (mahsulotsiz)."""
    res = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
    rest = res.scalar_one_or_none()
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")

    changes = []
    editable_fields = (
        "name", "inn", "phone", "address", "logo_url",
        "catering_payment_card", "catering_payment_owner", "is_verified",
        "bot_token", "courier_bot_token",
        "restaurant_lat", "restaurant_lon",
        "work_hours_from", "work_hours_until",
        "min_order", "delivery_base_fee", "delivery_per_km",
        "admin_username",
    )
    for field in editable_fields:
        val = getattr(body, field, None)
        if val is not None:
            setattr(rest, field, val)
            changes.append(field)

    if not changes:
        raise HTTPException(400, "Hech bir maydon ko'rsatilmadi")

    await db.commit()
    await _log_action(
        db, actor=actor.get("username") or "super",
        action="restaurant.info_updated",
        target_type="restaurant", target_id=rest.id,
        details={"changes": changes},
    )
    return {"success": True, "changed": changes}


# ── Financial Dashboard (Faza 5) ───────────────────────


@router.get("/finance/summary")
async def finance_summary(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    actor: dict = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Platforma moliyaviy hisoboti — daromad, tarif taqsimoti, top-10 restoranlar."""
    from datetime import timedelta
    from database.models import CommissionPayment, Payment, Refund

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    dt_from = datetime.strptime(date_from, "%Y-%m-%d") if date_from else today - timedelta(days=30)
    dt_to = (datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)) if date_to else today + timedelta(days=1)

    # 1. Jami komissiya daromadi (platforma)
    total_commission_q = await db.execute(
        select(func.coalesce(func.sum(CommissionPayment.amount), 0)).where(
            CommissionPayment.status == "confirmed",
            CommissionPayment.paid_at >= dt_from,
            CommissionPayment.paid_at < dt_to,
        )
    )
    total_commission_uzs = float(total_commission_q.scalar() or 0)

    # 2. SaaS tarif tushumi (Payment.status='success')
    saas_q = await db.execute(
        select(func.coalesce(func.sum(Payment.amount_tiyin), 0), func.count(Payment.id)).where(
            Payment.status == "success",
            Payment.paid_at >= dt_from,
            Payment.paid_at < dt_to,
        )
    )
    saas_sum_tiyin, saas_count = saas_q.one()
    saas_uzs = (saas_sum_tiyin or 0) / 100.0

    # 3. Top-10 restoranlar (komissiya bo'yicha)
    top_q = await db.execute(
        select(
            Restaurant.id, Restaurant.name,
            func.coalesce(func.sum(CommissionPayment.amount), 0).label("comm"),
            func.coalesce(func.sum(CommissionPayment.orders_revenue), 0).label("rev"),
        )
        .join(CommissionPayment, CommissionPayment.restaurant_id == Restaurant.id)
        .where(
            CommissionPayment.status == "confirmed",
            CommissionPayment.paid_at >= dt_from,
            CommissionPayment.paid_at < dt_to,
        )
        .group_by(Restaurant.id, Restaurant.name)
        .order_by(func.sum(CommissionPayment.amount).desc())
        .limit(10)
    )
    top_restaurants = [
        {"id": row[0], "name": row[1], "commission_uzs": float(row[2] or 0), "revenue_uzs": float(row[3] or 0)}
        for row in top_q.all()
    ]

    # 4. Tarif bo'yicha taqsimot (joriy holat — restoranlar soni)
    plan_q = await db.execute(
        select(Plan.slug, Plan.monthly_price, func.count(Restaurant.id))
        .join(Restaurant, Restaurant.plan_id == Plan.id, isouter=True)
        .group_by(Plan.slug, Plan.monthly_price)
    )
    plans_dist = [
        {"plan": row[0] or "none", "monthly_price": float(row[1] or 0), "restaurants": int(row[2] or 0)}
        for row in plan_q.all()
    ]

    # 5. Refund'lar (umumiy hajm)
    refund_q = await db.execute(
        select(
            func.count(Refund.id),
            func.coalesce(func.sum(Refund.amount_tiyin), 0),
        ).where(
            Refund.status == "success",
            Refund.requested_at >= dt_from,
            Refund.requested_at < dt_to,
        )
    )
    refund_count, refund_tiyin = refund_q.one()
    refund_uzs = (refund_tiyin or 0) / 100.0

    # 6. Provider taqsimoti
    prov_q = await db.execute(
        select(
            Order.payment_provider,
            func.count(Order.id),
            func.coalesce(func.sum(Order.paid_amount_tiyin), 0),
        ).where(
            Order.payment_status.in_(["paid", "partial"]),
            Order.created_at >= dt_from,
            Order.created_at < dt_to,
        ).group_by(Order.payment_provider)
    )
    by_provider = [
        {"provider": row[0] or "manual", "orders": int(row[1] or 0), "amount_uzs": (row[2] or 0) / 100.0}
        for row in prov_q.all()
    ]

    # 7. Kunlik seriya (commission by day)
    series_q = await db.execute(
        select(
            func.date(CommissionPayment.paid_at).label("d"),
            func.coalesce(func.sum(CommissionPayment.amount), 0).label("comm"),
            func.count(CommissionPayment.id).label("count"),
        )
        .where(
            CommissionPayment.status == "confirmed",
            CommissionPayment.paid_at >= dt_from,
            CommissionPayment.paid_at < dt_to,
        )
        .group_by(func.date(CommissionPayment.paid_at))
        .order_by(func.date(CommissionPayment.paid_at))
    )
    daily_series = [
        {"date": str(row.d), "commission_uzs": float(row.comm or 0), "count": int(row.count or 0)}
        for row in series_q.all()
    ]

    return {
        "period": {"from": dt_from.date().isoformat(), "to": (dt_to - timedelta(days=1)).date().isoformat()},
        "platform_revenue": {
            "commission_uzs": total_commission_uzs,
            "saas_uzs": saas_uzs,
            "saas_payments_count": int(saas_count or 0),
            "total_uzs": total_commission_uzs + saas_uzs,
        },
        "refunds": {"count": int(refund_count or 0), "total_uzs": refund_uzs},
        "top_restaurants": top_restaurants,
        "plan_distribution": plans_dist,
        "by_provider": by_provider,
        "daily_series": daily_series,
    }


@router.get("/analytics/payments")
async def payment_analytics(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    actor: dict = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    """To'lov analitikasi — conversion, AOV, failure reasons, provayder taqqoslash."""
    from datetime import timedelta
    from database.models import Payment

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    dt_from = datetime.strptime(date_from, "%Y-%m-%d") if date_from else today - timedelta(days=30)
    dt_to = (datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)) if date_to else today + timedelta(days=1)

    # ── Conversion rate (orders created → paid) ─────────
    total_orders_q = await db.execute(
        select(func.count(Order.id)).where(
            Order.created_at >= dt_from,
            Order.created_at < dt_to,
        )
    )
    total_orders = int(total_orders_q.scalar() or 0)

    paid_orders_q = await db.execute(
        select(func.count(Order.id)).where(
            Order.created_at >= dt_from,
            Order.created_at < dt_to,
            Order.payment_status.in_(["paid", "partial"]),
        )
    )
    paid_orders = int(paid_orders_q.scalar() or 0)

    cancelled_orders_q = await db.execute(
        select(func.count(Order.id)).where(
            Order.created_at >= dt_from,
            Order.created_at < dt_to,
            Order.status == OrderStatus.cancelled,
        )
    )
    cancelled_orders = int(cancelled_orders_q.scalar() or 0)

    conversion_rate = (paid_orders / total_orders * 100) if total_orders > 0 else 0.0
    cancellation_rate = (cancelled_orders / total_orders * 100) if total_orders > 0 else 0.0

    # ── AOV (Average Order Value) ───────────────────────
    aov_q = await db.execute(
        select(func.coalesce(func.avg(Order.paid_amount_tiyin), 0)).where(
            Order.created_at >= dt_from,
            Order.created_at < dt_to,
            Order.payment_status.in_(["paid", "partial"]),
            Order.paid_amount_tiyin > 0,
        )
    )
    aov_uzs = (aov_q.scalar() or 0) / 100.0

    # ── Failure / cancel sabablar (Order status taqsimoti) ─
    status_q = await db.execute(
        select(Order.status, func.count(Order.id)).where(
            Order.created_at >= dt_from,
            Order.created_at < dt_to,
        ).group_by(Order.status)
    )
    by_status = {(row[0].value if row[0] else "unknown"): int(row[1]) for row in status_q.all()}

    # ── Payment status taqsimoti (pending vs paid vs cancelled vs refunded) ─
    pstatus_q = await db.execute(
        select(Order.payment_status, func.count(Order.id)).where(
            Order.created_at >= dt_from,
            Order.created_at < dt_to,
        ).group_by(Order.payment_status)
    )
    by_payment_status = {(row[0] or "unknown"): int(row[1]) for row in pstatus_q.all()}

    # ── Provayder taqqoslash (success rate per provider) ─
    prov_q = await db.execute(
        select(
            Order.payment_provider,
            func.count(Order.id).label("total"),
            func.sum(
                func.cast(Order.payment_status.in_(["paid", "partial"]), sa_int_type())
            ).label("paid"),
        ).where(
            Order.created_at >= dt_from,
            Order.created_at < dt_to,
            Order.payment_method.in_(["card", "telegram"]),
        ).group_by(Order.payment_provider)
    )
    by_provider = []
    for row in prov_q.all():
        total = int(row[1] or 0)
        paid = int(row[2] or 0)
        by_provider.append({
            "provider": row[0] or "unknown",
            "total": total,
            "paid": paid,
            "success_rate_pct": (paid / total * 100) if total > 0 else 0.0,
        })

    # ── SaaS Payment failure reasons ────────────────────
    saas_failed_q = await db.execute(
        select(Payment.error_message, func.count(Payment.id)).where(
            Payment.created_at >= dt_from,
            Payment.created_at < dt_to,
            Payment.status == "failed",
        ).group_by(Payment.error_message).order_by(func.count(Payment.id).desc()).limit(10)
    )
    saas_failure_reasons = [
        {"reason": (row[0] or "unknown")[:120], "count": int(row[1])}
        for row in saas_failed_q.all()
    ]

    # ── Soatlik tahlil (oxirgi 24 soat ichida) ──────────
    last_24h = today - timedelta(days=1)
    hourly_q = await db.execute(
        select(
            func.strftime("%H", Order.created_at).label("hour"),
            func.count(Order.id),
            func.sum(
                func.cast(Order.payment_status.in_(["paid", "partial"]), sa_int_type())
            ),
        ).where(
            Order.created_at >= last_24h,
        ).group_by("hour").order_by("hour")
    )
    by_hour = [
        {"hour": int(row[0]), "orders": int(row[1] or 0), "paid": int(row[2] or 0)}
        for row in hourly_q.all() if row[0] is not None
    ]

    return {
        "period": {"from": dt_from.date().isoformat(), "to": (dt_to - timedelta(days=1)).date().isoformat()},
        "orders": {
            "total": total_orders,
            "paid": paid_orders,
            "cancelled": cancelled_orders,
            "conversion_rate_pct": round(conversion_rate, 2),
            "cancellation_rate_pct": round(cancellation_rate, 2),
        },
        "aov_uzs": round(aov_uzs, 2),
        "by_status": by_status,
        "by_payment_status": by_payment_status,
        "by_provider": by_provider,
        "saas_failure_reasons": saas_failure_reasons,
        "by_hour_24h": by_hour,
    }


def sa_int_type():
    """SQLAlchemy Integer type — multi-dialect safe boolean→int cast."""
    from sqlalchemy import Integer
    return Integer()


@router.get("/finance/summary.csv")
async def finance_summary_csv(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    actor: dict = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Platforma daromad CSV — har commission_payment yozuvini eksport qiladi."""
    from datetime import timedelta
    from io import StringIO
    import csv
    from fastapi.responses import StreamingResponse
    from database.models import CommissionPayment

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    dt_from = datetime.strptime(date_from, "%Y-%m-%d") if date_from else today - timedelta(days=30)
    dt_to = (datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)) if date_to else today + timedelta(days=1)

    res = await db.execute(
        select(CommissionPayment, Restaurant.name)
        .join(Restaurant, Restaurant.id == CommissionPayment.restaurant_id)
        .where(
            CommissionPayment.paid_at >= dt_from,
            CommissionPayment.paid_at < dt_to,
        )
        .order_by(CommissionPayment.id)
    )
    rows = res.all()

    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "restaurant", "paid_at", "amount_uzs", "commission_pct",
                "orders_revenue_uzs", "order_id", "status", "note"])
    for cp, rest_name in rows:
        w.writerow([
            cp.id, rest_name,
            cp.paid_at.isoformat() if cp.paid_at else "",
            f"{float(cp.amount or 0):.2f}",
            f"{float(cp.commission_percent or 0):.2f}",
            f"{float(cp.orders_revenue or 0):.2f}",
            cp.order_id or "",
            cp.status or "",
            cp.note or "",
        ])
    buf.seek(0)
    filename = f"platform_finance_{dt_from.date()}_{(dt_to - timedelta(days=1)).date()}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/monitoring/webhooks")
async def webhook_monitoring(
    window_seconds: int = 3600,
    actor: dict = Depends(require_superuser),
):
    """Webhook latency va success-rate monitoring (Faza 7)."""
    from api.services import webhook_metrics
    return {
        "window_seconds": window_seconds,
        "endpoints": webhook_metrics.get_all_stats(window_seconds),
        "anomalies": webhook_metrics.detect_anomalies(window_seconds),
    }


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
