"""Uzum Bank Merchant API webhook endpoint.

Endpoint: POST /payments/uzum/webhook

Uzum xulq-atvori (developer.uzumbank.uz/en/merchant/):
  - HTTP POST JSON
  - HTTP Basic Auth (Restaurant.uzum_webhook_user / uzum_webhook_pass)
  - 5 ta action: check, create, confirm, reverse, status
  - Action body'da `action` field, yoki URL path orqali aniqlanishi mumkin —
    biz bu yerda body field'iga tayanamiz (eng keng tarqalgan).
  - Javob: {"status": "OK"|"ERROR", "errorCode": 0, "errorMessage": "..."}
"""
from __future__ import annotations

import base64
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from database.models import Order, Restaurant
from api.services.order_webhook import handle_uzum_order_webhook


router = APIRouter(prefix="/payments/uzum", tags=["payments-uzum"])
log = logging.getLogger(__name__)


def _check_uzum_basic_auth(authorization: Optional[str], user: str, password: str) -> bool:
    """Uzum HTTP Basic Auth tekshiruvi."""
    if not authorization or not authorization.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(authorization[6:]).decode()
        login, pwd = decoded.split(":", 1)
    except Exception:
        return False
    import secrets
    return secrets.compare_digest(login, user) and secrets.compare_digest(pwd, password)


@router.post("/webhook")
async def uzum_webhook(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Uzum Bank Merchant webhook handler."""
    try:
        payload = await request.json()
    except Exception:
        return {"status": "ERROR", "errorCode": 1, "errorMessage": "Invalid JSON"}

    action = (payload.get("action") or "").lower()
    if not action:
        return {"status": "ERROR", "errorCode": 1, "errorMessage": "action required"}

    # Order'ni topib, restoranni aniqlaymiz (auth tekshiruvi uchun)
    order_id_raw = payload.get("order_id") or payload.get("orderId")
    if not order_id_raw:
        return {"status": "ERROR", "errorCode": 1, "errorMessage": "order_id required"}
    try:
        order_id = int(order_id_raw)
    except (TypeError, ValueError):
        return {"status": "ERROR", "errorCode": 1, "errorMessage": "order_id invalid"}

    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if not order:
        return {"status": "ERROR", "errorCode": 2, "errorMessage": "Order not found"}

    rest = (await db.execute(
        select(Restaurant).where(Restaurant.id == order.restaurant_id)
    )).scalar_one_or_none()
    if not rest or not rest.uzum_enabled:
        return {"status": "ERROR", "errorCode": 6, "errorMessage": "Uzum not configured"}

    # Basic auth tekshiruvi — MAJBURIY.
    # Agar restoran Uzum'ni yoqgan bo'lsa, lekin webhook login/parol o'rnatmagan
    # bo'lsa, webhook'ni autentifikatsiyasiz qabul qilish mumkin emas (aks holda
    # istalgan kishi buyurtmani "paid" qila oladi).
    if not rest.uzum_webhook_user or not rest.uzum_webhook_pass:
        log.error("Uzum webhook reddi: restaurant_id=%s webhook credentials o'rnatilmagan", rest.id)
        return {"status": "ERROR", "errorCode": 7, "errorMessage": "Auth not configured"}
    if not _check_uzum_basic_auth(authorization, rest.uzum_webhook_user, rest.uzum_webhook_pass):
        from api.services.detectors import webhook_auth_failed
        webhook_auth_failed("uzum", request.client.host if request.client else None)
        return {"status": "ERROR", "errorCode": 7, "errorMessage": "Auth failed"}

    return await handle_uzum_order_webhook(action, payload, db)
