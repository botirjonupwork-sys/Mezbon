"""Admin login — Restaurants jadvaldan va .env super admin dan tekshiradi"""
import hashlib
from fastapi import APIRouter, HTTPException, Depends, Header, Request
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.config import settings
from api.database import get_db
from database.models import Restaurant

router = APIRouter(prefix="/auth", tags=["auth"])

# Login uchun qattiq rate limit — brute-force hujumidan himoya
_auth_limiter = Limiter(key_func=get_remote_address)


# ── Super Admin auth dependency ──────────────────────
async def require_super_admin(authorization: str = Header(...)):
    """Super admin tokenni tekshirish."""
    token = authorization.replace("Bearer ", "")
    if token != settings.SECRET_KEY:
        raise HTTPException(403, "Ruxsat yo'q")


def _create_token(payload: dict) -> str:
    """Oddiy token yaratish (hozircha static SECRET_KEY)."""
    return settings.SECRET_KEY


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    name: str
    is_super: bool = False
    restaurant_id: Optional[int] = None


@router.post("/login", response_model=LoginResponse)
@_auth_limiter.limit("5/minute")
async def login(request: Request, data: LoginRequest, db: AsyncSession = Depends(get_db)):
    # 1. .env dagi super admin (barcha restoranlarga kirish)
    if data.username == settings.ADMIN_USERNAME and data.password == settings.ADMIN_PASSWORD:
        return LoginResponse(
            token=settings.SECRET_KEY,
            name=data.username,
            is_super=True,
            restaurant_id=None,
        )

    # 2. Restaurants jadvalidagi adminlar
    hashed = hashlib.sha256(data.password.encode()).hexdigest()
    result = await db.execute(
        select(Restaurant).where(
            Restaurant.admin_username == data.username,
            Restaurant.admin_password_hash == hashed,
        )
    )
    restaurant = result.scalar_one_or_none()
    if restaurant:
        return LoginResponse(
            token=f"{settings.SECRET_KEY}:{restaurant.id}",
            name=restaurant.name,
            is_super=False,
            restaurant_id=restaurant.id,
        )

    raise HTTPException(401, "Login yoki parol noto'g'ri")


# ── Bot login (bot_token orqali restaurant aniqlash) ──
class BotLoginRequest(BaseModel):
    bot_token: str


@router.post("/bot-login")
@_auth_limiter.limit("10/minute")
async def bot_login(request: Request, data: BotLoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Restaurant).where(Restaurant.bot_token == data.bot_token)
    )
    restaurant = result.scalar_one_or_none()
    if not restaurant:
        raise HTTPException(404, "Bot token bilan restoran topilmadi")
    return {
        "token": f"{settings.SECRET_KEY}:{restaurant.id}",
        "restaurant_id": restaurant.id,
        "restaurant_name": restaurant.name,
    }


# ── Super Admin login ────────────────────────────────
class SuperLoginRequest(BaseModel):
    username: str
    password: str


class SuperLoginResponse(BaseModel):
    token: str
    name: str


@router.post("/super/login", response_model=SuperLoginResponse)
@_auth_limiter.limit("5/minute")
async def super_login(request: Request, data: SuperLoginRequest):
    if (
        data.username == settings.SUPER_ADMIN_USERNAME
        and data.password == settings.SUPER_ADMIN_PASSWORD
    ):
        return SuperLoginResponse(token=settings.SECRET_KEY, name="Super Admin")
    raise HTTPException(401, "Login yoki parol noto'g'ri")
