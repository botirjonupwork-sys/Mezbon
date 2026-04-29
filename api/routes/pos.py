"""POS / Printer endpoints — sozlamalarni test qilish va terminal bridge.

Endpointlar:
    POST /admin/pos/test-print  — joriy konfiguratsiya bilan "Salom Dunyo" chekini yuborish
    GET  /admin/pos/status      — restoranga ulangan terminal'lar soni
    PUT  /admin/pos/config      — POS turi va konfiguratsiyani yangilash
    WS   /pos/bridge/{rid}      — Android/agent shu yerga ulanadi va print signal'larni qabul qiladi
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth_deps import require_restaurant_admin
from api.config import settings
from api.database import get_db
from api.services.pos_adapter import POS_TYPES, adapter as pos_adapter
from database.models import Restaurant


router = APIRouter(tags=["pos"])


class POSConfigUpdate(BaseModel):
    pos_system_type: Optional[str] = None
    pos_config: Optional[dict[str, Any]] = None


@router.get("/admin/pos/config")
async def get_pos_config(
    restaurant_id: int = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    if not restaurant_id:
        raise HTTPException(400, "restaurant_id kerak")
    res = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
    rest = res.scalar_one_or_none()
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")
    return {
        "pos_system_type": rest.pos_system_type or "NONE",
        "pos_config": rest.pos_config or {},
        "connected_terminals": pos_adapter.bridge.client_count(rest.id),
    }


@router.put("/admin/pos/config")
async def update_pos_config(
    body: POSConfigUpdate,
    restaurant_id: int = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    if not restaurant_id:
        raise HTTPException(400, "restaurant_id kerak")
    res = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
    rest = res.scalar_one_or_none()
    if not rest:
        raise HTTPException(404, "Restoran topilmadi")

    if body.pos_system_type is not None:
        if body.pos_system_type not in POS_TYPES:
            raise HTTPException(
                400, f"pos_system_type faqat: {', '.join(POS_TYPES)}",
            )
        rest.pos_system_type = body.pos_system_type
    if body.pos_config is not None:
        # Sodda merge — yo'q kalitlarni saqlab qoldiramiz
        cfg = dict(rest.pos_config or {})
        cfg.update(body.pos_config)
        rest.pos_config = cfg
    await db.commit()
    return {
        "ok": True,
        "pos_system_type": rest.pos_system_type or "NONE",
        "pos_config": rest.pos_config or {},
    }


@router.post("/admin/pos/test-print")
async def test_print(
    restaurant_id: int = Depends(require_restaurant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Joriy POS sozlamalari bilan "Salom Dunyo" testini yuboradi.

    Drayver muvaffaqiyatsiz bo'lsa ham 200 qaytaradi — natija `result` ichida.
    """
    if not restaurant_id:
        raise HTTPException(400, "restaurant_id kerak")
    result = await pos_adapter.test_print(db, restaurant_id)
    return {"ok": bool(result.get("ok")), "result": result}


# ── WebSocket bridge ─────────────────────────────────────────────────────
# Android terminal yoki kassa-agent bu endpoint orqali ulanadi va print
# signal'larni real-time qabul qiladi.
#
# Foydalanish (agent tomonida):
#   ws://api.example.com/pos/bridge/1?token=<RESTAURANT_TOKEN>
#
# Token format: <SECRET_KEY>:<restaurant_id>  (oddiy admin tokeni — oddiy bridge auth)


@router.websocket("/pos/bridge/{restaurant_id}")
async def pos_bridge(websocket: WebSocket, restaurant_id: int, token: str = ""):
    """Restoranga tegishli terminal'lar uchun WebSocket bridge."""
    # Tokenni tekshirish — restoran admin tokeni yoki POS-specific token
    expected_prefix = settings.SECRET_KEY
    valid = False
    if token == expected_prefix:
        valid = True
    elif token.startswith(f"{expected_prefix}:"):
        try:
            tk_rid = int(token.split(":", 1)[1])
            valid = (tk_rid == restaurant_id)
        except ValueError:
            pass
    if not valid:
        await websocket.close(code=1008)  # Policy violation
        return

    await websocket.accept()
    await pos_adapter.bridge.connect(restaurant_id, websocket)
    try:
        # Heartbeat: client'dan keladigan har qanday xabarni qabul qilamiz (ping/pong yoki agent javobi)
        while True:
            msg = await websocket.receive_text()
            # Agent javobini logga yozish kerak bo'lsa shu yerda. Hozircha shunchaki echo qilamiz.
            if msg == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        await pos_adapter.bridge.disconnect(restaurant_id, websocket)
