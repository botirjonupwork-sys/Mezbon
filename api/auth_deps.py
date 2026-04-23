"""Authentication dependencies — Admin va Super Admin uchun token tekshirish.

Token formatlari:
- Super Admin: `<SECRET_KEY>` (faqat)
- Restaurant Admin: `<SECRET_KEY>:<restaurant_id>`
"""
from typing import Optional
from fastapi import Depends, HTTPException, Header, Query
from dataclasses import dataclass

from api.config import settings


@dataclass
class AuthContext:
    """Auth natijasi — token orqali aniqlangan kontekst."""
    is_super: bool = False
    restaurant_id: Optional[int] = None  # Super admin uchun None


def _parse_token(raw: str) -> Optional[AuthContext]:
    """Token'ni parse qilish. None qaytarilsa — noto'g'ri token."""
    if not raw:
        return None
    token = raw.replace("Bearer ", "").strip()
    if not token:
        return None
    # Super admin: SECRET_KEY
    if token == settings.SECRET_KEY:
        return AuthContext(is_super=True, restaurant_id=None)
    # Restaurant admin: SECRET_KEY:restaurant_id
    if ":" in token:
        secret, rid = token.rsplit(":", 1)
        if secret == settings.SECRET_KEY:
            try:
                return AuthContext(is_super=False, restaurant_id=int(rid))
            except ValueError:
                return None
    return None


async def require_auth(authorization: str = Header(..., alias="Authorization")) -> AuthContext:
    """Har qanday autentifikatsiya qilingan foydalanuvchini tekshiradi.

    Rotate qilgan keyin: invalidate all old tokens. Hozir bu static.
    """
    ctx = _parse_token(authorization)
    if not ctx:
        raise HTTPException(401, "Ruxsat berilmadi — noto'g'ri yoki yo'q token")
    return ctx


async def require_restaurant_admin(
    authorization: str = Header(..., alias="Authorization"),
    restaurant_id: Optional[int] = Query(None),
) -> int:
    """Restaurant admin (yoki super admin) tokenni tekshiradi va restaurant_id qaytaradi.

    Muhim: restaurant_id query param bergan bo'lsa ham, token'dagi restaurant_id asosiy.
    Super admin bo'lsa — query param hurmat qilinadi (ixtiyoriy restaurantlarga kira oladi).
    Restaurant admin bo'lsa — faqat OZ restaurant_id'siga ruxsat.
    """
    ctx = _parse_token(authorization)
    if not ctx:
        raise HTTPException(401, "Ruxsat berilmadi")

    # Super admin har qanday restaurantga kira oladi
    if ctx.is_super:
        if restaurant_id is None:
            # Super admin restaurant tanlamagan bo'lsa — barchasi (None) qaytariladi
            return None  # Endpoint o'zi handle qiladi
        return restaurant_id

    # Restaurant admin — faqat o'ziniki
    if restaurant_id is not None and restaurant_id != ctx.restaurant_id:
        raise HTTPException(403, "Siz boshqa restoran ma'lumotlariga kira olmaysiz")
    return ctx.restaurant_id


async def require_super_admin(
    authorization: str = Header(..., alias="Authorization"),
) -> AuthContext:
    """Faqat super admin tokenini tekshiradi."""
    ctx = _parse_token(authorization)
    if not ctx or not ctx.is_super:
        raise HTTPException(403, "Faqat super admin uchun")
    return ctx
