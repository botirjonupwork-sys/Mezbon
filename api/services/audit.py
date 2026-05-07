"""Restaurant-level xavfsizlik audit log servisi.

`SecurityLog` jadvaliga yozuvlarni kiritadi. `SuperAdminAction` super-admin
amallari uchun edi — bu xizmat oddiy admin va foydalanuvchi xavfsizlik
hodisalari uchun (login, register, parol o'zgartirish, INN almashtirish).

Foydalanish:
    from api.services.audit import log_security

    await log_security(
        db,
        action="register",
        restaurant_id=rest.id,
        actor_username="admin",
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={"inn": "***", "name": rest.name},
        success=True,
    )

Yozuvlar **o'chirilmaydi**. Aktiv hujum yoki manipulyatsiya bo'lsa,
analyst log'larni ketma-ket o'qib aniqlaydi.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import SecurityLog


# Recognized action names — yangi action qo'shganda bu setni yangilash tavsiya etiladi
KNOWN_ACTIONS = {
    "register",
    "register.failed",
    "login.success",
    "login.failed",
    "logout",
    "password.change",
    "token.refresh",
    "inn.change",
    "inn.verify",
    "plan.change",
    "subscription.change",
    "rate_limit.hit",
    "auth.idor_attempt",
    "permission.denied",
}


async def log_security(
    db: AsyncSession,
    *,
    action: str,
    restaurant_id: Optional[int] = None,
    actor_username: Optional[str] = None,
    actor_user_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    success: bool = True,
) -> SecurityLog:
    """Bitta xavfsizlik yozuvini saqlaydi.

    Asla `raise` qilmaydi — log yozish xato bo'lsa, asosiy oqim davom etadi.
    """
    try:
        # `details` ichida sezgir ma'lumotlarni to'liq saqlamaslik
        # (parol, secret, token) — chaqiruvchi mas'ul
        details_json = None
        if details:
            try:
                details_json = json.dumps(details, ensure_ascii=False, default=str)
            except Exception:
                details_json = str(details)[:1000]

        entry = SecurityLog(
            action=action,
            restaurant_id=restaurant_id,
            actor_username=actor_username,
            actor_user_id=actor_user_id,
            ip_address=ip_address,
            user_agent=(user_agent or "")[:500],   # ba'zi browserlar juda uzun
            details=details_json,
            success=success,
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        return entry
    except Exception:
        # Log yozish o'zi xato bo'lsa, asosiy oqimni buzmaymiz
        try:
            await db.rollback()
        except Exception:
            pass
        return None  # type: ignore


def client_ip(request: Request) -> Optional[str]:
    """Reverse-proxy bilan ishlay oladigan client IP.

    nginx odatda `X-Forwarded-For` qo'yadi. Bir nechta proksi bo'lsa, birinchi IP
    haqiqiy mijoz IP'si.
    """
    fwd = (request.headers.get("x-forwarded-for") or "").strip()
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None
