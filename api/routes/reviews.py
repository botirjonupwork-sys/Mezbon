from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from api.database import get_db
from api.auth_deps import require_restaurant_admin
from api.schemas import ReviewCreate, ReviewOut
from database.models import Review, User, Branch

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("", response_model=ReviewOut)
async def create_review(
    telegram_id: str,
    data: ReviewCreate,
    branch_id: Optional[int] = None,
    restaurant_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    if not 1 <= data.rating <= 5:
        raise HTTPException(400, "Reyting 1 dan 5 gacha bo'lishi kerak")

    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Foydalanuvchi topilmadi")

    # SaaS izolatsiya: restaurant_id branch'dan yoki query'dan
    if branch_id and not restaurant_id:
        br = (await db.execute(select(Branch).where(Branch.id == branch_id))).scalar_one_or_none()
        if br:
            restaurant_id = br.restaurant_id

    if not restaurant_id:
        raise HTTPException(400, "restaurant_id yoki branch_id majburiy")

    review = Review(
        user_id=user.id,
        branch_id=branch_id,
        restaurant_id=restaurant_id,
        **data.model_dump(),
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return review


@router.get("")
async def get_reviews(
    branch_id: Optional[int] = None,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(Review).order_by(Review.created_at.desc())
    # SaaS izolatsiya
    if restaurant_id is None:
        return []
    branch_ids_subq = select(Branch.id).where(Branch.restaurant_id == restaurant_id)
    query = query.where(Review.branch_id.in_(branch_ids_subq))
    if branch_id:
        br = (await db.execute(select(Branch).where(Branch.id == branch_id))).scalar_one_or_none()
        if not br or br.restaurant_id != restaurant_id:
            return []
        query = query.where(Review.branch_id == branch_id)
    result = await db.execute(query)
    reviews = result.scalars().all()

    output = []
    for r in reviews:
        user_res = await db.execute(select(User).where(User.id == r.user_id))
        user = user_res.scalar_one_or_none()
        output.append({
            "id": r.id,
            "branch_id": r.branch_id,
            "rating": r.rating,
            "comment": r.comment,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "user": {"full_name": user.full_name, "phone": user.phone} if user else None,
        })
    return output


@router.get("/stats")
async def get_stats(
    branch_id: Optional[int] = None,
    restaurant_id: Optional[int] = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(
        func.avg(Review.rating).label("average"),
        func.count(Review.id).label("total"),
    )
    if restaurant_id is None:
        return {"average_rating": 0, "total_reviews": 0}
    branch_ids_subq = select(Branch.id).where(Branch.restaurant_id == restaurant_id)
    query = query.where(Review.branch_id.in_(branch_ids_subq))
    if branch_id:
        br = (await db.execute(select(Branch).where(Branch.id == branch_id))).scalar_one_or_none()
        if not br or br.restaurant_id != restaurant_id:
            return {"average_rating": 0, "total_reviews": 0}
        query = query.where(Review.branch_id == branch_id)
    result = await db.execute(query)
    row = result.one()
    return {
        "average_rating": round(float(row.average or 0), 1),
        "total_reviews": row.total,
    }
