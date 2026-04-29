"""GET /health — tashqi monitoring uchun.

Tekshiruvlar:
- database — `SELECT 1` so'rovi
- openai   — agar OPENAI_API_KEY mavjud bo'lsa, `/v1/models` ga ping
- yandex   — agar YANDEX_DELIVERY_TOKEN mavjud bo'lsa, statusni so'rash
- time     — Tashkent zonasidagi joriy vaqt (Asia/Tashkent)

Komponentlardan biri xato bersa ham endpoint 200 qaytaradi (har komponent
o'z `status` maydoniga ega), faqat DB butunlay yiqilsa 503 qaytaradi.
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime
from typing import Any

import httpx
from fastapi import APIRouter, Response, status
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from api import database
from api.logging_config import log_critical


router = APIRouter(tags=["health"])

_PING_TIMEOUT = 5.0


# ── Komponent ping'lari ──────────────────────────────────

async def _ping_db() -> dict[str, Any]:
    started = time.perf_counter()
    try:
        await database.ping()
        return {
            "status": "ok",
            "driver": "postgres" if database.IS_POSTGRES else ("sqlite" if database.IS_SQLITE else "unknown"),
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    except Exception as e:
        log_critical("database", "DB ping failed", error=str(e))
        return {"status": "error", "error": str(e)}


async def _ping_openai() -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {"status": "skipped", "reason": "OPENAI_API_KEY not set"}
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=_PING_TIMEOUT) as client:
            r = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if r.status_code == 200:
            return {
                "status": "ok",
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        return {"status": "error", "http_code": r.status_code}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _ping_yandex() -> dict[str, Any]:
    token = os.getenv("YANDEX_DELIVERY_TOKEN", "").strip()
    if not token:
        return {"status": "skipped", "reason": "YANDEX_DELIVERY_TOKEN not set"}
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=_PING_TIMEOUT) as client:
            # Yandex B2B Cargo — eng yengil endpoint
            r = await client.post(
                "https://b2b.taxi.yandex.net/b2b/cargo/integration/v2/check-price",
                headers={"Authorization": f"Bearer {token}"},
                json={"items": []},
            )
        # 400 ham OK — auth ishlayapti, faqat payload kerak
        if r.status_code in (200, 400, 422):
            return {
                "status": "ok",
                "http_code": r.status_code,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        if r.status_code in (401, 403):
            return {"status": "error", "http_code": r.status_code, "reason": "auth"}
        return {"status": "error", "http_code": r.status_code}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _tashkent_now() -> dict[str, Any]:
    if ZoneInfo is not None:
        try:
            now = datetime.now(ZoneInfo("Asia/Tashkent"))
            return {
                "iso": now.isoformat(),
                "timezone": "Asia/Tashkent",
                "epoch": int(now.timestamp()),
            }
        except Exception:
            pass
    # Fallback — server vaqti
    now = datetime.utcnow()
    return {"iso": now.isoformat() + "Z", "timezone": "UTC", "epoch": int(now.timestamp())}


# ── Endpoint ─────────────────────────────────────────────

@router.get("/health")
async def health(response: Response) -> dict[str, Any]:
    """Liveness + readiness probe.

    Loyiha komponentlarining holatini parallel tekshiradi va bittasi yiqilgan
    bo'lsa ham (DB'dan tashqari) 200 qaytaradi — alert tizimlari komponent
    bo'yicha filterlasin.
    """
    db_res, openai_res, yandex_res = await asyncio.gather(
        _ping_db(), _ping_openai(), _ping_yandex(),
        return_exceptions=False,
    )

    overall = "ok" if db_res.get("status") == "ok" else "degraded"

    # DB butunlay yiqilsa 503 — load balancer'lar shu instance'ni chetlatadi
    if db_res.get("status") != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": overall,
        "components": {
            "database": db_res,
            "openai": openai_res,
            "yandex": yandex_res,
        },
        "server_time": _tashkent_now(),
    }
