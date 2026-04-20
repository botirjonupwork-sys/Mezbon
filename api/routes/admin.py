"""Admin uchun maxsus endpointlar — mahsulot CRUD, kategoriya, statistika"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel
import shutil
import os
import uuid

from api.database import get_db
from api.schemas import CategoryOut
from api.config import settings
from database.models import (
    Product, Category, Order, OrderItem, User, Review, OrderStatus, Courier, Branch, Admin
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


class AdminCreate(BaseModel):
    username: str
    password: str


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    new_password: Optional[str] = None


def _get_restaurant_branches(restaurant_id: int):
    """Restaurant'ning barcha branch_id larini olish uchun subquery"""
    return select(Branch.id).where(Branch.restaurant_id == restaurant_id)


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


@router.delete("/upload-image")
async def delete_image(url: str):
    """Eski rasmni fayl tizimidan o'chirish."""
    if not url or not url.startswith("/static/images/products/"):
        return {"success": False, "reason": "invalid_url"}
    filename = url.rsplit("/", 1)[-1]
    filepath = os.path.join(UPLOAD_DIR, filename)
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            return {"success": True}
        except OSError:
            return {"success": False, "reason": "os_error"}
    return {"success": False, "reason": "not_found"}


# ── Statistika ────────────────────────────────────────
@router.get("/stats")
async def get_stats(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    branch_id: Optional[int] = None,
    restaurant_id: Optional[int] = None,
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

    order_filters = [
        func.date(Order.created_at) >= d_from,
        func.date(Order.created_at) <= d_to,
    ]
    if branch_id:
        order_filters.append(Order.branch_id == branch_id)
    elif restaurant_id:
        branch_ids = _get_restaurant_branches(restaurant_id)
        order_filters.append(Order.branch_id.in_(branch_ids))

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

    if restaurant_id:
        branch_ids = _get_restaurant_branches(restaurant_id)
        user_subq = select(Order.user_id).where(Order.branch_id.in_(branch_ids)).distinct()
        total_users = await db.execute(select(func.count()).select_from(
            select(User.id).where(User.id.in_(user_subq)).subquery()
        ))
    else:
        total_users = await db.execute(select(func.count(User.id)))
    users_count = total_users.scalar() or 0

    active_filters = [
        Order.status.notin_([OrderStatus.delivered, OrderStatus.cancelled])
    ]
    if branch_id:
        active_filters.append(Order.branch_id == branch_id)
    elif restaurant_id:
        branch_ids = _get_restaurant_branches(restaurant_id)
        active_filters.append(Order.branch_id.in_(branch_ids))
    active_orders = await db.execute(
        select(func.count(Order.id)).where(*active_filters)
    )
    active_count = active_orders.scalar() or 0

    review_q = select(
        func.avg(Review.rating).label("avg"),
        func.count(Review.id).label("total")
    )
    if branch_id:
        review_q = review_q.where(Review.branch_id == branch_id)
    elif restaurant_id:
        branch_ids = _get_restaurant_branches(restaurant_id)
        review_q = review_q.where(Review.branch_id.in_(branch_ids))
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
    restaurant_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    query = select(Order).order_by(Order.created_at.desc())

    if branch_id:
        query = query.where(Order.branch_id == branch_id)
    elif restaurant_id:
        branch_ids = _get_restaurant_branches(restaurant_id)
        query = query.where(Order.branch_id.in_(branch_ids))

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
async def list_products(
    branch_id: Optional[int] = None,
    restaurant_id: Optional[int] = None,
    category_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Product).where(Product.is_active == True).order_by(Product.category_id, Product.id)
    if category_id:
        query = query.where(Product.category_id == category_id)
    if branch_id:
        # Shu filialniki + restaurant darajasidagi (branch_id NULL) mahsulotlar
        br = await db.execute(select(Branch).where(Branch.id == branch_id))
        branch = br.scalar_one_or_none()
        if branch:
            query = query.where(
                (Product.branch_id == branch_id) |
                ((Product.restaurant_id == branch.restaurant_id) & (Product.branch_id.is_(None)))
            )
        else:
            query = query.where(Product.branch_id == branch_id)
    elif restaurant_id:
        branch_ids = _get_restaurant_branches(restaurant_id)
        query = query.where(
            (Product.restaurant_id == restaurant_id) | Product.branch_id.in_(branch_ids)
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
        }
        for p in products
    ]


@router.post("/products")
async def create_product(
    data: ProductCreate,
    restaurant_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    dump = data.model_dump()
    # branch_id bo'lsa — shu branchning restaurant_id sini olish
    if dump.get("branch_id"):
        br = await db.execute(select(Branch).where(Branch.id == dump["branch_id"]))
        branch = br.scalar_one_or_none()
        if branch:
            dump["restaurant_id"] = branch.restaurant_id
    elif restaurant_id:
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
    restaurant_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Mahsulot topilmadi")

    # Faqat yuborilgan maydonlarni yangilash (qolganlarini o'zgartirmaslik)
    dump = data.model_dump(exclude_unset=True)

    # branch_id yangilansa — restaurant_id ni ham yangilash
    if "branch_id" in dump and dump["branch_id"]:
        br = await db.execute(select(Branch).where(Branch.id == dump["branch_id"]))
        branch = br.scalar_one_or_none()
        if branch:
            dump["restaurant_id"] = branch.restaurant_id
    elif restaurant_id and "restaurant_id" not in dump:
        dump["restaurant_id"] = restaurant_id

    for key, value in dump.items():
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
async def list_categories(
    branch_id: Optional[int] = None,
    restaurant_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Category).where(Category.is_active == True).order_by(Category.order)
    if branch_id:
        # Shu filialniki + restaurant darajasidagi (branch_id NULL) kategoriyalar
        br = await db.execute(select(Branch).where(Branch.id == branch_id))
        branch = br.scalar_one_or_none()
        if branch:
            query = query.where(
                (Category.branch_id == branch_id) |
                ((Category.restaurant_id == branch.restaurant_id) & (Category.branch_id.is_(None)))
            )
        else:
            query = query.where(Category.branch_id == branch_id)
    elif restaurant_id:
        branch_ids = _get_restaurant_branches(restaurant_id)
        query = query.where(
            (Category.restaurant_id == restaurant_id) | Category.branch_id.in_(branch_ids)
        )
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/categories")
async def create_category(
    data: CategoryCreate,
    restaurant_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    dump = data.model_dump()
    if dump.get("branch_id"):
        br = await db.execute(select(Branch).where(Branch.id == dump["branch_id"]))
        branch = br.scalar_one_or_none()
        if branch:
            dump["restaurant_id"] = branch.restaurant_id
    elif restaurant_id:
        dump["restaurant_id"] = restaurant_id
    cat = Category(**dump)
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return {"id": cat.id, "name_uz": cat.name_uz}


@router.put("/categories/{cat_id}")
async def update_category(
    cat_id: int,
    data: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Category).where(Category.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(404, "Kategoriya topilmadi")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(cat, key, value)
    await db.commit()
    return {"success": True}


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
async def list_users(
    branch_id: Optional[int] = None,
    restaurant_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    if branch_id:
        subq = select(Order.user_id).where(Order.branch_id == branch_id).distinct()
        result = await db.execute(
            select(User).where(User.id.in_(subq)).order_by(User.created_at.desc())
        )
    elif restaurant_id:
        branch_ids = _get_restaurant_branches(restaurant_id)
        subq = select(Order.user_id).where(Order.branch_id.in_(branch_ids)).distinct()
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


# ── Settings (restaurant-specific) ────────────────────
from database.models import Restaurant
import hashlib as _hashlib


@router.get("/settings")
async def get_settings(
    restaurant_id: Optional[int] = None,
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
        "yandex_api_token": rest.yandex_api_token,
        "yandex_test_mode": rest.yandex_test_mode if rest.yandex_test_mode is not None else True,
    }


@router.put("/settings")
async def update_settings(
    data: SettingsUpdate,
    restaurant_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
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
    }
    for form_key, db_key in update_map.items():
        val = getattr(data, form_key, None)
        if val is not None:
            setattr(rest, db_key, val)

    await db.commit()
    return {"success": True}


# ── Profil (restaurant-specific) ─────────────────────
@router.get("/profile")
async def get_profile(
    restaurant_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    if restaurant_id:
        result = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
        rest = result.scalar_one_or_none()
        if rest:
            return {"name": rest.name, "username": rest.admin_username}
    return {"name": settings.ADMIN_USERNAME, "username": settings.ADMIN_USERNAME}


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


@router.put("/profile")
async def update_profile(
    data: ProfileUpdate,
    restaurant_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    if restaurant_id:
        result = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
        rest = result.scalar_one_or_none()
        if not rest:
            raise HTTPException(404, "Restoran topilmadi")
        if data.username:
            rest.admin_username = data.username
        if data.new_password:
            rest.admin_password_hash = _hashlib.sha256(data.new_password.encode()).hexdigest()
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
    restaurant_id: Optional[int] = None,
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
    restaurant_id: Optional[int] = None,
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
async def delete_admin(admin_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Admin).where(Admin.id == admin_id))
    admin = result.scalar_one_or_none()
    if not admin:
        raise HTTPException(404, "Admin topilmadi")
    await db.delete(admin)
    await db.commit()
    return {"success": True}
