"""Catering (tadbir) buyurtmalari — Somsa va Nonlar.

Endi guruh bo'yicha ishlaydi:
- Somsa guruh (min=100): Go'shtli somsa, Ko'kli somsa, Dollar somsa, Ovashnoy ...
- Non guruh (min=40, step=40): Shirmoy, Yong'oq-mayizli, Go'shtli non

Aralash orderlar: ikki yoki undan ortiq mahsulot bitta orderda
umumiy miqdor minimal va step'ga mos kelishi kerak.
"""
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime, time, timedelta

from api.database import get_db
from api.config import settings
from api.auth_deps import get_restaurant_plan, restaurant_has_feature
from api.services.currency import get_currency_rate, convert_usd_to_uzs
from database.models import (
    Product, User, Order, OrderItem, OrderStatus, DeliveryType, Branch, Restaurant
)


async def _require_bot_secret(x_bot_secret: Optional[str] = Header(None, alias="X-Bot-Secret")):
    """Bot'dan kelgan so'rovlarni tekshirish (telegram_id spoofing'dan himoya).

    Constant-time, markaziy is_valid_bot_secret orqali (BOT_API_SECRET) — audit C1/M1.
    """
    from api.services.security import is_valid_bot_secret
    if not is_valid_bot_secret(x_bot_secret or ""):
        raise HTTPException(403, "Ruxsat berilmadi")
    return True


async def _ensure_catering_enabled(restaurant_id: int, db: AsyncSession) -> None:
    """Restoran tarifi catering'ni qo'llab-quvvatlamasa **402 Payment Required**.

    Frontend bu javobni ushlab "tarifni yangilash" sahifasini ochishi mumkin.
    Yangi kod `Depends(require_plan_feature("catering"))` ishlatishi tavsiya etiladi —
    bu funksiya backward compat uchun qoldirilgan.
    """
    plan = await get_restaurant_plan(restaurant_id, db)
    if not restaurant_has_feature(plan, "catering"):
        plan_name = plan.name if plan else "tarif yo'q"
        raise HTTPException(
            402,
            {
                "code": "plan_feature_required",
                "feature": "catering",
                "current_plan": plan_name,
                "message": f"Catering joriy tarifda ({plan_name}) yoqilmagan. Tarifni yangilang.",
            },
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
    await _ensure_catering_enabled(restaurant_id, db)
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
            "unit_price_uzs": p.unit_price_pickup_uzs,
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


@router.get("/booked-dates")
async def booked_dates(
    restaurant_id: int,
    branch_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Kelajakdagi catering uchun TO'LIQ band (sana, vaqt) juftliklari.

    Mantiq (faza 3+): har (date, time) slot uchun nechta order bor — agar
    `count >= filial_car_count` bo'lsa, slot "to'liq band" deb hisoblanadi.
    Aks holda mashina hali bo'sh (yana zakaz qabul qilish mumkin).

    Misol: 5 ta mashinali filial → 10:00 ga 4 ta order tushgan → slot HALI ham
    `available` (1 ta mashina bo'sh). 5-chi order tushganda → `booked`.
    """
    from database.models import Branch
    await _ensure_catering_enabled(restaurant_id, db)
    today = datetime.now().date().isoformat()

    q = select(Order.schedule_date, Order.schedule_time, Order.branch_id).where(
        Order.order_kind == "catering",
        Order.schedule_date >= today,
        Order.status.notin_([OrderStatus.cancelled, OrderStatus.delivered]),
    )
    if branch_id is not None:
        q = q.where(Order.branch_id == branch_id)
    else:
        q = q.where(Order.restaurant_id == restaurant_id)
    rows = (await db.execute(q)).all()

    # Filial → car_count map
    branch_q = select(Branch.id, Branch.delivery_car_count).where(
        Branch.restaurant_id == restaurant_id
    )
    branch_caps = dict((await db.execute(branch_q)).all())

    # (branch_id, date, time) bo'yicha hisoblagich
    counts: dict[tuple, int] = {}
    for d, t, bid in rows:
        if not d or not t:
            continue
        key = (bid, d, t)
        counts[key] = counts.get(key, 0) + 1

    # Faqat to'liq band'larni qaytarish
    by_date: dict[str, list[str]] = {}
    for (bid, d, t), cnt in counts.items():
        cap = max(1, int(branch_caps.get(bid, 5) or 5))
        if cnt >= cap:
            by_date.setdefault(d, []).append(t)

    return {"booked": by_date}


@router.get("/available-slots")
async def available_slots(
    date: str,
    restaurant_id: int,
    branch_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Tanlangan sana uchun 08:00–22:00 oralig'ida bo'sh vaqt-slot'lar.

    Telegram WebApp uchun mo'ljallangan: foydalanuvchi sana tanlaganda har soat
    bo'sh-bandligini ko'rsatadi. Slot bo'sh deb hisoblanishi uchun shu soatdan
    boshlab `CATERING_DURATION_MINUTES` (4 soat) davomida hech bo'lmasa bitta
    mashina bo'sh bo'lishi kerak.

    Args:
        date: YYYY-MM-DD formatida (`?date=2026-05-15`)
        restaurant_id: restoran ID

    Response:
        {
          "date": "2026-05-15",
          "restaurant_id": 1,
          "slots": [
            {"time": "08:00", "status": "active"},
            {"time": "09:00", "status": "busy"},
            ...
          ]
        }
    """
    from api.services.resources import CATERING_DURATION_MINUTES, check_slot_availability

    # Sana validatsiyasi
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Sana formati: YYYY-MM-DD")

    today = datetime.now().date()
    if target_date < today:
        raise HTTPException(400, "O'tgan sanada slot bo'lmaydi")

    # Restoranning mavjudligi va catering yoqilganligi
    await _ensure_catering_enabled(restaurant_id, db)

    # branch_id berilmagan bo'lsa birinchi faol filialni olish
    if branch_id is None:
        from database.models import Branch
        first = (await db.execute(
            select(Branch).where(
                Branch.restaurant_id == restaurant_id,
                Branch.is_active == True,
            ).order_by(Branch.id).limit(1)
        )).scalar_one_or_none()
        if not first:
            raise HTTPException(404, "Faol filial topilmadi")
        branch_id = first.id

    # 08:00 dan 22:00 gacha har soat
    slots: list[dict] = []
    for hour in range(8, 22):
        slot_start = datetime.combine(target_date, time(hour=hour, minute=0))
        slot_end = slot_start + timedelta(minutes=CATERING_DURATION_MINUTES)

        # Bo'sh mashina bormi (filial darajasida)?
        is_available = await check_slot_availability(
            db, restaurant_id=restaurant_id, branch_id=branch_id,
            slot_start=slot_start, slot_end=slot_end,
        )
        slots.append({
            "time": f"{hour:02d}:00",
            "status": "active" if is_available else "busy",
        })

    return {
        "date": date,
        "restaurant_id": restaurant_id,
        "branch_id": branch_id,
        "slots": slots,
    }


@router.post("/calculate-price")
async def calculate_price(
    data: CalculatePriceRequest,
    restaurant_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Aralash catering buyurtma narxini hisoblash."""
    await _ensure_catering_enabled(restaurant_id, db)
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
    _bot: bool = Depends(_require_bot_secret),
    db: AsyncSession = Depends(get_db),
):
    """Aralash catering buyurtma yaratish."""
    # Tarif tekshiruvi
    await _ensure_catering_enabled(restaurant_id, db)
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

    # ── branch_id fallback: agar berilmagan bo'lsa birinchi faol filial
    # (catering uchun branch_id majburiy — admin panel filteri shu orqali ishlaydi)
    if branch_id is None:
        from database.models import Branch
        first = (await db.execute(
            select(Branch).where(
                Branch.restaurant_id == restaurant_id,
                Branch.is_active == True,
            ).order_by(Branch.id).limit(1)
        )).scalar_one_or_none()
        if first:
            branch_id = first.id

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

    # Slot konflikti — bir filialda bitta sana/vaqtga faqat bitta catering
    busy_q = select(Order).where(
        Order.order_kind == "catering",
        Order.schedule_date == data.schedule_date,
        Order.schedule_time == data.schedule_time,
        Order.status.notin_([OrderStatus.cancelled, OrderStatus.delivered]),
    )
    if branch_id is not None:
        busy_q = busy_q.where(Order.branch_id == branch_id)
    else:
        busy_q = busy_q.where(Order.restaurant_id == restaurant_id)
    busy = (await db.execute(busy_q)).scalar_one_or_none()
    if busy:
        raise HTTPException(
            409,
            f"Bu vaqt ({data.schedule_date} {data.schedule_time}) band qilingan. "
            f"Iltimos, boshqa vaqt yoki sana tanlang."
        )

    # Narx
    rate = await get_currency_rate(restaurant_id, db)
    breakdown = await _compute_catering_price(
        data.items, data.delivery_subtype, data.distance_km, rate, db, restaurant_id
    )

    # Catering mahsulotlarining narxi belgilanmagan bo'lsa — to'lov yarata olmaymiz
    if (breakdown.get("total_price_uzs") or 0) <= 0:
        raise HTTPException(
            400,
            "Tanlangan catering mahsulotlarining narxi belgilanmagan. "
            "Restoran administratoriga murojaat qiling.",
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
        service_type={
            "onsite": "onsite_catering",
            "pickup": "pickup",
            "delivery": "delivery",
        }.get(data.delivery_subtype, "pickup"),
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
    await _ensure_catering_enabled(restaurant_id, db)
    result = await db.execute(
        select(Product).where(
            Product.is_active == True,
            Product.product_type == "catering",
        )
    )
    return [_product_dict(p) for p in result.scalars().all()]
