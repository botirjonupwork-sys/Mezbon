"""Bildirishnoma routeri — hodisalarni kanal(lar)ga yo'naltiradi.

Oqim:
  dispatch() → fon thread → _process():
    1. konfiguratsiya (kanallar + qoidalar) DB'dan (qisqa kesh bilan)
    2. qoida filtri (hodisa kategoriyasi + minimal severity)
    3. quiet hours (tunda faqat critical o'tadi)
    4. dedup (bir xil xabar oyna ichida bir marta)
    5. Security AI tahlili (LLM yoki rule-based)
    6. har kanalga yuborish + alert_history yozuvi (xatoda retry)

`dispatch()` BLOKLAMAYDI — alohida daemon thread'da o'z event-loop'i bilan ishlaydi,
shuning uchun log_critical() chaqirilgan joyni (sync yoki async) ushlab turmaydi.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from api.config import settings
from api.services import platform, security_ai
from api.services.channels.base import Alert, SEVERITY_ORDER
from api.services.channels.telegram import TelegramChannel

log = logging.getLogger(__name__)
UZ_TZ = ZoneInfo("Asia/Tashkent")

_RETRY_ATTEMPTS = 2
_CONFIG_TTL = 15.0

# ── Dedup (bir xil xabar oyna ichida bir marta) ─────────
_dedup: dict[str, float] = {}
_dedup_lock = threading.Lock()

# ── Config kesh ─────────────────────────────────────────
_cfg_cache: dict | None = None
_cfg_cache_ts: float = 0.0
_cfg_lock = threading.Lock()


def invalidate_config_cache() -> None:
    """Super-admin sozlamani o'zgartirganda chaqiriladi."""
    global _cfg_cache, _cfg_cache_ts
    with _cfg_lock:
        _cfg_cache = None
        _cfg_cache_ts = 0.0


def _dedup_key(category: str, message: str) -> str:
    return hashlib.sha256(f"{category}|{message}".encode()).hexdigest()


def _should_send(category: str, message: str) -> bool:
    now = time.time()
    ttl = max(30, int(settings.ALERT_DEDUP_SECONDS or 300))
    key = _dedup_key(category, message)
    with _dedup_lock:
        stale = [k for k, t in _dedup.items() if now - t > ttl]
        for k in stale:
            _dedup.pop(k, None)
        if key in _dedup:
            return False
        _dedup[key] = now
        return True


def _parse_hhmm(val: Any) -> int | None:
    """'HH:MM' yoki soat raqamini daqiqaga aylantiradi (00:00 dan)."""
    if val is None or val == "":
        return None
    try:
        s = str(val)
        if ":" in s:
            h, m = s.split(":", 1)
            return int(h) * 60 + int(m)
        return int(s) * 60
    except Exception:
        return None


def _in_quiet_hours() -> bool:
    start = _parse_hhmm(platform.get("quiet_hours_start"))
    end = _parse_hhmm(platform.get("quiet_hours_end"))
    if start is None or end is None or start == end:
        return False
    now = datetime.now(UZ_TZ)
    cur = now.hour * 60 + now.minute
    if start < end:
        return start <= cur < end
    # Tundan o'tadigan oyna (masalan 22:00–07:00)
    return cur >= start or cur < end


async def _load_config() -> dict:
    """Kanallar va qoidalarni DB'dan o'qiydi (qisqa kesh bilan)."""
    global _cfg_cache, _cfg_cache_ts
    now = time.time()
    if _cfg_cache is not None and (now - _cfg_cache_ts) < _CONFIG_TTL:
        return _cfg_cache

    channels: list = []
    rules: list = []
    try:
        from sqlalchemy import select
        from api.database import AsyncSessionLocal
        from api.services.field_encryption import decrypt_field
        from database.models import AlertChannel, AlertRule

        async with AsyncSessionLocal() as db:
            ch_rows = (await db.execute(
                select(AlertChannel).where(AlertChannel.enabled == True)  # noqa: E712
            )).scalars().all()
            for row in ch_rows:
                cfg = {}
                if row.config_enc:
                    try:
                        cfg = json.loads(decrypt_field(row.config_enc) or "{}")
                    except Exception:
                        cfg = {}
                if row.type == "telegram":
                    ch = TelegramChannel(cfg.get("bot_token", ""), cfg.get("chat_ids") or [])
                    if ch.is_configured():
                        channels.append(ch)
            rule_rows = (await db.execute(
                select(AlertRule).where(AlertRule.enabled == True)  # noqa: E712
            )).scalars().all()
            rules = [{"category": r.event_category, "min_severity": r.min_severity} for r in rule_rows]
    except Exception as e:
        log.warning("alert_router config DB o'qishda xato: %s", e)

    # Fallback: DB'da kanal yo'q bo'lsa, .env Telegram'iga qaytamiz (orqaga moslik)
    if not channels:
        env_ch = TelegramChannel()
        if env_ch.is_configured():
            channels.append(env_ch)

    cfg = {"channels": channels, "rules": rules}
    with _cfg_lock:
        _cfg_cache = cfg
        _cfg_cache_ts = now
    return cfg


def _passes_rules(category: str, severity: str, rules: list[dict]) -> bool:
    """Hech qanday qoida yo'q bo'lsa: default 'warning'+ o'tadi (info filtrlanadi)."""
    sev_val = SEVERITY_ORDER.get(severity, 1)
    if not rules:
        return sev_val >= SEVERITY_ORDER["warning"]
    # Aniq kategoriya qoidasi yoki '*' (barchasi) qoidasi
    matched = [r for r in rules if r["category"] in (category, "*")]
    if not matched:
        return False
    # Eng past minimal severity'ni qoniqtirsa — o'tadi
    min_needed = min(SEVERITY_ORDER.get(r["min_severity"], 1) for r in matched)
    return sev_val >= min_needed


async def _write_history(alert: Alert, channel_type: str, status: str, error: str | None) -> None:
    try:
        from api.database import AsyncSessionLocal
        from database.models import AlertHistory
        async with AsyncSessionLocal() as db:
            db.add(AlertHistory(
                severity=alert.severity, category=alert.category,
                summary=alert.summary[:1000] if alert.summary else None,
                raw_message=alert.raw_message[:1000] if alert.raw_message else None,
                channel_type=channel_type, status=status, error=error,
                ai_used=alert.ai_used,
            ))
            await db.commit()
    except Exception as e:
        log.warning("alert_history yozishda xato: %s", e)


async def _send_with_retry(channel, alert: Alert) -> tuple[str, str | None]:
    last_err = None
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            await channel.send(alert)
            return "sent", None
        except Exception as e:
            last_err = str(e)
            if attempt < _RETRY_ATTEMPTS - 1:
                await asyncio.sleep(1.5)
    return "failed", last_err


async def _process(category: str, raw_message: str, context: dict,
                   severity_hint: str | None, title: str | None) -> None:
    cfg = await _load_config()
    channels = cfg["channels"]
    if not channels:
        return  # hech qanday kanal sozlanmagan — jim

    # 1. Qoida filtri (hint asosida — AI severity keyin aniqlanadi)
    hint = (severity_hint or "warning").lower()
    if not _passes_rules(category, hint, cfg["rules"]):
        return

    # 2. dedup
    if not _should_send(category, raw_message):
        return

    # 3. Security AI tahlili
    a = await security_ai.analyze(category, raw_message, context, hint)

    # 4. quiet hours — critical bo'lmasa tunda o'tkazib yuboriladi
    alert = Alert(
        category=category, severity=a["severity"], title=title or category.capitalize(),
        summary=a["summary"], raw_message=raw_message, context=context or {},
        action=a.get("action", ""), ai_used=a.get("ai_used", False),
    )
    if alert.severity != "critical" and _in_quiet_hours():
        await _write_history(alert, "-", "skipped", "quiet hours")
        return

    # 5. Yuborish + tarix
    for ch in channels:
        status, error = await _send_with_retry(ch, alert)
        await _write_history(alert, ch.type, status, error)


def _run(category, raw_message, context, severity_hint, title) -> None:
    try:
        asyncio.run(_process(category, raw_message, context, severity_hint, title))
    except Exception as e:
        log.warning("alert_router _run xato: %s", e)


def dispatch(category: str, raw_message: str, context: dict | None = None,
             severity_hint: str | None = "critical", title: str | None = None) -> None:
    """Hodisani fon rejimda kanal(lar)ga yo'naltiradi (fire-and-forget)."""
    threading.Thread(
        target=_run,
        args=(category, raw_message, context or {}, severity_hint, title),
        daemon=True,
    ).start()


async def send_test(channel) -> tuple[str, str | None]:
    """Test endpointi uchun — berilgan kanalga sinov xabari (kutib turadi)."""
    alert = Alert(
        category="test", severity="info", title="Test bildirishnoma",
        summary="Bu — bildirishnoma kanali ishlayotganini tekshirish uchun sinov xabari.",
        raw_message="test", context={"vaqt": datetime.now(UZ_TZ).strftime("%Y-%m-%d %H:%M")},
        ai_used=False,
    )
    return await _send_with_retry(channel, alert)
