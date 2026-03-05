from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from api.database import get_db
from api.schemas import UserCreate, UserOut, AddressCreate, AddressOut
from database.models import User, Address

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/", response_model=UserOut)
async def create_or_get_user(data: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.telegram_id == data.telegram_id))
    user = result.scalar_one_or_none()

    if user:
        return user

    user = User(**data.model_dump())
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/{telegram_id}", response_model=UserOut)
async def get_user(telegram_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Foydalanuvchi topilmadi")
    return user


@router.get("/{telegram_id}/addresses", response_model=list[AddressOut])
async def get_addresses(telegram_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Foydalanuvchi topilmadi")

    result = await db.execute(select(Address).where(Address.user_id == user.id))
    return result.scalars().all()


@router.post("/{telegram_id}/addresses", response_model=AddressOut)
async def add_address(
    telegram_id: str,
    data: AddressCreate,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Foydalanuvchi topilmadi")

    address = Address(user_id=user.id, **data.model_dump())
    db.add(address)
    await db.commit()
    await db.refresh(address)
    return address
