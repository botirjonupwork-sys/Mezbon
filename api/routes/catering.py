"""Catering (tadbir) buyurtmalari — Dollar somsa va Nonlar uchun.

Oqim:
1. GET /catering/products — catering mahsulotlar ro'yxati
2. GET /catering/currency — joriy valyuta kursi
3. POST /catering/calculate-price — narx hisoblash (tasdiqlashdan oldin)
4. POST /catering/orders — buyurtma yaratish
5. GET /admin/catering/orders — admin catering buyurtmalari
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

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
    unit_type: str
    min_quantity: int
    quantity_step: int
    price_onsite_usd: Optional[float] = None
    price_pickup_uzs: Optional[float] = None
    price_delivery_uzs: Optional[float] = None
    price_per_km_uzs: Optional[float] = None

    class Config:
        from_attributes = True


class CalculatePriceRequest(BaseModel):
    product_id: int
    quantity: int
    delivery_subtype: str  # 'onsite' | 'pickup' | 'delivery'
    distance_km: Optional[float] = None  # Delivery uchun


class CalculatePriceResponse(BaseModel):
    total_price_uzs: float
    total_price_usd: float
    currency_rate: float
    breakdown: dict


class CateringOrderCreate(BaseModel):
    product_id: int
    quantity: int
    delivery_subtype: str
    schedule_date: str  # YYYY-MM-DD
    schedule_time: str  # HH:MM
    phone: str
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_km: Optional[float] = None
    payment_method: str = "cash"  # 'cash' | 'card'
    payment_timing: str = "later"  # 'now' | 'later'
    comment: Optional[str] = None


# ── Mahsulotlar ──────────────────────────────────────

@router.get("/products", response_model=List[CateringProductOut])
async def list_catering_products(
    branch_id: Optional[int] = None,
    restaurant_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Catering mahsulotlarini olish (bot va admin uchun)."""
    query = select(Product).where(
        Product.is_active == True,
        (Product.is_stop == False) | (Product.is_stop.is_(None)),
        Product.product_type == "catering",
    )
    if branch_id:
        br = await db.execute(select(Branch).where(Branch.id == branch_id))
        branch = br.scalar_one_or_none()
        if branch:
            query = query.where(
                (Product.branch_id == branch_id) |
                ((Product.restaurant_id == branch.restaurant_id) & (Product.branch_id.is_(None)))
            )
    elif restaurant_id:
        branch_ids = select(Branch.id).where(Branch.restaurant_id == restaurant_id)
        query = query.where(
            (Product.restaurant_id == restaurant_id) | Product.branch_id.in_(branch_ids)
        )
    result = await db.execute(query)
    return result.scalars().all()


# ── Valyuta kursi ────────────────────────────────────

@router.get("/currency")
async def get_currency(
    restaurant_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Joriy USD → UZS kursini olish."""
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
    product: Product,
    quantity: int,
    delivery_subtype: str,
    distance_km: Optional[float],
    rate: float,
) -> dict:
    """Catering buyurtma narxini hisoblaydi.

    - quantity: miqdor (somsa uchun 100 ga karrali, non uchun tandir soni)
    - delivery_subtype: onsite/pickup/delivery
    """
    # Mahsulot uchun "birlik" — somsa: 100 dona = 1 birlik, non: 1 tandir = 1 birlik
    units = quantity / product.quantity_step if product.quantity_step > 0 else quantity

    delivery_fee_uzs = 0.0
    product_price_uzs = 0.0
    product_price_usd = 0.0

    if delivery_subtype == "onsite":
        # Joyiga borib yopish — USD narx
        unit_price_usd = product.price_onsite_usd or 0.0
        product_price_usd = unit_price_usd * units
        product_price_uzs = convert_usd_to_uzs(product_price_usd, rate)
    elif delivery_subtype == "pickup":
        # Saboy — UZS narx
        unit_price_uzs = product.price_pickup_uzs or 0.0
        product_price_uzs = unit_price_uzs * units
        product_price_usd = round(product_price_uzs / rate, 2) if rate > 0 else 0.0
    elif delivery_subtype == "delivery":
        # Dastavka: USD narx + dastavka haqi
        unit_price_usd = product.price_delivery_uzs or product.price_onsite_usd or 0.0
        product_price_usd = unit_price_usd * units
        product_price_uzs = convert_usd_to_uzs(product_price_usd, rate)
        # Dastavka haqi: km × narx (agar km berilgan bo'lsa)
        if distance_km and product.price_per_km_uzs:
            delivery_fee_uzs = distance_km * product.price_per_km_uzs

    total_uzs = product_price_uzs + delivery_fee_uzs
    total_usd = round(total_uzs / rate, 2) if rate > 0 else 0.0

    return {
        "units": units,
        "product_price_uzs": product_price_uzs,
        "product_price_usd": product_price_usd,
        "delivery_fee_uzs": delivery_fee_uzs,
        "total_price_uzs": total_uzs,
        "total_price_usd": total_usd,
        "currency_rate": rate,
    }


@router.post("/calculate-price", response_model=CalculatePriceResponse)
async def calculate_price(
    data: CalculatePriceRequest,
    restaurant_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Catering buyurtma narxini oldindan hisoblash (tasdiqlashdan oldin)."""
    result = await db.execute(select(Product).where(Product.id == data.product_id))
    product = result.scalar_one_or_none()
    if not product or product.product_type != "catering":
        raise HTTPException(404, "Catering mahsulot topilmadi")

    if data.quantity < product.min_quantity:
        raise HTTPException(400, f"Minimal miqdor: {product.min_quantity}")

    if product.quantity_step > 1 and data.quantity % product.quantity_step != 0:
        raise HTTPException(400, f"Miqdor {product.quantity_step} ga karrali bo'lishi kerak")

    rate = await get_currency_rate(restaurant_id, db)
    breakdown = await _compute_catering_price(
        product, data.quantity, data.delivery_subtype, data.distance_km, rate
    )
    return CalculatePriceResponse(
        total_price_uzs=breakdown["total_price_uzs"],
        total_price_usd=breakdown["total_price_usd"],
        currency_rate=rate,
        breakdown=breakdown,
    )


# ── Buyurtma yaratish ────────────────────────────────

@router.post("/orders")
async def create_catering_order(
    data: CateringOrderCreate,
    telegram_id: str,
    restaurant_id: int,
    branch_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Catering buyurtma yaratish."""
    # Foydalanuvchini topish yoki yaratish
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Foydalanuvchi topilmadi — avval ro'yxatdan o'ting")

    # Mahsulot
    result = await db.execute(select(Product).where(Product.id == data.product_id))
    product = result.scalar_one_or_none()
    if not product or product.product_type != "catering":
        raise HTTPException(404, "Mahsulot topilmadi")

    # Validatsiya
    if data.quantity < product.min_quantity:
        raise HTTPException(400, f"Minimal miqdor: {product.min_quantity}")
    if product.quantity_step > 1 and data.quantity % product.quantity_step != 0:
        raise HTTPException(400, f"Miqdor {product.quantity_step} ga karrali bo'lishi kerak")

    # Sana va vaqt tekshirish
    try:
        schedule_dt = datetime.strptime(f"{data.schedule_date} {data.schedule_time}", "%Y-%m-%d %H:%M")
        if schedule_dt < datetime.now():
            raise HTTPException(400, "Sana o'tmishda bo'lishi mumkin emas")
    except ValueError:
        raise HTTPException(400, "Sana/vaqt noto'g'ri formatda")

    # Narx hisoblash
    rate = await get_currency_rate(restaurant_id, db)
    breakdown = await _compute_catering_price(
        product, data.quantity, data.delivery_subtype, data.distance_km, rate
    )

    # Buyurtma yaratish
    order = Order(
        user_id=user.id,
        restaurant_id=restaurant_id,
        branch_id=branch_id,
        delivery_type=DeliveryType.delivery if data.delivery_subtype == "delivery" else DeliveryType.pickup,
        address=data.address,
        latitude=data.latitude,
        longitude=data.longitude,
        comment=data.comment,
        total_price=breakdown["total_price_uzs"],
        delivery_fee=breakdown["delivery_fee_uzs"],
        status=OrderStatus.pending,
        # Catering maydonlari
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

    db.add(OrderItem(
        order_id=order.id,
        product_id=product.id,
        quantity=data.quantity,
        price=product.price_onsite_usd or product.price,
    ))
    await db.commit()
    await db.refresh(order)

    # To'lov karta ma'lumoti (agar "hozir to'lov" bo'lsa)
    payment_info = None
    if data.payment_timing == "now":
        rest_res = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
        rest = rest_res.scalar_one_or_none()
        if rest and rest.catering_payment_card:
            payment_info = {
                "card_number": rest.catering_payment_card,
                "owner": rest.catering_payment_owner,
            }

    return {
        "id": order.id,
        "total_price_uzs": breakdown["total_price_uzs"],
        "total_price_usd": breakdown["total_price_usd"],
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
