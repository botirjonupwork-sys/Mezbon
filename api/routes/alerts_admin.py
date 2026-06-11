"""Super-admin: Xavfsizlik AI bildirishnoma sozlamalari.

Endpointlar (barchasi require_superuser):
  GET  /super-admin/alerts/config   — kanal + qoidalar + sozlama (sirlar maskalangan)
  PUT  /super-admin/alerts/config   — yangilash
  POST /super-admin/alerts/test     — sinov xabari (rate-limit)
  GET  /super-admin/alerts/history  — bildirishnoma tarixi (sahifalangan)
"""
from __future__ import annotations

import json
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.routes.super_admin import require_superuser
from api.services import platform
from api.services.alert_router import invalidate_config_cache, send_test
from api.services.channels.telegram import TelegramChannel
from api.services.field_encryption import decrypt_field, encrypt_field
from database.models import AlertChannel, AlertHistory, AlertRule

router = APIRouter(prefix="/super-admin/alerts", tags=["super-admin-alerts"])

_MASK = "••••"
_VALID_SEVERITY = {"info", "warning", "critical"}


def _mask_token(token: str) -> str:
    if not token:
        return ""
    return _MASK + token[-4:] if len(token) > 4 else _MASK


async def _get_telegram_channel(db: AsyncSession) -> Optional[AlertChannel]:
    return (await db.execute(
        select(AlertChannel).where(AlertChannel.type == "telegram").order_by(AlertChannel.id)
    )).scalars().first()


def _decode_cfg(row: Optional[AlertChannel]) -> dict:
    if not row or not row.config_enc:
        return {}
    try:
        return json.loads(decrypt_field(row.config_enc) or "{}")
    except Exception:
        return {}


# ── GET config ──────────────────────────────────────────

@router.get("/config")
async def get_config(actor: dict = Depends(require_superuser), db: AsyncSession = Depends(get_db)):
    ch = await _get_telegram_channel(db)
    cfg = _decode_cfg(ch)
    token = cfg.get("bot_token", "")

    rules = (await db.execute(select(AlertRule).order_by(AlertRule.id))).scalars().all()
    return {
        "telegram": {
            "enabled": bool(ch.enabled) if ch else False,
            "bot_token_masked": _mask_token(token),
            "bot_token_set": bool(token),
            "chat_ids": cfg.get("chat_ids") or [],
        },
        "rules": [
            {"id": r.id, "event_category": r.event_category,
             "min_severity": r.min_severity, "enabled": bool(r.enabled)}
            for r in rules
        ],
        "security_ai_enabled": (True if platform.get("security_ai_enabled") is None
                                else bool(platform.get("security_ai_enabled"))),
        "quiet_hours_start": platform.get("quiet_hours_start") or "",
        "quiet_hours_end": platform.get("quiet_hours_end") or "",
    }


# ── PUT config ──────────────────────────────────────────

class TelegramIn(BaseModel):
    enabled: bool = True
    bot_token: str = ""          # bo'sh yoki maskalangan kelsa — eski qiymat saqlanadi
    chat_ids: list[str] = []


class RuleIn(BaseModel):
    event_category: str = "*"
    min_severity: str = "warning"
    enabled: bool = True


class ConfigIn(BaseModel):
    telegram: Optional[TelegramIn] = None
    rules: Optional[list[RuleIn]] = None
    security_ai_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None


@router.put("/config")
async def put_config(body: ConfigIn, actor: dict = Depends(require_superuser),
                     db: AsyncSession = Depends(get_db)):
    # ── Telegram kanal ──
    if body.telegram is not None:
        ch = await _get_telegram_channel(db)
        cfg = _decode_cfg(ch)
        incoming = (body.telegram.bot_token or "").strip()
        # Maskalangan yoki bo'sh token — eski qiymatni saqlaymiz
        if incoming and not incoming.startswith(_MASK):
            cfg["bot_token"] = incoming
        cfg["chat_ids"] = [str(c).strip() for c in body.telegram.chat_ids if str(c).strip()]
        enc = encrypt_field(json.dumps(cfg, ensure_ascii=False))
        if ch:
            ch.enabled = body.telegram.enabled
            ch.config_enc = enc
        else:
            db.add(AlertChannel(type="telegram", enabled=body.telegram.enabled, config_enc=enc))

    # ── Qoidalar (replace-all) ──
    if body.rules is not None:
        await db.execute(delete(AlertRule))
        for r in body.rules:
            sev = r.min_severity if r.min_severity in _VALID_SEVERITY else "warning"
            db.add(AlertRule(event_category=(r.event_category or "*").strip(),
                             min_severity=sev, enabled=r.enabled))

    await db.commit()

    # ── Platform sozlamalari ──
    updates = {}
    if body.security_ai_enabled is not None:
        updates["security_ai_enabled"] = bool(body.security_ai_enabled)
    if body.quiet_hours_start is not None:
        updates["quiet_hours_start"] = body.quiet_hours_start.strip()
    if body.quiet_hours_end is not None:
        updates["quiet_hours_end"] = body.quiet_hours_end.strip()
    if updates:
        platform.set_many(updates)

    invalidate_config_cache()
    return {"ok": True}


# ── POST test ───────────────────────────────────────────

_last_test: dict[str, float] = {}


@router.post("/test")
async def test_alert(actor: dict = Depends(require_superuser), db: AsyncSession = Depends(get_db)):
    # Oddiy rate-limit: 10 soniyada bir marta (spam emas)
    now = time.time()
    user = actor.get("u", "super")
    if now - _last_test.get(user, 0) < 10:
        raise HTTPException(429, "Juda tez-tez. 10 soniyadan keyin qayta urinib ko'ring.")
    _last_test[user] = now

    ch_row = await _get_telegram_channel(db)
    cfg = _decode_cfg(ch_row)
    channel = TelegramChannel(cfg.get("bot_token", ""), cfg.get("chat_ids") or [])
    if not channel.is_configured():
        raise HTTPException(400, "Telegram kanal sozlanmagan (bot_token va chat_id kiriting).")

    status, error = await send_test(channel)
    if status != "sent":
        raise HTTPException(502, f"Yuborilmadi: {error}")
    return {"ok": True, "status": status}


# ── GET history ─────────────────────────────────────────

@router.get("/history")
async def get_history(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    actor: dict = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(AlertHistory).order_by(desc(AlertHistory.created_at)).limit(limit).offset(offset)
    )).scalars().all()
    return [
        {
            "id": r.id, "severity": r.severity, "category": r.category,
            "summary": r.summary, "channel_type": r.channel_type,
            "status": r.status, "error": r.error, "ai_used": bool(r.ai_used),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
