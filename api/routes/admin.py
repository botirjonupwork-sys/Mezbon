"""Admin uchun maxsus endpointlar — mahsulot CRUD, kategoriya, statistika"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel
import shutil
import os
import uuid

from api.database import get_db
from api.schemas import CategoryOut
from api.config import settings
from api.auth_deps import get_branch_context, get_restaurant_context, require_restaurant_admin, require_super_admin
from database.models import (
    Product, Category, Order, OrderItem, User, Review, OrderStatus, Courier, Branch, Admin, Plan
)

router = APIRouter(prefix="/admin", tags=["admin"])

UPLOAD_DIR = "static/images/products"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ── Schemas ───────────────────────────────────────────
class ProductCreate(BaseModel):
    name_uz: str
    name_ru: Optional[str] = None
    description_uz: Optional[str] = None
    description_ru: Optional[str] = None
    category_id: int
    price: float
    image_url: Optional[str] = None
    has_time_limit: bool = False
    available_from: Optional[str] = None
    available_until: Optional[str] = None
    branch_id: Optional[int] = None
    # Catering maydonlari
    product_type: Optional[str] = "regular"
    catering_group: Optional[str] = None  # 'somsa' | 'nan'
    unit_price_usd: Optional[float] = None
    unit_price_pickup_uzs: Optional[float] = None
    # Eski (backward compat)
    unit_type: Optional[str] = "piece"
    min_quantity: Optional[int] = 1
    quantity_step: Optional[int] = 1
    price_onsite_usd: Optional[float] = None
    price_pickup_uzs: Optional[float] = None
    price_delivery_uzs: Optional[float] = None
    price_per_km_uzs: Optional[float] = None


class ProductUpdate(BaseModel):
    name_uz: Optional[str] = None
    name_ru: Optional[str] = None
    description_uz: Optional[str] = None
    description_ru: Optional[str] = None
    category_id: Optional[int] = None
    price: Optional[float] = None
    image_url: Optional[str] = None
    has_time_limit: Optional[bool] = None
    available_from: Optional[str] = None
    available_until: Optional[str] = None
    branch_id: Optional[int] = None
    # Catering maydonlari
    product_type: Optional[str] = None
    catering_group: Optional[str] = None
    unit_price_usd: Optional[float] = None
    unit_price_pickup_uzs: Optional[float] = None
    unit_type: Optional[str] = None
    min_quantity: Optional[int] = None
    quantity_step: Optional[int] = None
    price_onsite_usd: Optional[float] = None
    price_pickup_uzs: Optional[float] = None
    price_delivery_uzs: Optional[float] = None
    price_per_km_uzs: Optional[float] = None


class CategoryCreate(BaseModel):
    name_uz: str
    name_ru: Optional[str] = None
    order: int = 0
    branch_id: Optional[int] = None


class CategoryUpdate(BaseModel):
    name_uz: Optional[str] = None
    name_ru: Optional[str] = None
    order: Optional[int] = None
    branch_id: Optional[int] = None


class SettingsUpdate(BaseModel):
    language: Optional[str] = None
    min_order: Optional[float] = None
    work_hours_from: Optional[str] = None
    work_hours_until: Optional[str] = None
    restaurant_name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    restaurant_lat: Optional[float] = None
    restaurant_lon: Optional[float] = None
    delivery_base_fee: Optional[float] = None
    delivery_per_km: Optional[float] = None
    delivery_provider: Optional[str] = None
    yandex_api_token: Optional[str] = None
    yandex_test_mode: Optional[bool] = None
    yandex_balance_monitor_enabled: Optional[bool] = None
    yandex_balance_amount: Optional[float] = None
    yandex_balance_currency: Optional[str] = None
    yandex_balance_low_threshold: Optional[float] = None
    yandex_balance_critical_threshold: Optional[float] = None
    yandex_balance_block_on_critical: Optional[bool] = None
    # Catering / valyuta
    currency_auto: Optional[bool] = None
    currency_rate_manual: Optional[float] = None
    catering_payment_card: Optional[str] = None
    catering_payment_owner: Optional[str] = None
    # Catering guruh sozlamalari
    catering_somsa_min: Optional[int] = None
    catering_somsa_step: Optional[int] = None
    catering_nan_min: Optional[int] = None
    catering_nan_step: Optional[int] = None
    catering_delivery_per_km_uzs: Optional[float] = None
    # Catering "borib yopib berish" (onsite) sig'imi — admin ishchilarga qarab o'zgartiradi
    catering_onsite_max: Optional[int] = None
    catering_onsite_window_hours: Optional[float] = None
    # To'lov gateway'lar
    click_merchant_id: Optional[str] = None
    click_service_id: Optional[str] = None
    click_secret_key: Optional[str] = None
    click_enabled: Optional[bool] = None
    payme_merchant_id: Optional[str] = None
    payme_secret_key: Optional[str] = None
    payme_enabled: Optional[bool] = None
    # Uzum Bank
    uzum_service_id: Optional[str] = None
    uzum_webhook_user: Optional[str] = None
    uzum_webhook_pass: Optional[str] = None
    uzum_enabled: Optional[bool] = None
    # Faza 1.4: Telegram Native Payments tokenlari + test/live rejim
    telegram_provider_token_click: Optional[str] = None
    telegram_provider_token_payme: Optional[str] = None
    payment_test_mode: Optional[bool] = None
    # Faza 6: Soliq va huquqiy
    is_vat_payer: Optional[bool] = None
    vat_percent: Optional[float] = None
    # Faza 8: yetkazib berish bo'yicha majburiy prepayment
    enforce_prepayment_for_delivery: Optional[bool] = None
    # Faza 9: ertangi catering ro'yxati Telegram chat ID
    catering_notifier_chat_id: Optional[str] = None
    # Telegram botlar (BotFather'dan)
    bot_token: Optional[str] = None
    courier_bot_token: Optional[str] = None
    # Faza 4-5: catering xizmat haqi va prepayment limiti
    catering_service_fee: Optional[float] = None
    prepayment_required_above: Optional[float] = None
    # AI Operator (restoran-spesifik — provider/model/api_key super-admin'da)
    ai_agent_enabled: Optional[bool] = None
    ai_agent_prompt: Optional[str] = None
    ai_agent_voice: Optional[str] = None
    ai_agent_greeting: Optional[str] = None
    ai_agent_work_hours_only: Optional[bool] = None
    ai_agent_max_call_minutes: Optional[int] = None
    ai_agent_fallback_phone: Optional[str] = None
    ai_agent_language: Optional[str] = None


class AdminCreate(BaseModel):
    username: str
    password: str


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    new_password: Optional[str] = None
    current_password: Optional[str] = None  # Faza 9: parol o'zgartirsa majburiy


def _get_restaurant_branches(restaurant_id: int):
    """Restaurant'ning barcha branch_id larini olish uchun subquery"""
    return select(Branch.id).where(Branch.restaurant_id == restaurant_id)


import re as _re

# Fayl nomi formati: UUIDv4.ext — faqat shuni qabul qilamiz (path traversal'ni oldini olish)
_FILENAME_RE = _re.compile(r"^[0-9a-f\-]{8,}\.(jpg|jpeg|png|webp|gif)$", _re.IGNORECASE)
_MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


# ── Image upload ───────────────────────────────────────
@router.post("/upload-image")
async def upload_image(
    file: UploadFile = File(...),
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
):
    # Extension validation
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
    if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
        raise HTTPException(400, "Faqat rasm fayllar (jpg, png, webp)")

    # Hajm cheklov — fayl butunini o'qimasdan
    content = await file.read()
    if len(content) > _MAX_UPLOAD_SIZE:
        raise HTTPException(400, "Rasm juda katta — max 10 MB")

    # Content-type bo'yicha ham tekshirish
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(400, "Fayl rasm emas")

    filename = f"{uuid.uuid4()}.{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(content)
    return {"url": f"/static/images/products/{filename}"}


@router.delete("/upload-image")
async def delete_image(
    url: str,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
):
    """Eski rasmni fayl tizimidan o'chirish (path traversal himoyasi bilan)."""
    if not url or not url.startswith("/static/images/products/"):
        return {"success": False, "reason": "invalid_url"}
    filename = url.rsplit("/", 1)[-1]
    # Path traversal himoyasi: UUID format'ga mos kelishi shart
    if not _FILENAME_RE.match(filename):
        raise HTTPException(400, "Fayl nomi noto'g'ri")
    filepath = os.path.abspath(os.path.join(UPLOAD_DIR, filename))
    # abspath tekshirish — katalog tashqarisiga chiqmaslik
    upload_abs = os.path.abspath(UPLOAD_DIR)
    if not filepath.startswith(upload_abs + os.sep):
        raise HTTPException(400, "Fayl yo'li noto'g'ri")
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            return {"success": True}
        except OSError:
            return {"success": False, "reason": "os_error"}
    return {"success": False, "reason": "not_found"}


# ── Resource widget (mashina holati — filial darajasida) ─────
@router.get("/stats/resources")
async def stats_resources(
    ctx: dict = Depends(get_branch_context),
    db: AsyncSession = Depends(get_db),
):
    """Mashinalar real-time holati — filial darajasida.

    `X-Branch-Context` header (yoki `?branch_id=`) majburiy.
    `get_branch_context` rid+bid pair'ni qaytaradi va filial restoranga
    tegishliligini IDOR'dan himoya qiladi.

    Branch berilmagan bo'lsa — restoranning birinchi faol filiali ishlatiladi.
    """
    from api.services.resources import get_capacity_snapshot
    from database.models import Branch

    rid = ctx["restaurant_id"]
    bid = ctx["branch_id"]
    if bid is None:
        # Branch berilmagan — birinchi faol filialni topamiz
        first = (await db.execute(
            select(Branch).where(Branch.restaurant_id == rid, Branch.is_active == True)
            .order_by(Branch.id).limit(1)
        )).scalar_one_or_none()
        if not first:
            raise HTTPException(404, "Hech qanday faol filial topilmadi")
        bid = first.id

    return await get_capacity_snapshot(db, restaurant_id=rid, branch_id=bid)


# ── Statistika ────────────────────────────────────────
@router.get("/stats")
async def get_stats(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    branch_id: Optional[int] = None,
    operational_date: bool = False,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db)
):
    if date_from:
        try:
            d_from = datetime.strptime(date_from, "%Y-%m-%d").date()
        except ValueError:
            d_from = date.today()
    else:
        d_from = date.today()

    if date_to:
        try:
            d_to = datetime.strptime(date_to, "%Y-%m-%d").date()
        except ValueError:
            d_to = date.today()
    else:
        d_to = date.today()

    # SaaS izolatsiya: restoran context majburiy
    if restaurant_id is None:
        return {"today_orders": 0, "today_revenue": 0, "total_users": 0,
                "active_orders": 0, "average_rating": 0, "total_reviews": 0}

    branch_ids = _get_restaurant_branches(restaurant_id)
    rest_filter = (Order.restaurant_id == restaurant_id) | Order.branch_id.in_(branch_ids)

    if branch_id:
        # IDOR
        br = (await db.execute(select(Branch).where(Branch.id == branch_id))).scalar_one_or_none()
        if not br or br.restaurant_id != restaurant_id:
            return {"today_orders": 0, "today_revenue": 0, "total_users": 0,
                    "active_orders": 0, "average_rating": 0, "total_reviews": 0}
        rest_filter = (Order.branch_id == branch_id)

    if operational_date:
        order_date_filter = or_(
            and_(
                Order.order_kind != "catering",
                func.date(Order.created_at) >= d_from,
                func.date(Order.created_at) <= d_to,
            ),
            and_(
                Order.order_kind == "catering",
                Order.schedule_date >= d_from.isoformat(),
                Order.schedule_date <= d_to.isoformat(),
            ),
        )
    else:
        order_date_filter = and_(
            func.date(Order.created_at) >= d_from,
            func.date(Order.created_at) <= d_to,
        )

    order_filters = [order_date_filter, rest_filter]

    orders_q = await db.execute(
        select(func.count(Order.id)).where(*order_filters)
    )
    orders_count = orders_q.scalar() or 0

    revenue_q = await db.execute(
        select(func.sum(Order.total_price)).where(
            *order_filters,
            Order.status != OrderStatus.cancelled
        )
    )
    revenue = revenue_q.scalar() or 0.0

    user_subq = select(Order.user_id).where(rest_filter).distinct()
    total_users = await db.execute(select(func.count()).select_from(
        select(User.id).where(User.id.in_(user_subq)).subquery()
    ))
    users_count = total_users.scalar() or 0

    active_orders = await db.execute(
        select(func.count(Order.id)).where(
            rest_filter,
            Order.status.notin_([OrderStatus.delivered, OrderStatus.cancelled]),
        )
    )
    active_count = active_orders.scalar() or 0

    review_q = select(
        func.avg(Review.rating).label("avg"),
        func.count(Review.id).label("total")
    ).where(Review.branch_id.in_(branch_ids))
    if branch_id:
        review_q = select(
            func.avg(Review.rating).label("avg"),
            func.count(Review.id).label("total")
        ).where(Review.branch_id == branch_id)
    avg_rating = await db.execute(review_q)
    rating_row = avg_rating.one()

    return {
        "today_orders": orders_count,
        "today_revenue": float(revenue),
        "total_users": users_count,
        "active_orders": active_count,
        "average_rating": round(float(rating_row.avg or 0), 1),
        "total_reviews": rating_row.total,
    }


@router.get("/orders")
async def get_all_orders(
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    branch_id: Optional[int] = None,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    order_kind: Optional[str] = None,  # 'regular' | 'catering'
    operational_date: bool = False,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    query = select(Order).order_by(Order.created_at.desc())

    # SaaS izolatsiya: restoran filteri HAR DOIM qo'llaniladi (super-admin tashqari)
    if restaurant_id is None:
        # Super-admin context tanlamagan — bo'sh ro'yxat (xavfsizlik default'i)
        return []

    branch_ids = _get_restaurant_branches(restaurant_id)
    # Faqat restoran ichidagi orderlar
    query = query.where(
        (Order.restaurant_id == restaurant_id) | Order.branch_id.in_(branch_ids)
    )

    # Qo'shimcha branch filtri — branch shu restoraniga tegishli bo'lishi shart
    if branch_id:
        # IDOR himoyasi: branch_id boshqa restoraniki bo'lsa — bo'sh
        br = (await db.execute(select(Branch).where(Branch.id == branch_id))).scalar_one_or_none()
        if not br or br.restaurant_id != restaurant_id:
            return []
        query = query.where(Order.branch_id == branch_id)

    if order_kind:
        query = query.where(Order.order_kind == order_kind)

    # To'lanmagan karta zakazlari platformaga ko'rinmasin (to'lov kutilmoqda).
    # Faqat naqd yoki to'langan/qisman to'langan zakazlar ko'rsatiladi.
    query = query.where(
        (Order.payment_method == "cash")
        | (Order.payment_method == None)  # noqa: E711 — SQL IS NULL
        | (Order.payment_status.in_(["paid", "partial", "refunded"]))
    )

    if status:
        try:
            query = query.where(Order.status == OrderStatus(status))
        except ValueError:
            raise HTTPException(400, f"Noto'g'ri status: {status}")

    if date_from:
        try:
            d_from = datetime.strptime(date_from, "%Y-%m-%d").date()
            if operational_date:
                query = query.where(or_(
                    and_(Order.order_kind != "catering", func.date(Order.created_at) >= d_from),
                    and_(Order.order_kind == "catering", Order.schedule_date >= d_from.isoformat()),
                ))
            else:
                query = query.where(func.date(Order.created_at) >= d_from)
        except ValueError:
            pass

    if date_to:
        try:
            d_to = datetime.strptime(date_to, "%Y-%m-%d").date()
            if operational_date:
                query = query.where(or_(
                    and_(Order.order_kind != "catering", func.date(Order.created_at) <= d_to),
                    and_(Order.order_kind == "catering", Order.schedule_date <= d_to.isoformat()),
                ))
            else:
                query = query.where(func.date(Order.created_at) <= d_to)
        except ValueError:
            pass

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    orders = result.scalars().all()

    output = []
    for order in orders:
        user_res = await db.execute(select(User).where(User.id == order.user_id))
        user = user_res.scalar_one_or_none()

        items_res = await db.execute(
            select(OrderItem).where(OrderItem.order_id == order.id)
        )
        items = items_res.scalars().all()

        items_with_names = []
        for i in items:
            prod_res = await db.execute(select(Product).where(Product.id == i.product_id))
            prod = prod_res.scalar_one_or_none()
            items_with_names.append({
                "product_id": i.product_id,
                "product_name": prod.name_uz if prod else f"#{i.product_id}",
                "quantity": i.quantity,
                "price": i.price,
            })

        output.append({
            "id": order.id,
            "branch_id": order.branch_id,
            "status": order.status.value,
            "delivery_type": order.delivery_type.value,
            "address": order.address,
            "latitude": float(order.latitude) if order.latitude is not None else None,
            "longitude": float(order.longitude) if order.longitude is not None else None,
            "comment": order.comment,
            "total_price": order.total_price,
            "delivery_fee": order.delivery_fee,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "user": {"full_name": user.full_name, "phone": user.phone} if user else None,
            "items": items_with_names,
            # Catering maydonlari
            "order_kind": order.order_kind or "regular",
            "schedule_date": order.schedule_date,
            "schedule_time": order.schedule_time,
            "delivery_subtype": order.delivery_subtype,
            "service_type": order.service_type,
            "payment_method": order.payment_method,
            "payment_timing": order.payment_timing,
            "payment_status": order.payment_status,
            "total_price_usd": order.total_price_usd,
            "currency_rate_snapshot": order.currency_rate_snapshot,
        })
    return output


# ── Mahsulot CRUD ─────────────────────────────────────
@router.get("/products")
async def list_products(
    branch_id: Optional[int] = None,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    category_id: Optional[int] = None,
    product_type: Optional[str] = None,  # 'regular' | 'catering' | None (barchasi)
    catering_category: Optional[str] = None,  # 'Somsalar' | 'Nonlar' | 'Ichimliklar' ...
    catering_group: Optional[str] = None,     # 'somsa' | 'nan' (logika)
    db: AsyncSession = Depends(get_db),
):
    """Mahsulotlar ro'yxati. Filterlar:

    - `product_type=regular|catering` — asosiy turi
    - `catering_category=Somsalar` — UI display kategoriyasi (frontend tab'lar uchun)
    - `catering_group=somsa|nan` — logik guruh (catering algoritmlari uchun)
    - `category_id`, `branch_id` — boshqa standart filterlar

    Kombinatsiya misollar:
        ?product_type=catering&catering_category=Somsalar
        ?product_type=catering&catering_group=nan
    """
    query = select(Product).where(Product.is_active == True).order_by(Product.category_id, Product.id)

    # SaaS izolatsiya: restoran filteri HAR DOIM
    if restaurant_id is None:
        return []
    branch_ids = _get_restaurant_branches(restaurant_id)
    query = query.where(
        (Product.restaurant_id == restaurant_id) | Product.branch_id.in_(branch_ids)
    )

    if product_type:
        query = query.where(Product.product_type == product_type)
    if catering_category:
        query = query.where(Product.catering_category == catering_category)
    if catering_group:
        query = query.where(Product.catering_group == catering_group)
    if category_id:
        query = query.where(Product.category_id == category_id)
    if branch_id:
        # IDOR: branch shu restoranga tegishli bo'lishi shart
        br = (await db.execute(select(Branch).where(Branch.id == branch_id))).scalar_one_or_none()
        if not br or br.restaurant_id != restaurant_id:
            return []
        query = query.where(
            (Product.branch_id == branch_id) |
            ((Product.restaurant_id == restaurant_id) & (Product.branch_id.is_(None)))
        )
    result = await db.execute(query)
    products = result.scalars().all()
    return [
        {
            "id": p.id,
            "name_uz": p.name_uz,
            "name_ru": p.name_ru,
            "description_uz": p.description_uz,
            "category_id": p.category_id,
            "price": p.price,
            "image_url": p.image_url,
            "has_time_limit": p.has_time_limit,
            "available_from": p.available_from,
            "available_until": p.available_until,
            "is_stop": p.is_stop,
            "is_active": p.is_active,
            "branch_id": p.branch_id,
            "product_type": p.product_type or "regular",
            "catering_group": p.catering_group,
            "catering_category": p.catering_category,
            "unit_price_usd": p.unit_price_usd,
            "unit_price_pickup_uzs": p.unit_price_pickup_uzs,
            "unit_type": p.unit_type or "piece",
            "min_quantity": p.min_quantity or 1,
            "quantity_step": p.quantity_step or 1,
            "price_onsite_usd": p.price_onsite_usd,
            "price_pickup_uzs": p.price_pickup_uzs,
            "price_delivery_uzs": p.price_delivery_uzs,
            "price_per_km_uzs": p.price_per_km_uzs,
        }
        for p in products
    ]


@router.post("/products")
async def create_product(
    data: ProductCreate,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    dump = data.model_dump()
    # SaaS izolatsiya: restoran admin uchun restaurant_id majburiy va o'zinikidan
    if not restaurant_id:
        raise HTTPException(400, "Super-admin: restaurant_id query majburiy")

    # branch_id boshqa restoraniki bo'lsa — silently null qil
    if dump.get("branch_id"):
        br = await db.execute(select(Branch).where(Branch.id == dump["branch_id"]))
        branch = br.scalar_one_or_none()
        if not branch or branch.restaurant_id != restaurant_id:
            dump["branch_id"] = None
    dump["restaurant_id"] = restaurant_id

    product = Product(**dump)
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return {"id": product.id, "name_uz": product.name_uz}


@router.put("/products/{product_id}")
async def update_product(
    product_id: int,
    data: ProductUpdate,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Mahsulot topilmadi")

    # SaaS izolatsiya: faqat o'z restorani mahsulotini tahrirsa bo'ladi
    if restaurant_id and product.restaurant_id and product.restaurant_id != restaurant_id:
        raise HTTPException(403, "Bu mahsulot sizning restoraningizniki emas")

    # Faqat yuborilgan maydonlarni yangilash
    dump = data.model_dump(exclude_unset=True)

    # branch_id yangilansa — boshqa restoraniki bo'lsa silently null
    if "branch_id" in dump and dump["branch_id"]:
        br = await db.execute(select(Branch).where(Branch.id == dump["branch_id"]))
        branch = br.scalar_one_or_none()
        if not branch or (restaurant_id and branch.restaurant_id != restaurant_id):
            dump["branch_id"] = None
    if restaurant_id:
        dump["restaurant_id"] = restaurant_id

    # Foydalanuvchi DB'dagi restaurant_id ni qo'lda override qilolmasligi kerak
    if restaurant_id and dump.get("restaurant_id") != restaurant_id:
        dump.pop("restaurant_id", None)
        dump["restaurant_id"] = restaurant_id

    for key, value in dump.items():
        setattr(product, key, value)

    await db.commit()
    return {"success": True}


@router.delete("/products/{product_id}")
async def delete_product(
    product_id: int,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Mahsulot topilmadi")
    # IDOR: faqat o'z restorani mahsulotini o'chirsa bo'ladi
    if restaurant_id and product.restaurant_id and product.restaurant_id != restaurant_id:
        raise HTTPException(403, "Bu mahsulot sizning restoraningizniki emas")
    product.is_active = False
    await db.commit()
    return {"success": True}


# ── Kategoriya CRUD ───────────────────────────────────
@router.get("/categories")
async def list_categories(
    branch_id: Optional[int] = None,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(Category).where(Category.is_active == True).order_by(Category.order)

    # SaaS izolatsiya
    if restaurant_id is None:
        return []
    branch_ids = _get_restaurant_branches(restaurant_id)
    query = query.where(
        (Category.restaurant_id == restaurant_id) | Category.branch_id.in_(branch_ids)
    )

    if branch_id:
        br = (await db.execute(select(Branch).where(Branch.id == branch_id))).scalar_one_or_none()
        if not br or br.restaurant_id != restaurant_id:
            return []
        query = query.where(
            (Category.branch_id == branch_id) |
            ((Category.restaurant_id == restaurant_id) & (Category.branch_id.is_(None)))
        )
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/categories")
async def create_category(
    data: CategoryCreate,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    dump = data.model_dump()
    if not restaurant_id:
        raise HTTPException(400, "Super-admin: restaurant_id query majburiy")

    # branch_id boshqa restoraniki bo'lsa — silently null qil (restaurant-level category)
    if dump.get("branch_id"):
        br = await db.execute(select(Branch).where(Branch.id == dump["branch_id"]))
        branch = br.scalar_one_or_none()
        if not branch or branch.restaurant_id != restaurant_id:
            dump["branch_id"] = None  # restaurant-level

    dump["restaurant_id"] = restaurant_id  # JWT'dan, har doim
    cat = Category(**dump)
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return {"id": cat.id, "name_uz": cat.name_uz}


@router.put("/categories/{cat_id}")
async def update_category(
    cat_id: int,
    data: CategoryUpdate,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Category).where(Category.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(404, "Kategoriya topilmadi")
    if restaurant_id and cat.restaurant_id and cat.restaurant_id != restaurant_id:
        raise HTTPException(403, "Bu kategoriya sizning restoraningizniki emas")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(cat, key, value)
    await db.commit()
    return {"success": True}


@router.delete("/categories/{cat_id}")
async def delete_category(
    cat_id: int,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Category).where(Category.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(404, "Kategoriya topilmadi")
    if restaurant_id and cat.restaurant_id and cat.restaurant_id != restaurant_id:
        raise HTTPException(403, "Bu kategoriya sizning restoraningizniki emas")
    cat.is_active = False
    await db.commit()
    return {"success": True}


# ── Foydalanuvchilar ──────────────────────────────────
@router.get("/users")
async def list_users(
    branch_id: Optional[int] = None,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    # SaaS izolatsiya: faqat shu restoran orderlari bilan bog'liq mijozlar
    if restaurant_id is None:
        return []
    branch_ids = _get_restaurant_branches(restaurant_id)
    if branch_id:
        # IDOR
        br = (await db.execute(select(Branch).where(Branch.id == branch_id))).scalar_one_or_none()
        if not br or br.restaurant_id != restaurant_id:
            return []
        subq = select(Order.user_id).where(Order.branch_id == branch_id).distinct()
    else:
        subq = select(Order.user_id).where(
            (Order.restaurant_id == restaurant_id) | Order.branch_id.in_(branch_ids)
        ).distinct()
    result = await db.execute(
        select(User).where(User.id.in_(subq)).order_by(User.created_at.desc())
    )
    users = result.scalars().all()
    return [
        {
            "id": u.id,
            "telegram_id": u.telegram_id,
            "full_name": u.full_name,
            "phone": u.phone,
            "language": u.language,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.get("/users/{user_id}/orders")
async def get_user_orders(
    user_id: int,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Mijoz buyurtmalari — faqat shu restoran ichidagi (SaaS izolatsiya)."""
    if restaurant_id is None:
        return []
    branch_ids = _get_restaurant_branches(restaurant_id)
    result = await db.execute(
        select(Order).where(
            Order.user_id == user_id,
            (Order.restaurant_id == restaurant_id) | Order.branch_id.in_(branch_ids),
        ).order_by(Order.created_at.desc())
    )
    orders = result.scalars().all()

    output = []
    for order in orders:
        items_res = await db.execute(
            select(OrderItem).where(OrderItem.order_id == order.id)
        )
        items = items_res.scalars().all()

        items_with_names = []
        for i in items:
            prod_res = await db.execute(select(Product).where(Product.id == i.product_id))
            prod = prod_res.scalar_one_or_none()
            items_with_names.append({
                "product_name": prod.name_uz if prod else f"#{i.product_id}",
                "quantity": i.quantity,
                "price": i.price,
            })

        output.append({
            "id": order.id,
            "status": order.status.value,
            "delivery_type": order.delivery_type.value,
            "total_price": order.total_price,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "items": items_with_names,
        })
    return output


# ── Settings (restaurant-specific) ────────────────────
from database.models import Restaurant
import hashlib as _hashlib


# ── Maxfiy sozlama maydonlari (token / secret key / merchant id) ──────
# Bu maydonlar GET'da maskalanadi (faqat oxirgi 4 belgi ko'rinadi).
# PUT'da maskalangan yoki bo'sh qiymat kelsa — eski qiymat saqlanadi.
SECRET_MASK_CHAR = "•"

SENSITIVE_SETTING_FIELDS = {
    "click_merchant_id", "click_service_id", "click_secret_key",
    "payme_merchant_id", "payme_secret_key",
    "uzum_service_id", "uzum_webhook_user", "uzum_webhook_pass",
    "telegram_provider_token_click", "telegram_provider_token_payme",
    "bot_token", "courier_bot_token",
    "yandex_api_token",
}


def _mask_secret(value: Optional[str]) -> str:
    """Maxfiy qiymatni maskalash — faqat oxirgi 4 belgi ko'rinadi.

    Bo'sh        → ""
    uzunlik ≤ 4  → to'liq yulduzcha (hech narsa ochilmasin)
    aks holda    → "••••" + oxirgi 4 belgi
    """
    if not value:
        return ""
    s = str(value)
    if len(s) <= 4:
        return SECRET_MASK_CHAR * len(s)
    return SECRET_MASK_CHAR * 4 + s[-4:]


@router.get("/settings")
async def get_settings(
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    if not restaurant_id:
        return {}
    result = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
    rest = result.scalar_one_or_none()
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")
    return {
        "restaurant_name": rest.name,
        "address": rest.address,
        "phone": rest.phone,
        "work_hours_from": rest.work_hours_from,
        "work_hours_until": rest.work_hours_until,
        "min_order": rest.min_order,
        "delivery_base_fee": rest.delivery_base_fee,
        "delivery_per_km": rest.delivery_per_km,
        "restaurant_lat": rest.restaurant_lat,
        "restaurant_lon": rest.restaurant_lon,
        "delivery_provider": rest.delivery_provider or "own",
        "yandex_api_token": _mask_secret(rest.yandex_api_token),
        "yandex_test_mode": rest.yandex_test_mode if rest.yandex_test_mode is not None else True,
        "yandex_balance_monitor_enabled": bool(rest.yandex_balance_monitor_enabled),
        "yandex_balance_amount": rest.yandex_balance_amount,
        "yandex_balance_currency": rest.yandex_balance_currency or "UZS",
        "yandex_balance_checked_at": rest.yandex_balance_checked_at.isoformat() if rest.yandex_balance_checked_at else None,
        "yandex_balance_low_threshold": float(rest.yandex_balance_low_threshold or 300000),
        "yandex_balance_critical_threshold": float(rest.yandex_balance_critical_threshold or 100000),
        "yandex_balance_status": rest.yandex_balance_status or "unknown",
        "yandex_balance_source": rest.yandex_balance_source or "manual",
        "yandex_balance_last_alert_at": rest.yandex_balance_last_alert_at.isoformat() if rest.yandex_balance_last_alert_at else None,
        "yandex_balance_block_on_critical": bool(rest.yandex_balance_block_on_critical),
        # Catering / valyuta
        "currency_auto": rest.currency_auto if rest.currency_auto is not None else True,
        "currency_rate_manual": rest.currency_rate_manual,
        "currency_rate_cache": rest.currency_rate_cache,
        "catering_payment_card": rest.catering_payment_card,
        "catering_payment_owner": rest.catering_payment_owner,
        # Catering guruhlari
        "catering_somsa_min": rest.catering_somsa_min or 100,
        "catering_somsa_step": rest.catering_somsa_step or 1,
        "catering_nan_min": rest.catering_nan_min or 40,
        "catering_nan_step": rest.catering_nan_step or 40,
        "catering_delivery_per_km_uzs": rest.catering_delivery_per_km_uzs or 5000,
        # Catering onsite sig'imi
        "catering_onsite_max": rest.catering_onsite_max or 8,
        "catering_onsite_window_hours": rest.catering_onsite_window_hours or 2,
        # To'lov gateway'lar (maxfiy maydonlar maskalanadi — oxirgi 4 belgi)
        "click_merchant_id": _mask_secret(rest.click_merchant_id),
        "click_service_id": _mask_secret(rest.click_service_id),
        "click_secret_key": _mask_secret(rest.click_secret_key),
        "click_enabled": bool(rest.click_enabled),
        "payme_merchant_id": _mask_secret(rest.payme_merchant_id),
        "payme_secret_key": _mask_secret(rest.payme_secret_key),
        "payme_enabled": bool(rest.payme_enabled),
        # Uzum Bank
        "uzum_service_id": _mask_secret(rest.uzum_service_id),
        "uzum_webhook_user": _mask_secret(rest.uzum_webhook_user),
        "uzum_webhook_pass": _mask_secret(rest.uzum_webhook_pass),
        "uzum_enabled": bool(rest.uzum_enabled),
        # Faza 1.4: Telegram Native Payments
        "telegram_provider_token_click": _mask_secret(rest.telegram_provider_token_click),
        "telegram_provider_token_payme": _mask_secret(rest.telegram_provider_token_payme),
        "payment_test_mode": bool(rest.payment_test_mode),
        "is_vat_payer": bool(rest.is_vat_payer),
        "vat_percent": float(rest.vat_percent or 12.0),
        "enforce_prepayment_for_delivery": bool(rest.enforce_prepayment_for_delivery),
        "catering_notifier_chat_id": rest.catering_notifier_chat_id or "",
        "bot_token": _mask_secret(rest.bot_token),
        "courier_bot_token": _mask_secret(rest.courier_bot_token),
        # Faza 4-5: to'lov sozlamalari
        "catering_service_fee": float(rest.catering_service_fee or 0),
        "prepayment_required_above": float(rest.prepayment_required_above or 0),
        # AI Operator (restoran-spesifik; provider/model/api_key super-admin'da)
        "ai_agent_enabled": bool(rest.ai_agent_enabled),
        "ai_agent_prompt": rest.ai_agent_prompt or "",
        "ai_agent_voice": rest.ai_agent_voice or "female",
        "ai_agent_greeting": rest.ai_agent_greeting or "",
        "ai_agent_work_hours_only": bool(rest.ai_agent_work_hours_only),
        "ai_agent_max_call_minutes": int(rest.ai_agent_max_call_minutes or 10),
        "ai_agent_fallback_phone": rest.ai_agent_fallback_phone or "",
        "ai_agent_language": rest.ai_agent_language or "uz",
    }


@router.put("/settings")
async def update_settings(
    data: SettingsUpdate,
    restaurant_id: int = Depends(get_restaurant_context),
    db: AsyncSession = Depends(get_db),
):
    """Restoran sozlamalarini saqlash — super-admin X-Restaurant-Context header bilan
    boshqa restoranni yangilashi mumkin (audit log'ga yozuv tushadi).
    """
    if not restaurant_id:
        raise HTTPException(400, "restaurant_id kerak")
    result = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
    rest = result.scalar_one_or_none()
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")

    update_map = {
        "restaurant_name": "name",
        "address": "address",
        "phone": "phone",
        "work_hours_from": "work_hours_from",
        "work_hours_until": "work_hours_until",
        "min_order": "min_order",
        "delivery_base_fee": "delivery_base_fee",
        "delivery_per_km": "delivery_per_km",
        "restaurant_lat": "restaurant_lat",
        "restaurant_lon": "restaurant_lon",
        "delivery_provider": "delivery_provider",
        "yandex_api_token": "yandex_api_token",
        "yandex_test_mode": "yandex_test_mode",
        "yandex_balance_monitor_enabled": "yandex_balance_monitor_enabled",
        "yandex_balance_amount": "yandex_balance_amount",
        "yandex_balance_currency": "yandex_balance_currency",
        "yandex_balance_low_threshold": "yandex_balance_low_threshold",
        "yandex_balance_critical_threshold": "yandex_balance_critical_threshold",
        "yandex_balance_block_on_critical": "yandex_balance_block_on_critical",
        "currency_auto": "currency_auto",
        "currency_rate_manual": "currency_rate_manual",
        "catering_payment_card": "catering_payment_card",
        "catering_payment_owner": "catering_payment_owner",
        "catering_somsa_min": "catering_somsa_min",
        "catering_somsa_step": "catering_somsa_step",
        "catering_nan_min": "catering_nan_min",
        "catering_nan_step": "catering_nan_step",
        "catering_delivery_per_km_uzs": "catering_delivery_per_km_uzs",
        "click_merchant_id": "click_merchant_id",
        "click_service_id": "click_service_id",
        "click_secret_key": "click_secret_key",
        "click_enabled": "click_enabled",
        "payme_merchant_id": "payme_merchant_id",
        "payme_secret_key": "payme_secret_key",
        "payme_enabled": "payme_enabled",
        "uzum_service_id": "uzum_service_id",
        "uzum_webhook_user": "uzum_webhook_user",
        "uzum_webhook_pass": "uzum_webhook_pass",
        "uzum_enabled": "uzum_enabled",
        "telegram_provider_token_click": "telegram_provider_token_click",
        "telegram_provider_token_payme": "telegram_provider_token_payme",
        "payment_test_mode": "payment_test_mode",
        "is_vat_payer": "is_vat_payer",
        "vat_percent": "vat_percent",
        "enforce_prepayment_for_delivery": "enforce_prepayment_for_delivery",
        "catering_notifier_chat_id": "catering_notifier_chat_id",
        "bot_token": "bot_token",
        "courier_bot_token": "courier_bot_token",
        "catering_service_fee": "catering_service_fee",
        "prepayment_required_above": "prepayment_required_above",
        "ai_agent_enabled": "ai_agent_enabled",
        "ai_agent_prompt": "ai_agent_prompt",
        "ai_agent_voice": "ai_agent_voice",
        "ai_agent_greeting": "ai_agent_greeting",
        "ai_agent_work_hours_only": "ai_agent_work_hours_only",
        "ai_agent_max_call_minutes": "ai_agent_max_call_minutes",
        "ai_agent_fallback_phone": "ai_agent_fallback_phone",
        "ai_agent_language": "ai_agent_language",
    }
    for form_key, db_key in update_map.items():
        val = getattr(data, form_key, None)
        if val is None:
            continue
        # Maxfiy maydon: maskalangan (•) yoki bo'sh qiymat kelsa — eski qiymat saqlanadi.
        # Faqat admin yangi haqiqiy qiymat kiritganda almashtiriladi.
        if form_key in SENSITIVE_SETTING_FIELDS:
            if isinstance(val, str) and (val == "" or SECRET_MASK_CHAR in val):
                continue
        setattr(rest, db_key, val)

    await db.commit()
    return {"success": True}


# ── Yandex balance monitoring ────────────────────────
@router.get("/yandex-balance")
async def get_yandex_balance(
    restaurant_id: int = Depends(get_restaurant_context),
    db: AsyncSession = Depends(get_db),
):
    if not restaurant_id:
        raise HTTPException(400, "restaurant_id kerak")
    rest = (await db.execute(
        select(Restaurant).where(Restaurant.id == restaurant_id)
    )).scalar_one_or_none()
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")

    from api.services.yandex_balance import yandex_balance_ai_template, yandex_balance_snapshot
    data = yandex_balance_snapshot(rest)
    data["ai_template"] = yandex_balance_ai_template()
    return data


@router.post("/yandex-balance/check-now")
async def check_yandex_balance_now(
    restaurant_id: int = Depends(get_restaurant_context),
    db: AsyncSession = Depends(get_db),
):
    if not restaurant_id:
        raise HTTPException(400, "restaurant_id kerak")
    rest = (await db.execute(
        select(Restaurant).where(Restaurant.id == restaurant_id)
    )).scalar_one_or_none()
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")

    from api.services.yandex_balance import check_restaurant_yandex_balance, yandex_balance_ai_template
    data = await check_restaurant_yandex_balance(db, rest, notify=True)
    data["ai_template"] = yandex_balance_ai_template()
    return data


# ── Profil (restaurant-specific) ─────────────────────
@router.get("/profile")
async def get_profile(
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Joriy admin va restoran profili.

    Restaurant admin uchun: o'z restorani ma'lumotlari (INN, balans, status).
    Super admin uchun (rid=None): platform-level info.

    Faza 1: INN, is_verified, subscription_status va balans ham qaytariladi.
    """
    if restaurant_id:
        result = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
        rest = result.scalar_one_or_none()
        if not rest:
            return {"name": settings.ADMIN_USERNAME, "username": settings.ADMIN_USERNAME}

        # Balans hisobi: cancelled emas total revenue (so'm)
        from database.models import Order, OrderStatus
        revenue = (await db.execute(
            select(func.coalesce(func.sum(Order.total_price), 0))
            .where(Order.restaurant_id == restaurant_id, Order.status != OrderStatus.cancelled)
        )).scalar() or 0.0
        # To'langan to'lovlar (paid)
        from database.models import Payment
        paid_total_tiyin = (await db.execute(
            select(func.coalesce(func.sum(Payment.amount_tiyin), 0))
            .where(Payment.restaurant_id == restaurant_id, Payment.status == "success")
        )).scalar() or 0
        # Komissiya to'lovlari
        from database.models import CommissionPayment
        commission_paid = (await db.execute(
            select(func.coalesce(func.sum(CommissionPayment.amount), 0))
            .where(CommissionPayment.restaurant_id == restaurant_id,
                   CommissionPayment.status == "confirmed")
        )).scalar() or 0.0

        return {
            # Identity
            "name": rest.name,
            "username": rest.admin_username,
            "slug": rest.slug,
            "inn": rest.inn,
            "phone": rest.phone,
            "address": rest.address,
            "logo_url": rest.logo_url,
            # Verifikatsiya va holat
            "is_verified": bool(rest.is_verified),
            "status": rest.status or "active",                       # admin-level
            "subscription_status": rest.subscription_status or "active",  # billing-level
            # Tarif
            "plan_id": rest.plan_id,
            "plan_expires_at": rest.plan_expires_at.isoformat() if rest.plan_expires_at else None,
            "commission_percent": float(rest.commission_percent or 0),
            # Qo'shimcha funksiyalar holati (banner uchun)
            "ai_agent_enabled": bool(rest.ai_agent_enabled),
            # Balans / moliyaviy hisob
            "balance": {
                "orders_revenue_uzs": float(revenue),
                "paid_total_tiyin": int(paid_total_tiyin),
                "commission_paid_uzs": float(commission_paid),
            },
        }

    return {"name": settings.ADMIN_USERNAME, "username": settings.ADMIN_USERNAME}


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


@router.put("/profile")
async def update_profile(
    data: ProfileUpdate,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Restoran admin profili: login (username) va/yoki parol o'zgartirish.

    Parol o'zgartirish uchun **eski parol majburiy** (xavfsizlik talabi).
    Faqat login o'zgartirsa eski parol shart emas.
    """
    if restaurant_id:
        result = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
        rest = result.scalar_one_or_none()
        if not rest:
            raise HTTPException(404, "Restoran topilmadi")

        # Parol o'zgartirilayotgan bo'lsa — eski parolni tekshirish
        if data.new_password:
            if not data.current_password:
                raise HTTPException(400, "Parolni o'zgartirish uchun eski parol kerak")
            current_hash = _hashlib.sha256(data.current_password.encode()).hexdigest()
            # Eski parol bcrypt yoki SHA-256 bo'lishi mumkin (backward compat)
            from api.services.auth_service import verify_password
            stored = rest.admin_password_hash or ""
            if not (stored == current_hash or verify_password(data.current_password, stored)):
                raise HTTPException(403, "Eski parol noto'g'ri")
            rest.admin_password_hash = _hashlib.sha256(data.new_password.encode()).hexdigest()

        if data.username:
            # Username unique tekshirish (boshqa restoran ishlatmasligi shart)
            existing = (await db.execute(
                select(Restaurant).where(
                    Restaurant.admin_username == data.username,
                    Restaurant.id != rest.id,
                )
            )).scalar_one_or_none()
            if existing:
                raise HTTPException(409, "Bu login band — boshqa nom tanlang")
            rest.admin_username = data.username

        await db.commit()
        return {"success": True, "username": rest.admin_username}

    # Fallback: .env admin
    env_path = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(env_path):
        raise HTTPException(500, ".env fayl topilmadi")
    with open(env_path, "r") as f:
        lines = f.readlines()
    changes = {}
    if data.username:
        changes["ADMIN_USERNAME"] = data.username
        settings.ADMIN_USERNAME = data.username
    if data.new_password:
        changes["ADMIN_PASSWORD"] = data.new_password
        settings.ADMIN_PASSWORD = data.new_password
    if changes:
        new_lines = []
        updated_keys = set()
        for line in lines:
            key = line.split("=", 1)[0].strip() if "=" in line else ""
            if key in changes:
                new_lines.append(f"{key}={changes[key]}\n")
                updated_keys.add(key)
            else:
                new_lines.append(line)
        for key, val in changes.items():
            if key not in updated_keys:
                new_lines.append(f"{key}={val}\n")
        with open(env_path, "w") as f:
            f.writelines(new_lines)
    return {"success": True, "username": settings.ADMIN_USERNAME}


# ── Adminlar boshqaruvi ──────────────────────────────
@router.get("/admins")
async def list_admins(
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(Admin)
    if restaurant_id:
        query = query.where(Admin.restaurant_id == restaurant_id)
    query = query.order_by(Admin.created_at.desc())
    result = await db.execute(query)
    admins = result.scalars().all()
    return [
        {
            "id": a.id,
            "restaurant_id": a.restaurant_id,
            "username": a.username,
            "role": a.role,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in admins
    ]


@router.post("/admins")
async def create_admin(
    data: AdminCreate,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    if not restaurant_id:
        raise HTTPException(400, "restaurant_id kerak")
    # Username takrorlanmasligini tekshirish
    existing = await db.execute(
        select(Admin).where(Admin.username == data.username, Admin.restaurant_id == restaurant_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Bu username allaqachon mavjud")
    admin = Admin(
        restaurant_id=restaurant_id,
        username=data.username,
        password_hash=_hashlib.sha256(data.password.encode()).hexdigest(),
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return {"id": admin.id, "username": admin.username}


@router.delete("/admins/{admin_id}")
async def delete_admin(
    admin_id: int,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Admin).where(Admin.id == admin_id))
    admin = result.scalar_one_or_none()
    if not admin:
        raise HTTPException(404, "Admin topilmadi")
    if restaurant_id and admin.restaurant_id != restaurant_id:
        raise HTTPException(403, "Bu admin sizning restoraningizniki emas")
    await db.delete(admin)
    await db.commit()
    return {"success": True}


# ── Catering notifier — manual trigger (sinov uchun) ─

@router.post("/catering-notifier/test")
async def trigger_catering_notifier(
    restaurant_id: int = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Hozir ertangi catering ro'yxatini joriy restoranga yuborish (sinov)."""
    from api.services.catering_notifier import send_tomorrow_catering_notifications
    # Faqat shu restoran uchun chaqirish — boshqalarni o'tkazib yuborish
    res = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
    rest = res.scalar_one_or_none()
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")
    if not (rest.catering_notifier_chat_id or "").strip():
        raise HTTPException(400, "Avval Settings'da Catering notifier chat ID ni o'rnating")
    # Vaqtincha boshqa restoranlarni notifier'dan o'chirib, faqat shu uchun chaqiramiz
    # Soddalik uchun: to'g'ridan-to'g'ri shu restoran uchun ishlatamiz
    from api.services.catering_notifier import _send_telegram, _format_orders_message
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from sqlalchemy.orm import selectinload
    import os

    bot_token = (os.getenv("CATERING_NOTIFIER_BOT_TOKEN") or "").strip()
    if not bot_token:
        raise HTTPException(503, "CATERING_NOTIFIER_BOT_TOKEN env'da o'rnatilmagan")

    tz = ZoneInfo("Asia/Tashkent")
    tomorrow = (datetime.now(tz) + timedelta(days=1)).date()
    orders_q = await db.execute(
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.user))
        .where(
            Order.restaurant_id == restaurant_id,
            Order.order_kind == "catering",
            Order.status != OrderStatus.cancelled,
            Order.schedule_date == tomorrow.isoformat(),
        )
        .order_by(Order.schedule_time)
    )
    orders = list(orders_q.scalars().all())
    text = _format_orders_message(datetime.combine(tomorrow, datetime.min.time()), orders)
    ok = await _send_telegram(bot_token, rest.catering_notifier_chat_id, text)
    return {"ok": ok, "orders_count": len(orders), "chat_id": rest.catering_notifier_chat_id}


# ── Bot tokenlarini sinash ─────────────────────────

@router.post("/bots/check")
async def check_bot_tokens(
    restaurant_id: int = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Joriy restoran bot tokenlarini Telegram getMe() orqali tekshirish."""
    import httpx
    res = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
    rest = res.scalar_one_or_none()
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")

    async def _check(token: Optional[str]) -> dict:
        if not token:
            return {"configured": False, "online": False}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            if r.status_code == 200:
                d = r.json().get("result", {})
                return {
                    "configured": True, "online": True,
                    "username": d.get("username"),
                    "first_name": d.get("first_name"),
                    "id": d.get("id"),
                }
            return {"configured": True, "online": False, "error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"configured": True, "online": False, "error": str(e)[:80]}

    return {
        "customer_bot": await _check(rest.bot_token),
        "courier_bot": await _check(rest.courier_bot_token),
        "note": "Yangi tokenlarni Telegram'dan ulash uchun super-admin'dan 'Bots service restart' so'rang",
    }


# ── Plan / tarif ma'lumoti ───────────────────────────
@router.get("/me/plan")
async def get_my_plan(
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Joriy restoran tarifi va undagi yoqilgan funksiyalar.

    Frontend sidebar badge va "Locked" menyu elementlarini ko'rsatish uchun ishlatadi.
    """
    if not restaurant_id:
        # Super admin restaurantsiz so'roq qilsa
        return {"plan": None, "features": {}}

    rest_result = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
    rest = rest_result.scalar_one_or_none()
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")

    plan = None
    if rest.plan_id:
        plan_result = await db.execute(select(Plan).where(Plan.id == rest.plan_id))
        plan = plan_result.scalar_one_or_none()

    if not plan:
        return {
            "plan": {"id": None, "name": "Tariff yo'q", "slug": None, "max_branches_limit": 1},
            "features": {"catering": False, "ai_agent": False, "yandex": False, "multi_branch": False},
            "order_limit": 0,
        }

    return {
        "plan": {
            "id": plan.id,
            "name": plan.name,
            "slug": plan.slug,
            "monthly_price": plan.monthly_price,
            "commission_percent": plan.commission_percent,
            "max_branches_limit": int(plan.max_branches_limit or 1),
        },
        "features": {
            "catering": bool(plan.has_catering),
            "ai_agent": bool(plan.has_ai_agent),
            "yandex": bool(plan.has_yandex),
            "multi_branch": bool(plan.has_multi_branch),
        },
        "order_limit": plan.order_limit,
    }
