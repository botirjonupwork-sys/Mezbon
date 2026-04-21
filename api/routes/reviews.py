from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from api.database import get_db
from api.schemas import ReviewCreate, ReviewOut
from database.models import Review, User, Branch

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("", response_model=ReviewOut)
async def create_review(
    telegram_id: str,
    data: ReviewCreate,
    branch_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    if not 1 <= data.rating <= 5:
        raise HTTPException(400, "Reyting 1 dan 5 gacha bo'lishi kerak")

    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Foydalanuvchi topilmadi")

    review = Review(user_id=user.id, branch_id=branch_id, **data.model_dump())
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return review


@router.get("")
async def get_reviews(
    branch_id: Optional[int] = None,
    restaurant_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Review).order_by(Review.created_at.desc())
    if branch_id:
        query = query.where(Review.branch_id == branch_id)
    elif restaurant_id:
        branch_ids = select(Branch.id).where(Branch.restaurant_id == restaurant_id)
        query = query.where(Review.branch_id.in_(branch_ids))
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
    restaurant_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(
        func.avg(Review.rating).label("average"),
        func.count(Review.id).label("total"),
    )
    if branch_id:
        query = query.where(Review.branch_id == branch_id)
    elif restaurant_id:
        branch_ids = select(Branch.id).where(Branch.restaurant_id == restaurant_id)
        query = query.where(Review.branch_id.in_(branch_ids))
    result = await db.execute(query)
    row = result.one()
    return {
        "average_rating": round(float(row.average or 0), 1),
        "total_reviews": row.total,
    }
