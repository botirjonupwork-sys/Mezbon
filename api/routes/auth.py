"""Admin login — Restaurants jadvaldan va .env super admin dan tekshiradi"""
import base64
import hashlib
import hmac
import json
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Header, Request, Response
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


def _set_auth_cookie(response: Response, token: str, max_age: int = 3600) -> None:
    """JWT'ni HttpOnly + Secure + SameSite=Strict cookie sifatida o'rnatadi.

    SameSite=Strict bilan boshqa domendan kelgan so'rovlarga cookie yuborilmaydi
    (CSRF himoyasi). Backward compat: token body'da ham qaytariladi.
    """
    response.set_cookie(
        key="admin_token",
        value=token,
        max_age=max_age,
        httponly=True,
        secure=True,   # HTTPS faqat
        samesite="strict",  # CSRF himoyasi
        path="/",
    )


@router.post("/login", response_model=LoginResponse)
# noqa — login endpoint o'zgartirilgan, lockout qo'shildi
@_auth_limiter.limit("5/minute")
async def login(request: Request, response: Response, data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Restaurant admin yoki .env super-admin login.

    Per-username lockout: 5 ketma-ket xato → 15 daqiqa qulflanadi.

    JWT access token chiqaradi (1 soat TTL). Eski SHA-256 hash'lar bcrypt'ga
    avtomatik upgrade qilinadi (foydalanuvchi parolini bilgan paytda).
    """
    from api.services.auth_service import make_access_token
    from api.services.security import hash_password, needs_rehash, verify_password
    from api.services.login_lockout import login_lockout
    from api.services.audit import log_security

    # IP va User-Agent (audit log uchun)
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")[:500]

    # Lockout tekshiruvi — bruteforce'ga qarshi
    locked, secs = login_lockout.is_locked(data.username)
    if locked:
        await log_security(
            db, action="login.locked", actor_username=data.username,
            ip_address=client_ip, user_agent=user_agent, success=False,
            details={"locked_for_seconds": secs},
        )
        mins = (secs + 59) // 60
        raise HTTPException(
            429,
            f"Juda ko'p urinish. {mins} daqiqadan keyin qayta urinib ko'ring.",
        )

    # 1. .env dagi super admin
    if data.username == settings.ADMIN_USERNAME and data.password == settings.ADMIN_PASSWORD:
        login_lockout.record_success(data.username)
        await log_security(
            db, action="login.success", actor_username=data.username,
            ip_address=client_ip, user_agent=user_agent, success=True,
            details={"is_super": True},
        )
        token = make_access_token(restaurant_id=None, is_super=True, username=data.username)
        _set_auth_cookie(response, token)
        return LoginResponse(
            token=token,
            name=data.username,
            is_super=True,
            restaurant_id=None,
        )

    # 2. Restaurants jadvalidagi adminlar — username bo'yicha topib, parolni verify qilamiz
    result = await db.execute(
        select(Restaurant).where(Restaurant.admin_username == data.username)
    )
    restaurant = result.scalar_one_or_none()
    if not restaurant or not restaurant.admin_password_hash:
        login_lockout.record_failure(data.username)
        await log_security(
            db, action="login.failed", actor_username=data.username,
            ip_address=client_ip, user_agent=user_agent, success=False,
            details={"reason": "user_not_found"},
        )
        raise HTTPException(401, "Login yoki parol noto'g'ri")

    if not verify_password(data.password, restaurant.admin_password_hash):
        failures, lock_secs = login_lockout.record_failure(data.username)
        await log_security(
            db, action="login.failed", restaurant_id=restaurant.id,
            actor_username=data.username, ip_address=client_ip,
            user_agent=user_agent, success=False,
            details={"reason": "wrong_password", "failures": failures},
        )
        if lock_secs:
            raise HTTPException(
                429,
                f"5 ta xato urinish — login {lock_secs // 60} daqiqaga qulflandi.",
            )
        raise HTTPException(401, "Login yoki parol noto'g'ri")

    # Restoran holatini tekshirish (Faza 11: bloklan rentaurant login qila olmaydi)
    rest_status = (restaurant.status or "active").lower()
    if rest_status == "blocked":
        raise HTTPException(403, "Restoraningiz bloklangan. Platforma administratoriga murojaat qiling.")
    if rest_status == "suspended":
        raise HTTPException(402, "Tarifingiz to'lov muddati tugagan. Administratorga murojaat qiling.")

    # Muvaffaqiyatli login — lockout counter tozalanadi + audit log
    login_lockout.record_success(data.username)
    await log_security(
        db, action="login.success", restaurant_id=restaurant.id,
        actor_username=data.username, ip_address=client_ip,
        user_agent=user_agent, success=True,
    )

    # Backward compat: SHA-256 hash'ni bcrypt'ga upgrade
    if needs_rehash(restaurant.admin_password_hash):
        try:
            restaurant.admin_password_hash = hash_password(data.password)
            await db.commit()
        except Exception:
            await db.rollback()  # upgrade'siz davom etamiz

    token = make_access_token(
        restaurant_id=restaurant.id, is_super=False, username=data.username,
    )
    _set_auth_cookie(response, token)
    return LoginResponse(
        token=token,
        name=restaurant.name,
        is_super=False,
        restaurant_id=restaurant.id,
    )


@router.post("/logout")
async def logout(response: Response):
    """Cookie'ni tozalash. Frontend ham local state'ni o'zi tozalashi kerak."""
    response.delete_cookie(key="admin_token", path="/")
    return {"ok": True}


@router.get("/me")
async def me(request: Request, db: AsyncSession = Depends(get_db)):
    """Joriy auth holatini qaytaradi (sahifa refresh paytida cookie tekshirish uchun).

    Cookie yoki Bearer token orqali ishlaydi. Token yo'q yoki yaroqsiz bo'lsa 401.
    """
    from api.auth_deps import _parse_token, _get_token_from_request
    token = _get_token_from_request(
        request.headers.get("authorization"),
        request,
    )
    ctx = _parse_token(token)
    if not ctx:
        raise HTTPException(401, "Sessiya yaroqsiz")

    # Super admin
    if ctx.is_super:
        return {
            "name": ctx.username or "super",
            "is_super": True,
            "restaurant_id": None,
        }

    # Restaurant admin — joriy holatni qaytaramiz
    rest = (await db.execute(
        select(Restaurant).where(Restaurant.id == ctx.restaurant_id)
    )).scalar_one_or_none()
    if not rest:
        raise HTTPException(401, "Restoran topilmadi")

    return {
        "name": rest.name,
        "is_super": False,
        "restaurant_id": rest.id,
    }


@router.post("/refresh")
@_auth_limiter.limit("10/minute")
async def refresh_token(request: Request, refresh_token: str = ""):
    """Refresh token orqali yangi access token olish.

    Body: `{"refresh_token": "..."}` yoki query/header.
    """
    from api.services.auth_service import refresh_access_token
    if not refresh_token:
        # Body dan ham qabul qilamiz
        try:
            body = await request.json()
            refresh_token = body.get("refresh_token", "")
        except Exception:
            pass
    new = refresh_access_token(refresh_token)
    if not new:
        raise HTTPException(401, "Refresh token yaroqsiz yoki muddati o'tgan")
    return new


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
