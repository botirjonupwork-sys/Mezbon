from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from typing import Optional

from api.auth_deps import require_restaurant_admin
from zoneinfo import ZoneInfo

from api.database import get_db
from api.schemas import CategoryOut, ProductOut
from database.models import Category, Product, Branch

router = APIRouter(prefix="/menu", tags=["menu"])

UZ_TZ = ZoneInfo("Asia/Tashkent")


def is_product_available(product: Product) -> bool:
    """Mahsulot hozir mavjudligini tekshirish (O'zbekiston vaqti bilan)."""
    if product.is_stop:
        return False
    if not product.has_time_limit:
        return True

    now = datetime.now(UZ_TZ).strftime("%H:%M")
    if product.available_from and product.available_until:
        # Oddiy holatda: 09:00–22:00
        if product.available_from <= product.available_until:
            return product.available_from <= now <= product.available_until
        # Tungi oraliq: 22:00–06:00 (kun o'zgaradi)
        return now >= product.available_from or now <= product.available_until
    return True


async def _resolve_restaurant_id(
    branch_id: Optional[int], restaurant_id: Optional[int], db: AsyncSession,
) -> Optional[int]:
    """SaaS izolatsiya: branch_id berilsa undan restaurant_id ni olib qaytaramiz.

    Returns: restaurant_id (int) yoki None (ikkalasi ham yo'q yoki branch yo'q).
    """
    if branch_id:
        br = await db.execute(select(Branch).where(Branch.id == branch_id))
        branch = br.scalar_one_or_none()
        if branch:
            # Agar restaurant_id ham berilgan bo'lsa, mosligi tekshiriladi
            if restaurant_id and branch.restaurant_id != restaurant_id:
                return None
            return branch.restaurant_id
        return None
    return restaurant_id


@router.get("/categories", response_model=list[CategoryOut])
async def get_categories(
    branch_id: Optional[int] = None,
    restaurant_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Mijoz menyu kategoriyalari — SaaS izolatsiya: restaurant_id majburiy."""
    rid = await _resolve_restaurant_id(branch_id, restaurant_id, db)
    if not rid:
        return []   # restoran konteksti yo'q — bo'sh

    query = select(Category).where(
        Category.is_active == True,
    ).order_by(Category.order)

    branch_ids = select(Branch.id).where(Branch.restaurant_id == rid)
    if branch_id:
        # Faqat shu filial + restaurant-level
        query = query.where(
            (Category.branch_id == branch_id) |
            ((Category.restaurant_id == rid) & (Category.branch_id.is_(None)))
        )
    else:
        # Restaurant-level + barcha filial kategoriyalari
        query = query.where(
            (Category.restaurant_id == rid) | Category.branch_id.in_(branch_ids)
        )
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/products", response_model=list[ProductOut])
async def get_all_products(
    branch_id: Optional[int] = None,
    restaurant_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Mijoz mahsulotlar — SaaS izolatsiya."""
    rid = await _resolve_restaurant_id(branch_id, restaurant_id, db)
    if not rid:
        return []

    query = select(Product).where(
        Product.is_active == True, Product.product_type != "catering",
    )
    branch_ids = select(Branch.id).where(Branch.restaurant_id == rid)
    if branch_id:
        query = query.where(
            (Product.branch_id == branch_id) |
            ((Product.restaurant_id == rid) & (Product.branch_id.is_(None)))
        )
    else:
        query = query.where(
            (Product.restaurant_id == rid) | Product.branch_id.in_(branch_ids)
        )
    result = await db.execute(query)
    products = result.scalars().all()
    return [p for p in products if is_product_available(p)]


@router.get("/categories/{category_id}/products", response_model=list[ProductOut])
async def get_products_by_category(
    category_id: int,
    branch_id: Optional[int] = None,
    restaurant_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Mijoz: kategoriya mahsulotlari — SaaS izolatsiya."""
    rid = await _resolve_restaurant_id(branch_id, restaurant_id, db)
    if not rid:
        return []

    # Kategoriya ham shu restoraniki ekanini tekshirish (IDOR)
    cat = (await db.execute(select(Category).where(Category.id == category_id))).scalar_one_or_none()
    if not cat:
        return []
    if cat.restaurant_id and cat.restaurant_id != rid:
        return []  # boshqa restoran kategoriyasi

    query = select(Product).where(
        Product.category_id == category_id,
        Product.is_active == True,
        Product.product_type != "catering",
    )
    branch_ids = select(Branch.id).where(Branch.restaurant_id == rid)
    if branch_id:
        query = query.where(
            (Product.branch_id == branch_id) |
            ((Product.restaurant_id == rid) & (Product.branch_id.is_(None)))
        )
    else:
        query = query.where(
            (Product.restaurant_id == rid) | Product.branch_id.in_(branch_ids)
        )
    result = await db.execute(query)
    products = result.scalars().all()
    return [p for p in products if is_product_available(p)]


@router.get("/products/{product_id}", response_model=ProductOut)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Mahsulot topilmadi")
    return product


@router.patch("/products/{product_id}/stop")
async def toggle_stop(
    product_id: int,
    is_stop: bool,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Stop-list ga qo'shish yoki olib tashlash (Admin uchun) — IDOR himoyasi."""
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Mahsulot topilmadi")
    # SaaS izolatsiya
    if restaurant_id and product.restaurant_id and product.restaurant_id != restaurant_id:
        raise HTTPException(403, "Bu mahsulot sizning restoraningizniki emas")

    product.is_stop = is_stop
    await db.commit()
    return {"success": True, "is_stop": is_stop}
