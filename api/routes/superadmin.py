"""Super Admin endpointlari — bot, panel nomi, tizim sozlamalari"""
import os
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/superadmin", tags=["superadmin"])

SUPER_SETTINGS_FILE = "super_settings.json"


def _load_super_settings() -> dict:
    if not os.path.exists(SUPER_SETTINGS_FILE):
        return {
            "panel_name": "Muhsina Admin",
            "bots": [],
        }
    try:
        with open(SUPER_SETTINGS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"panel_name": "Muhsina Admin", "bots": []}


def _save_super_settings(data: dict):
    with open(SUPER_SETTINGS_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Schemas ──────────────────────────────────────────
class PanelNameUpdate(BaseModel):
    panel_name: str


class BotCreate(BaseModel):
    name: str
    token: str
    bot_type: str = "customer"  # customer, courier, notification


class BotUpdate(BaseModel):
    name: Optional[str] = None
    token: Optional[str] = None
    is_active: Optional[bool] = None


# ── Panel sozlamalari ────────────────────────────────
@router.get("/settings")
async def get_super_settings():
    settings = _load_super_settings()
    # Token larni maskalash
    for bot in settings.get("bots", []):
        t = bot.get("token", "")
        if len(t) > 10:
            bot["token_masked"] = t[:5] + "..." + t[-4:]
        else:
            bot["token_masked"] = "***"
    return settings


@router.put("/panel-name")
async def update_panel_name(data: PanelNameUpdate):
    settings = _load_super_settings()
    settings["panel_name"] = data.panel_name
    _save_super_settings(settings)
    return {"success": True, "panel_name": data.panel_name}


# ── Bot boshqaruvi ───────────────────────────────────
@router.get("/bots")
async def list_bots():
    settings = _load_super_settings()
    bots = settings.get("bots", [])
    result = []
    for b in bots:
        result.append({
            "id": b["id"],
            "name": b["name"],
            "bot_type": b.get("bot_type", "customer"),
            "is_active": b.get("is_active", True),
            "token_masked": (b["token"][:5] + "..." + b["token"][-4:]) if len(b.get("token", "")) > 10 else "***",
            "created_at": b.get("created_at"),
        })
    return result


@router.post("/bots")
async def add_bot(data: BotCreate):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    settings = _load_super_settings()
    bots = settings.get("bots", [])
    new_id = max((b["id"] for b in bots), default=0) + 1
    bot = {
        "id": new_id,
        "name": data.name,
        "token": data.token,
        "bot_type": data.bot_type,
        "is_active": True,
        "created_at": datetime.now(ZoneInfo("Asia/Tashkent")).isoformat(),
    }
    bots.append(bot)
    settings["bots"] = bots
    _save_super_settings(settings)
    return {"id": new_id, "name": data.name}


@router.put("/bots/{bot_id}")
async def update_bot(bot_id: int, data: BotUpdate):
    settings = _load_super_settings()
    bots = settings.get("bots", [])
    for b in bots:
        if b["id"] == bot_id:
            if data.name is not None:
                b["name"] = data.name
            if data.token is not None:
                b["token"] = data.token
            if data.is_active is not None:
                b["is_active"] = data.is_active
            settings["bots"] = bots
            _save_super_settings(settings)
            return {"success": True}
    raise HTTPException(404, "Bot topilmadi")


@router.delete("/bots/{bot_id}")
async def delete_bot(bot_id: int):
    settings = _load_super_settings()
    bots = settings.get("bots", [])
    new_bots = [b for b in bots if b["id"] != bot_id]
    if len(new_bots) == len(bots):
        raise HTTPException(404, "Bot topilmadi")
    settings["bots"] = new_bots
    _save_super_settings(settings)
    return {"success": True}


# ── Tizim ma'lumotlari ──────────────────────────────
@router.get("/system-info")
async def system_info():
    from api.config import settings as app_settings
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("Asia/Tashkent"))
    return {
        "server_time": now.isoformat(),
        "timezone": "Asia/Tashkent",
        "api_url": app_settings.API_URL,
        "debug": app_settings.DEBUG,
        "bot_token_set": bool(app_settings.BOT_TOKEN),
        "courier_bot_token_set": bool(app_settings.COURIER_BOT_TOKEN),
        "alice_api_key_set": bool(app_settings.ALICE_API_KEY),
        "yandex_delivery_set": bool(app_settings.YANDEX_DELIVERY_TOKEN),
    }
