"""Branch (Filial) endpointlari — CRUD va bot uchun yaqin filiallar"""
import math
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from pydantic import BaseModel
from datetime import datetime
from zoneinfo import ZoneInfo

from api.database import get_db
from api.auth_deps import require_super_admin, require_restaurant_admin, get_restaurant_context
from database.models import Branch, Plan, Restaurant

router = APIRouter(tags=["branches"])

UZ_TZ = ZoneInfo("Asia/Tashkent")


# ── Schemas ──────────────────────────────────────────

class BranchCreate(BaseModel):
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    work_hours_from: str = "09:00"
    work_hours_until: str = "22:00"
    min_order: float = 30000
    delivery_base_fee: float = 10000
    delivery_per_km: float = 3000


class BranchUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    work_hours_from: Optional[str] = None
    work_hours_until: Optional[str] = None
    min_order: Optional[float] = None
    delivery_base_fee: Optional[float] = None
    delivery_per_km: Optional[float] = None
    is_active: Optional[bool] = None


class BranchOut(BaseModel):
    id: int
    restaurant_id: int
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    work_hours_from: str
    work_hours_until: str
    min_order: float
    delivery_base_fee: float
    delivery_per_km: float
    is_active: bool

    class Config:
        from_attributes = True


# ── Yordamchi funksiyalar ────────────────────────────

def _haversine(lat1, lon1, lat2, lon2) -> float:
    """Ikki nuqta orasidagi masofani km da hisoblash."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _is_branch_open(branch: Branch) -> bool:
    """Filial hozir ochiqmi."""
    try:
        now = datetime.now(UZ_TZ).strftime("%H:%M")
        return branch.work_hours_from <= now <= branch.work_hours_until
    except Exception:
        return True


# ── Super Admin: Branch CRUD ────────────────────────

@router.get("/super/restaurants/{restaurant_id}/branches")
async def list_branches(restaurant_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Branch)
        .where(Branch.restaurant_id == restaurant_id)
        .order_by(Branch.id)
    )
    branches = result.scalars().all()
    return [
        {
            "id": b.id,
            "restaurant_id": b.restaurant_id,
            "name": b.name,
            "address": b.address,
            "phone": b.phone,
            "latitude": b.latitude,
            "longitude": b.longitude,
            "work_hours_from": b.work_hours_from,
            "work_hours_until": b.work_hours_until,
            "min_order": b.min_order,
            "delivery_base_fee": b.delivery_base_fee,
            "delivery_per_km": b.delivery_per_km,
            "is_active": b.is_active,
            "is_open": _is_branch_open(b),
        }
        for b in branches
    ]


async def _check_branch_quota(db: AsyncSession, rest: Restaurant) -> None:
    """Tarif bo'yicha filiallar sonini tekshirish.

    Free → 1 filial, Basic → 3, Pro → 10 (Plan.max_branches_limit dan o'qiladi).
    """
    if not rest.plan_id:
        # Plan yo'q — Free deb hisoblaymiz
        max_branches = 1
    else:
        plan = await db.get(Plan, rest.plan_id)
        max_branches = (plan.max_branches_limit or 1) if plan else 1

    current_count = (await db.execute(
        select(func.count(Branch.id)).where(Branch.restaurant_id == rest.id)
    )).scalar() or 0

    if current_count >= max_branches:
        raise HTTPException(403, {
            "code": "branch_limit_reached",
            "message": f"Tarif bo'yicha maksimal filiallar soniga yetdingiz "
                       f"({current_count}/{max_branches}). Tarifni yuqoriga ko'taring.",
            "current": current_count,
            "limit": max_branches,
        })


@router.post("/super/restaurants/{restaurant_id}/branches")
async def create_branch_super(
    restaurant_id: int,
    data: BranchCreate,
    actor: dict = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Super-admin: har qaysi restoran uchun filial qo'shish (tarif limitisiz)."""
    rest = await db.get(Restaurant, restaurant_id)
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")

    branch = Branch(
        restaurant_id=restaurant_id,
        name=data.name,
        address=data.address,
        phone=data.phone,
        latitude=data.latitude,
        longitude=data.longitude,
        work_hours_from=data.work_hours_from,
        work_hours_until=data.work_hours_until,
        min_order=data.min_order,
        delivery_base_fee=data.delivery_base_fee,
        delivery_per_km=data.delivery_per_km,
    )
    db.add(branch)
    await db.commit()
    await db.refresh(branch)
    return {"id": branch.id, "name": branch.name}


@router.post("/admin/branches")
async def create_branch_admin(
    data: BranchCreate,
    rid: int = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Restoran admin: o'z restoraniga yangi filial qo'shish.

    Tarif chegarasi (max_branches_limit) tekshiriladi. Faza 10 audit.
    """
    rest = await db.get(Restaurant, rid)
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")

    # Tarif limiti tekshiruvi
    await _check_branch_quota(db, rest)

    branch = Branch(
        restaurant_id=rid,
        name=data.name,
        address=data.address,
        phone=data.phone,
        latitude=data.latitude,
        longitude=data.longitude,
        work_hours_from=data.work_hours_from,
        work_hours_until=data.work_hours_until,
        min_order=data.min_order,
        delivery_base_fee=data.delivery_base_fee,
        delivery_per_km=data.delivery_per_km,
    )
    db.add(branch)
    await db.commit()
    await db.refresh(branch)
    return {"id": branch.id, "name": branch.name}


@router.put("/super/branches/{branch_id}")
async def update_branch(
    branch_id: int,
    data: BranchUpdate,
    actor: dict = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    branch = await db.get(Branch, branch_id)
    if not branch:
        raise HTTPException(404, "Filial topilmadi")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(branch, field, value)

    await db.commit()
    await db.refresh(branch)
    return {"success": True, "id": branch.id}


@router.delete("/super/branches/{branch_id}")
async def delete_branch(
    branch_id: int,
    actor: dict = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    branch = await db.get(Branch, branch_id)
    if not branch:
        raise HTTPException(404, "Filial topilmadi")

    await db.delete(branch)
    await db.commit()
    return {"success": True}


# ── Admin Panel: Branch API ─────────────────────────

@router.get("/admin/branches")
async def admin_list_branches(
    restaurant_id: int = Depends(get_restaurant_context),
    db: AsyncSession = Depends(get_db),
):
    """Restoran admin: o'z filiallari. IDOR himoyasi via get_restaurant_context."""
    result = await db.execute(
        select(Branch)
        .where(Branch.restaurant_id == restaurant_id, Branch.is_active == True)
        .order_by(Branch.id)
    )
    branches = result.scalars().all()
    return [
        {
            "id": b.id,
            "name": b.name,
            "address": b.address,
            "phone": b.phone,
            "is_open": _is_branch_open(b),
        }
        for b in branches
    ]


@router.get("/admin/branches/{branch_id}/settings")
async def get_branch_settings(
    branch_id: int,
    rid: int = Depends(get_restaurant_context),
    db: AsyncSession = Depends(get_db),
):
    branch = await db.get(Branch, branch_id)
    if not branch:
        raise HTTPException(404, "Filial topilmadi")
    # IDOR: filial joriy restoraniga tegishli bo'lishi shart
    if branch.restaurant_id != rid:
        raise HTTPException(403, "Bu filial sizning restoraningiznikidan emas")

    return {
        "id": branch.id,
        "name": branch.name,
        "address": branch.address,
        "phone": branch.phone,
        "latitude": branch.latitude,
        "longitude": branch.longitude,
        "work_hours_from": branch.work_hours_from,
        "work_hours_until": branch.work_hours_until,
        "min_order": branch.min_order,
        "delivery_base_fee": branch.delivery_base_fee,
        "delivery_per_km": branch.delivery_per_km,
        "is_active": branch.is_active,
    }


@router.put("/admin/branches/{branch_id}/settings")
async def update_branch_settings(
    branch_id: int,
    data: BranchUpdate,
    rid: int = Depends(get_restaurant_context),
    db: AsyncSession = Depends(get_db),
):
    """Restoran admin: o'z filiali sozlamalarini yangilash. IDOR himoyasi."""
    branch = await db.get(Branch, branch_id)
    if not branch:
        raise HTTPException(404, "Filial topilmadi")
    if branch.restaurant_id != rid:
        raise HTTPException(403, "Bu filial sizning restoraningiznikidan emas")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(branch, field, value)

    await db.commit()
    return {"success": True}


# ── Bot: Yaqin filiallar ────────────────────────────

@router.get("/branches/nearest")
async def nearest_branches(
    lat: float = Query(...),
    lon: float = Query(...),
    restaurant_id: int = Query(default=1),
    db: AsyncSession = Depends(get_db),
):
    """Foydalanuvchi joylashuviga yaqin filiallarni qaytaradi (masofasi bilan)."""
    result = await db.execute(
        select(Branch)
        .where(
            Branch.restaurant_id == restaurant_id,
            Branch.is_active == True,
            Branch.latitude.isnot(None),
            Branch.longitude.isnot(None),
        )
    )
    branches = result.scalars().all()

    items = []
    for b in branches:
        dist = _haversine(lat, lon, b.latitude, b.longitude)
        items.append({
            "id": b.id,
            "name": b.name,
            "address": b.address,
            "phone": b.phone,
            "distance_km": round(dist, 1),
            "is_open": _is_branch_open(b),
            "work_hours_from": b.work_hours_from,
            "work_hours_until": b.work_hours_until,
        })

    items.sort(key=lambda x: x["distance_km"])
    return items


@router.get("/branches/{branch_id}")
async def get_branch(branch_id: int, db: AsyncSession = Depends(get_db)):
    branch = await db.get(Branch, branch_id)
    if not branch:
        raise HTTPException(404, "Filial topilmadi")

    return {
        "id": branch.id,
        "restaurant_id": branch.restaurant_id,
        "name": branch.name,
        "address": branch.address,
        "phone": branch.phone,
        "latitude": branch.latitude,
        "longitude": branch.longitude,
        "work_hours_from": branch.work_hours_from,
        "work_hours_until": branch.work_hours_until,
        "min_order": branch.min_order,
        "delivery_base_fee": branch.delivery_base_fee,
        "delivery_per_km": branch.delivery_per_km,
        "is_active": branch.is_active,
        "is_open": _is_branch_open(branch),
    }


@router.get("/branches/{branch_id}/is-open")
async def is_branch_open(branch_id: int, db: AsyncSession = Depends(get_db)):
    branch = await db.get(Branch, branch_id)
    if not branch:
        raise HTTPException(404, "Filial topilmadi")

    return {
        "is_open": _is_branch_open(branch),
        "work_hours_from": branch.work_hours_from,
        "work_hours_until": branch.work_hours_until,
    }
