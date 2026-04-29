"""Admin login — Restaurants jadvaldan va .env super admin dan tekshiradi"""
import base64
import hashlib
import hmac
import json
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Header, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.config import settings
from api.database import get_db
from database.models import Restaurant


# ── Qisqa muddatli super-admin tokeni (HMAC-SHA256 + exp) ─────────────
# JWT-like, lekin pyjwt'siz. Format: <payload_b64>.<sig_b64>
# Payload: {"u": username, "exp": unix_seconds, "is_super": True}
SUPER_TOKEN_TTL_SECONDS = 60 * 60   # 1 soat


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padded = s + "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(padded.encode())


def make_super_token(username: str, ttl_seconds: int = SUPER_TOKEN_TTL_SECONDS) -> str:
    payload = {"u": username, "exp": int(time.time()) + ttl_seconds, "is_super": True}
    body = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(
        settings.SECRET_KEY.encode(), body.encode(), hashlib.sha256
    ).digest()
    return f"{body}.{_b64url_encode(sig)}"


def verify_super_token(token: str) -> Optional[dict]:
    """Qaytaradi: payload dict yoki None (yaroqsiz/eskirgan)."""
    if not token or "." not in token:
        return None
    try:
        body, sig = token.rsplit(".", 1)
        expected = hmac.new(
            settings.SECRET_KEY.encode(), body.encode(), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(_b64url_encode(expected), sig):
            return None
        payload = json.loads(_b64url_decode(body))
    except Exception:
        return None
    if not payload.get("is_super"):
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload

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
            token=make_super_token(data.username),
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
        return SuperLoginResponse(
            token=make_super_token(data.username), name="Super Admin",
        )
    raise HTTPException(401, "Login yoki parol noto'g'ri")
