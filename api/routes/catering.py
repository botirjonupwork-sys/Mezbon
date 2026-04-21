"""Catering (tadbir) buyurtmalari — Somsa va Nonlar.

Endi guruh bo'yicha ishlaydi:
- Somsa guruh (min=100): Go'shtli somsa, Ko'kli somsa, Dollar somsa, Ovashnoy ...
- Non guruh (min=40, step=40): Shirmoy, Yong'oq-mayizli, Go'shtli non

Aralash orderlar: ikki yoki undan ortiq mahsulot bitta orderda
umumiy miqdor minimal va step'ga mos kelishi kerak.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime, timedelta

from api.database import get_db
from api.services.currency import get_currency_rate, convert_usd_to_uzs
from database.models import (
    Product, User, Order, OrderItem, OrderStatus, DeliveryType, Branch, Restaurant
)

router = APIRouter(prefix="/catering", tags=["catering"])


# ── Schemas ──────────────────────────────────────────

class CateringProductOut(BaseModel):
    id: int
    name_uz: str
    name_ru: Optional[str] = None
    description_uz: Optional[str] = None
    image_url: Optional[str] = None
    catering_group: Optional[str] = None
    unit_price_usd: Optional[float] = None
    unit_price_pickup_uzs: Optional[float] = None

    class Config:
        from_attributes = True


class CateringGroupInfo(BaseModel):
    group: str  # 'somsa' | 'nan'
    min_total: int
    step: int
    delivery_per_km_uzs: float
    products: List[CateringProductOut]


class CateringItem(BaseModel):
    product_id: int
    quantity: int


class CalculatePriceRequest(BaseModel):
    group: str  # 'somsa' | 'nan'
    items: List[CateringItem]
    delivery_subtype: str  # 'onsite' | 'pickup' | 'delivery'
    distance_km: Optional[float] = None


class CateringOrderCreate(BaseModel):
    group: str
    items: List[CateringItem]
    delivery_subtype: str
    schedule_date: str
    schedule_time: str
    phone: str
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_km: Optional[float] = None
    payment_method: str = "cash"
    payment_timing: str = "later"
    comment: Optional[str] = None


# ── Guruhlar ─────────────────────────────────────────

@router.get("/groups")
async def get_catering_groups(
    restaurant_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Barcha catering guruhlari va ulardagi mahsulotlar."""
    result = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
    rest = result.scalar_one_or_none()
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")

    # Somsa guruhi
    somsa_q = await db.execute(
        select(Product).where(
            Product.is_active == True,
            Product.product_type == "catering",
            Product.catering_group == "somsa",
            (Product.restaurant_id == restaurant_id) | (Product.restaurant_id.is_(None))
        )
    )
    somsa_products = somsa_q.scalars().all()

    # Non guruhi
    nan_q = await db.execute(
        select(Product).where(
            Product.is_active == True,
            Product.product_type == "catering",
            Product.catering_group == "nan",
            (Product.restaurant_id == restaurant_id) | (Product.restaurant_id.is_(None))
        )
    )
    nan_products = nan_q.scalars().all()

    return [
        {
            "group": "somsa",
            "label": "🥟 Somsa",
            "min_total": rest.catering_somsa_min or 100,
            "step": rest.catering_somsa_step or 1,
            "delivery_per_km_uzs": rest.catering_delivery_per_km_uzs or 5000,
            "products": [_product_dict(p) for p in somsa_products],
        },
        {
            "group": "nan",
            "label": "🍞 Non",
            "min_total": rest.catering_nan_min or 40,
            "step": rest.catering_nan_step or 40,
            "delivery_per_km_uzs": rest.catering_delivery_per_km_uzs or 5000,
            "products": [_product_dict(p) for p in nan_products],
        },
    ]


def _product_dict(p: Product) -> dict:
    return {
        "id": p.id,
        "name_uz": p.name_uz,
        "name_ru": p.name_ru,
        "description_uz": p.description_uz,
        "image_url": p.image_url,
        "catering_group": p.catering_group,
        "unit_price_usd": p.unit_price_usd,
        "unit_price_pickup_uzs": p.unit_price_pickup_uzs,
    }


# ── Valyuta ──────────────────────────────────────────

@router.get("/currency")
async def get_currency(
    restaurant_id: int,
    db: AsyncSession = Depends(get_db),
):
    rate = await get_currency_rate(restaurant_id, db)
    result = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
    rest = result.scalar_one_or_none()
    return {
        "rate": rate,
        "is_auto": bool(rest and rest.currency_auto),
        "updated_at": rest.currency_cache_updated_at.isoformat() if rest and rest.currency_cache_updated_at else None,
    }


# ── Narx hisoblash ───────────────────────────────────

async def _compute_catering_price(
    items: List[CateringItem],
    delivery_subtype: str,
    distance_km: Optional[float],
    rate: float,
    db: AsyncSession,
    restaurant_id: int,
) -> dict:
    """Aralash buyurtma narxi:
    - Har bir mahsulot uchun (miqdor × dona narx)
    - Delivery bo'lsa km × per_km qo'shiladi
    - Pickup — UZS narxda, onsite/delivery — USD narxda
    """
    total_uzs = 0.0
    total_usd = 0.0
    total_quantity = 0
    breakdown = []

    for it in items:
        if it.quantity <= 0:
            continue
        res = await db.execute(select(Product).where(Product.id == it.product_id))
        p = res.scalar_one_or_none()
        if not p:
            raise HTTPException(404, f"Mahsulot #{it.product_id} topilmadi")

        if delivery_subtype == "pickup":
            unit_uzs = p.unit_price_pickup_uzs or 0
            item_uzs = unit_uzs * it.quantity
            item_usd = round(item_uzs / rate, 2) if rate > 0 else 0
        else:
            unit_usd = p.unit_price_usd or 0
            item_usd = unit_usd * it.quantity
            item_uzs = convert_usd_to_uzs(item_usd, rate)

        total_uzs += item_uzs
        total_usd += item_usd
        total_quantity += it.quantity
        breakdown.append({
            "product_id": it.product_id,
            "name_uz": p.name_uz,
            "quantity": it.quantity,
            "unit_price_usd": p.unit_price_usd,
            "item_usd": round(item_usd, 2),
            "item_uzs": item_uzs,
        })

    delivery_fee_uzs = 0.0
    if delivery_subtype == "delivery" and distance_km:
        res = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
        rest = res.scalar_one_or_none()
        per_km = (rest.catering_delivery_per_km_uzs if rest else None) or 5000
        delivery_fee_uzs = distance_km * per_km

    final_uzs = total_uzs + delivery_fee_uzs
    final_usd = round(final_uzs / rate, 2) if rate > 0 else 0

    return {
        "total_quantity": total_quantity,
        "subtotal_uzs": total_uzs,
        "subtotal_usd": round(total_usd, 2),
        "delivery_fee_uzs": delivery_fee_uzs,
        "total_price_uzs": final_uzs,
        "total_price_usd": final_usd,
        "currency_rate": rate,
        "breakdown": breakdown,
    }


def _validate_group_order(group: str, total: int, rest: Restaurant) -> None:
    """Min va step validation."""
    if group == "somsa":
        min_t = rest.catering_somsa_min or 100
        step = rest.catering_somsa_step or 1
    elif group == "nan":
        min_t = rest.catering_nan_min or 40
        step = rest.catering_nan_step or 40
    else:
        raise HTTPException(400, f"Noto'g'ri guruh: {group}")
    if total < min_t:
        raise HTTPException(400, f"Minimal miqdor: {min_t}")
    if step > 1 and total % step != 0:
        raise HTTPException(400, f"Miqdor {step} ga karrali bo'lishi kerak")


@router.post("/calculate-price")
async def calculate_price(
    data: CalculatePriceRequest,
    restaurant_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Aralash catering buyurtma narxini hisoblash."""
    result = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
    rest = result.scalar_one_or_none()
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")

    total = sum(it.quantity for it in data.items if it.quantity > 0)
    _validate_group_order(data.group, total, rest)

    rate = await get_currency_rate(restaurant_id, db)
    breakdown = await _compute_catering_price(
        data.items, data.delivery_subtype, data.distance_km, rate, db, restaurant_id
    )
    return breakdown


# ── Buyurtma yaratish ────────────────────────────────

@router.post("/orders")
async def create_catering_order(
    data: CateringOrderCreate,
    telegram_id: str,
    restaurant_id: int,
    branch_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Aralash catering buyurtma yaratish."""
    # Foydalanuvchi
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Foydalanuvchi topilmadi — avval ro'yxatdan o'ting")

    # Restaurant
    result = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
    rest = result.scalar_one_or_none()
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")

    # Validation
    total = sum(it.quantity for it in data.items if it.quantity > 0)
    _validate_group_order(data.group, total, rest)

    # Sana — kamida 24 soat oldin
    try:
        schedule_dt = datetime.strptime(f"{data.schedule_date} {data.schedule_time}", "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(400, "Sana/vaqt noto'g'ri formatda")
    min_allowed = datetime.now() + timedelta(hours=24)
    if schedule_dt < min_allowed:
        raise HTTPException(
            400,
            "Catering buyurtmalari kamida 24 soat oldin qabul qilinadi. "
            "Tezkor buyurtmalar uchun: +998 98 000 06 04"
        )

    # Narx
    rate = await get_currency_rate(restaurant_id, db)
    breakdown = await _compute_catering_price(
        data.items, data.delivery_subtype, data.distance_km, rate, db, restaurant_id
    )

    # Buyurtma
    order = Order(
        user_id=user.id,
        restaurant_id=restaurant_id,
        branch_id=branch_id,
        delivery_type=DeliveryType.delivery if data.delivery_subtype == "delivery" else DeliveryType.pickup,
        address=data.address,
        latitude=data.latitude,
        longitude=data.longitude,
        comment=f"[{data.group.upper()}] {data.comment or ''}",
        total_price=breakdown["total_price_uzs"],
        delivery_fee=breakdown["delivery_fee_uzs"],
        status=OrderStatus.pending,
        order_kind="catering",
        schedule_date=data.schedule_date,
        schedule_time=data.schedule_time,
        delivery_subtype=data.delivery_subtype,
        payment_method=data.payment_method,
        payment_timing=data.payment_timing,
        payment_status="pending",
        currency_rate_snapshot=rate,
        total_price_usd=breakdown["total_price_usd"],
    )
    db.add(order)
    await db.flush()

    for it in data.items:
        if it.quantity <= 0:
            continue
        p_res = await db.execute(select(Product).where(Product.id == it.product_id))
        p = p_res.scalar_one_or_none()
        db.add(OrderItem(
            order_id=order.id,
            product_id=it.product_id,
            quantity=it.quantity,
            price=(p.unit_price_usd if p else 0) or 0,
        ))

    await db.commit()
    await db.refresh(order)

    # To'lov karta
    payment_info = None
    if data.payment_timing == "now" and rest.catering_payment_card:
        payment_info = {
            "card_number": rest.catering_payment_card,
            "owner": rest.catering_payment_owner,
        }

    return {
        "id": order.id,
        "total_price_uzs": breakdown["total_price_uzs"],
        "total_price_usd": breakdown["total_price_usd"],
        "total_quantity": breakdown["total_quantity"],
        "schedule_date": data.schedule_date,
        "schedule_time": data.schedule_time,
        "delivery_subtype": data.delivery_subtype,
        "payment_info": payment_info,
        "message": (
            "Buyurtmangiz qabul qilindi ✅\n\n"
            "Belgilangan vaqtdan taxminan 2 soat oldin somsachilar tayyorgarlik "
            "ko'rish uchun yetib borishadi. Iltimos, shu vaqt oralig'ida aloqada "
            "bo'lib turing, shunda jarayonda muammo yuzaga kelmaydi.\n\n"
            "Hamkorligingiz uchun rahmat!"
        ),
    }


# ── Backward compat: eski /products endpointi ──────

@router.get("/products")
async def legacy_products(
    restaurant_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Eski endpoint — barcha catering mahsulotlari."""
    result = await db.execute(
        select(Product).where(
            Product.is_active == True,
            Product.product_type == "catering",
        )
    )
    return [_product_dict(p) for p in result.scalars().all()]
