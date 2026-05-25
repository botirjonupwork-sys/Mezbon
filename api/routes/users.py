from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from api.database import get_db
from api.schemas import UserCreate, UserOut, AddressCreate, AddressOut
from database.models import User, Address, Branch, Restaurant
from api.services.security import is_valid_bot_secret


async def _require_bot_secret(x_bot_secret: Optional[str] = Header(None, alias="X-Bot-Secret")):
    """Bot'dan kelgan so'rovlarni tekshirish (telegram_id spoofing'dan himoya)."""
    if not is_valid_bot_secret(x_bot_secret or ""):
        raise HTTPException(403, "Ruxsat berilmadi")
    return True


router = APIRouter(prefix="/users", tags=["users"])

# Public router for bot/customer-facing endpoints
public_router = APIRouter(tags=["public"])


class SelectBranchRequest(BaseModel):
    branch_id: Optional[int] = None


@public_router.get("/restaurants/{restaurant_id}/info")
async def restaurant_public_info(restaurant_id: int, db: AsyncSession = Depends(get_db)):
    """Restoran haqida ommaviy ma'lumot — bot va mijoz uchun (auth shart emas)."""
    result = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
    rest = result.scalar_one_or_none()
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")
    return {
        "id": rest.id,
        "name": rest.name,
        "logo_url": rest.logo_url,
        "address": rest.address,
        "phone": rest.phone,
        "work_hours_from": rest.work_hours_from,
        "work_hours_until": rest.work_hours_until,
        "min_order": rest.min_order,
        "restaurant_lat": rest.restaurant_lat,
        "restaurant_lon": rest.restaurant_lon,
    }


@router.post("/", response_model=UserOut)
async def create_or_get_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    _bot: bool = Depends(_require_bot_secret),
):
    result = await db.execute(select(User).where(User.telegram_id == data.telegram_id))
    user = result.scalar_one_or_none()

    if user:
        return user

    user = User(**data.model_dump())
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


# ── AI Call Operator orqali kelgan foydalanuvchini yaratish ─────────────
# Identifikatsiya qoidasi: telegram_id = "phone:+9989..." formatida saqlanadi.
# Bu Telegram orqali kelgan oddiy mijozlardan farq qilish va ovozli kanaldan
# kelgan foydalanuvchilarni alohida tanib olish uchun.
async def get_or_create_phone_user(
    db: AsyncSession,
    phone: str,
    full_name: Optional[str] = None,
) -> User:
    """Ovozli (telefon orqali) kelgan mijozni topadi yoki yaratadi.

    Telefon raqami `+998XXXXXXXXX` formatida bo'lishi kutiladi.
    Telegram_id sifatida `phone:+998...` saqlanadi — boshqa kanallar bilan to'qnashmaydi.
    """
    if not phone:
        raise ValueError("phone bo'sh bo'lmasligi kerak")
    phone = phone.strip()
    if not phone.startswith("+"):
        # Oddiy formatga keltiramiz (998... → +998...)
        digits = "".join(ch for ch in phone if ch.isdigit())
        phone = "+" + digits if digits else phone
    tg_id = f"phone:{phone}"
    result = await db.execute(select(User).where(User.telegram_id == tg_id))
    user = result.scalar_one_or_none()
    if user:
        return user
    user = User(
        telegram_id=tg_id,
        full_name=(full_name or "AI mijoz").strip(),
        phone=phone,
        language="uz",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/{telegram_id}", response_model=UserOut)
async def get_user(
    telegram_id: str,
    db: AsyncSession = Depends(get_db),
    _bot: bool = Depends(_require_bot_secret),
):
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Foydalanuvchi topilmadi")
    return user


@router.post("/{telegram_id}/branch", response_model=UserOut)
async def set_user_branch(
    telegram_id: str,
    data: SelectBranchRequest,
    db: AsyncSession = Depends(get_db),
    _bot: bool = Depends(_require_bot_secret),
):
    """Foydalanuvchi tanlagan filialni saqlash."""
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Foydalanuvchi topilmadi")

    if data.branch_id is not None:
        b_result = await db.execute(select(Branch).where(Branch.id == data.branch_id))
        if not b_result.scalar_one_or_none():
            raise HTTPException(404, "Filial topilmadi")

    user.selected_branch_id = data.branch_id
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/{telegram_id}/addresses", response_model=list[AddressOut])
async def get_addresses(
    telegram_id: str,
    db: AsyncSession = Depends(get_db),
    _bot: bool = Depends(_require_bot_secret),
):
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
    db: AsyncSession = Depends(get_db),
    _bot: bool = Depends(_require_bot_secret),
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
