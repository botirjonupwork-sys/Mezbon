"""Admin uchun maxsus endpointlar — mahsulot CRUD, kategoriya, statistika"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel
import shutil
import os
import uuid

from api.database import get_db
from api.schemas import CategoryOut
from api.config import settings
from fastapi import Query
from database.models import (
    Product, Category, Order, OrderItem, User, Review, OrderStatus, Courier
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


class CategoryCreate(BaseModel):
    name_uz: str
    name_ru: Optional[str] = None
    order: int = 0
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


class AdminCreate(BaseModel):
    username: str
    password: str


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    new_password: Optional[str] = None


# ── Image upload ───────────────────────────────────────
@router.post("/upload-image")
async def upload_image(file: UploadFile = File(...)):
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
    if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
        raise HTTPException(400, "Faqat rasm fayllar (jpg, png, webp)")
    filename = f"{uuid.uuid4()}.{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"url": f"/static/images/products/{filename}"}


# ── Statistika ────────────────────────────────────────
@router.get("/stats")
async def get_stats(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    branch_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    # Date range
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

    # Branch filter
    order_filters = [
        func.date(Order.created_at) >= d_from,
        func.date(Order.created_at) <= d_to,
    ]
    if branch_id:
        order_filters.append(Order.branch_id == branch_id)

    # Zakazlar soni
    orders_q = await db.execute(
        select(func.count(Order.id)).where(*order_filters)
    )
    orders_count = orders_q.scalar() or 0

    # Daromad
    revenue_q = await db.execute(
        select(func.sum(Order.total_price)).where(
            *order_filters,
            Order.status != OrderStatus.cancelled
        )
    )
    revenue = revenue_q.scalar() or 0.0

    # Jami foydalanuvchilar
    total_users = await db.execute(select(func.count(User.id)))
    users_count = total_users.scalar() or 0

    # Faol zakazlar
    active_filters = [
        Order.status.notin_([OrderStatus.delivered, OrderStatus.cancelled])
    ]
    if branch_id:
        active_filters.append(Order.branch_id == branch_id)
    active_orders = await db.execute(
        select(func.count(Order.id)).where(*active_filters)
    )
    active_count = active_orders.scalar() or 0

    # O'rtacha reyting
    review_q = select(
        func.avg(Review.rating).label("avg"),
        func.count(Review.id).label("total")
    )
    if branch_id:
        review_q = review_q.where(Review.branch_id == branch_id)
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
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    query = select(Order).order_by(Order.created_at.desc())

    if branch_id:
        query = query.where(Order.branch_id == branch_id)

    if status:
        try:
            query = query.where(Order.status == OrderStatus(status))
        except ValueError:
            raise HTTPException(400, f"Noto'g'ri status: {status}")

    if date_from:
        try:
            d_from = datetime.strptime(date_from, "%Y-%m-%d").date()
            query = query.where(func.date(Order.created_at) >= d_from)
        except ValueError:
            pass

    if date_to:
        try:
            d_to = datetime.strptime(date_to, "%Y-%m-%d").date()
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

        # Product nomlarini olamiz
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
            "comment": order.comment,
            "total_price": order.total_price,
            "delivery_fee": order.delivery_fee,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "user": {"full_name": user.full_name, "phone": user.phone} if user else None,
            "items": items_with_names,
        })
    return output


# ── Mahsulot CRUD ─────────────────────────────────────
@router.get("/products")
async def list_products(branch_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    query = select(Product).order_by(Product.category_id, Product.id)
    if branch_id:
        query = query.where(Product.branch_id == branch_id)
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
        }
        for p in products
    ]


@router.post("/products")
async def create_product(data: ProductCreate, db: AsyncSession = Depends(get_db)):
    product = Product(**data.model_dump())
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return {"id": product.id, "name_uz": product.name_uz}


@router.put("/products/{product_id}")
async def update_product(
    product_id: int,
    data: ProductCreate,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Mahsulot topilmadi")

    for key, value in data.model_dump().items():
        setattr(product, key, value)

    await db.commit()
    return {"success": True}


@router.delete("/products/{product_id}")
async def delete_product(product_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Mahsulot topilmadi")
    product.is_active = False
    await db.commit()
    return {"success": True}


# ── Kategoriya CRUD ───────────────────────────────────
@router.get("/categories")
async def list_categories(branch_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    query = select(Category).order_by(Category.order)
    if branch_id:
        query = query.where(Category.branch_id == branch_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/categories")
async def create_category(data: CategoryCreate, db: AsyncSession = Depends(get_db)):
    cat = Category(**data.model_dump())
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return {"id": cat.id, "name_uz": cat.name_uz}


@router.delete("/categories/{cat_id}")
async def delete_category(cat_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).where(Category.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(404, "Kategoriya topilmadi")
    cat.is_active = False
    await db.commit()
    return {"success": True}


# ── Foydalanuvchilar ──────────────────────────────────
@router.get("/users")
async def list_users(branch_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    if branch_id:
        # Shu filialga buyurtma bergan foydalanuvchilar
        subq = select(Order.user_id).where(Order.branch_id == branch_id).distinct()
        result = await db.execute(
            select(User).where(User.id.in_(subq)).order_by(User.created_at.desc())
        )
    else:
        result = await db.execute(select(User).order_by(User.created_at.desc()))
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
async def get_user_orders(user_id: int, db: AsyncSession = Depends(get_db)):
    """Foydalanuvchining barcha zakazlari"""
    result = await db.execute(
        select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc())
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


# ── Settings ──────────────────────────────────────────
# Oddiy JSON fayl orqali sozlamalarni saqlash
SETTINGS_FILE = "settings.json"


def _load_settings() -> dict:
    import json
    defaults = {
        "language": "uz",
        "min_order": 20000,
        "work_hours_from": "09:00",
        "work_hours_until": "22:00",
        "restaurant_name": "Muhsina Dollar Somsa",
        "address": "Toshkent sh.",
        "phone": "+998901234567",
    }
    if not os.path.exists(SETTINGS_FILE):
        return defaults
    try:
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)
        return {**defaults, **data}
    except Exception:
        return defaults


def _save_settings(data: dict):
    import json
    existing = _load_settings()
    existing.update({k: v for k, v in data.items() if v is not None})
    with open(SETTINGS_FILE, "w") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


@router.get("/settings")
async def get_settings():
    return _load_settings()


@router.put("/settings")
async def update_settings(data: SettingsUpdate):
    _save_settings(data.model_dump())
    return _load_settings()


# ── Profil ────────────────────────────────────────────
@router.get("/profile")
async def get_profile():
    """Hozirgi admin profili"""
    return {
        "name": settings.ADMIN_USERNAME,
        "username": settings.ADMIN_USERNAME,
    }


@router.put("/profile")
async def update_profile(data: ProfileUpdate):
    """Admin profilini yangilash (ism, username, parol)"""
    import json as _json

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
        # Yangi kalitlarni qo'shish
        for key, val in changes.items():
            if key not in updated_keys:
                new_lines.append(f"{key}={val}\n")
        with open(env_path, "w") as f:
            f.writelines(new_lines)

    return {"success": True, "username": settings.ADMIN_USERNAME}


# ── Adminlar ──────────────────────────────────────────
ADMINS_FILE = "admins.json"


def _load_admins() -> list:
    import json
    if not os.path.exists(ADMINS_FILE):
        return []
    try:
        with open(ADMINS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save_admins(admins: list):
    import json
    with open(ADMINS_FILE, "w") as f:
        json.dump(admins, f, ensure_ascii=False, indent=2)


@router.get("/admins")
async def list_admins():
    admins = _load_admins()
    result = []
    # .env dagi super admin
    result.append({
        "id": 0,
        "username": settings.ADMIN_USERNAME,
        "created_at": None,
        "is_super": True,
    })
    # admins.json dagi adminlar
    for a in admins:
        result.append({
            "id": a["id"],
            "username": a["username"],
            "created_at": a["created_at"],
            "is_super": False,
        })
    return result


@router.post("/admins")
async def create_admin(data: AdminCreate):
    import hashlib
    from datetime import datetime as dt
    admins = _load_admins()
    if any(a["username"] == data.username for a in admins):
        raise HTTPException(400, "Bu username allaqachon mavjud")
    new_id = max((a["id"] for a in admins), default=0) + 1
    hashed = hashlib.sha256(data.password.encode()).hexdigest()
    admins.append({
        "id": new_id,
        "username": data.username,
        "password": hashed,
        "created_at": dt.utcnow().isoformat(),
    })
    _save_admins(admins)
    return {"id": new_id, "username": data.username}


@router.delete("/admins/{admin_id}")
async def delete_admin(admin_id: int):
    admins = _load_admins()
    new_list = [a for a in admins if a["id"] != admin_id]
    if len(new_list) == len(admins):
        raise HTTPException(404, "Admin topilmadi")
    _save_admins(new_list)
    return {"success": True}
