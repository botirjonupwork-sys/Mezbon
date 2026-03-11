from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from api.database import get_db
from api.schemas import CategoryOut, ProductOut
from database.models import Category, Product

router = APIRouter(prefix="/menu", tags=["menu"])

UZ_TZ = ZoneInfo("Asia/Tashkent")


def is_product_available(product: Product) -> bool:
    """Mahsulot hozir mavjudligini tekshirish (vaqt limiti)"""
    if product.is_stop:
        return False
    if not product.has_time_limit:
        return True

    now = datetime.now(UZ_TZ).strftime("%H:%M")
    if product.available_from and product.available_until:
        return product.available_from <= now <= product.available_until
    return True


@router.get("/categories", response_model=list[CategoryOut])
async def get_categories(
    branch_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Category).where(Category.is_active == True).order_by(Category.order)
    if branch_id:
        query = query.where(Category.branch_id == branch_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/products", response_model=list[ProductOut])
async def get_all_products(
    branch_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Product).where(Product.is_active == True)
    if branch_id:
        query = query.where(Product.branch_id == branch_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/categories/{category_id}/products", response_model=list[ProductOut])
async def get_products_by_category(
    category_id: int,
    branch_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Product).where(
        Product.category_id == category_id,
        Product.is_active == True,
    )
    if branch_id:
        query = query.where(Product.branch_id == branch_id)
    result = await db.execute(query)
    return result.scalars().all()


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
    db: AsyncSession = Depends(get_db),
):
    """Stop-list ga qo'shish yoki olib tashlash (Admin uchun)"""
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Mahsulot topilmadi")

    product.is_stop = is_stop
    await db.commit()
    return {"success": True, "is_stop": is_stop}
