"""Kritik xatolar uchun Telegram bildirishnoma.

`log_critical()` shu modulning `notify_critical()` funksiyasini chaqiradi.
Agar `.env`'da `ALERT_BOT_TOKEN` va `ALERT_CHAT_ID` mavjud bo'lsa — Telegram
xabari yuboriladi. Aks holda — sokin o'tib ketadi (no-op).

Tashkil etish:
- Fire-and-forget thread orqali HTTP so'rov — log_critical() bloklanmaydi
- Dedup: bir xil (category, message) jufti `ALERT_DEDUP_SECONDS` davomida
  qayta yuborilmaydi (in-memory hash set)
- Telegram xato bersa — sokin (Telegram chiqib qolsa, asosiy app yiqilmasin)
"""
from __future__ import annotations

import hashlib
import threading
import time
from typing import Any

import httpx

from api.config import settings


_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# Dedup cache: {hash: last_sent_epoch}
_dedup: dict[str, float] = {}
_dedup_lock = threading.Lock()


def _is_configured() -> bool:
    return bool(settings.ALERT_BOT_TOKEN and settings.ALERT_CHAT_ID)


def _dedup_key(category: str, message: str) -> str:
    return hashlib.sha256(f"{category}|{message}".encode()).hexdigest()


def _should_send(key: str) -> bool:
    """TTL ichida bir martagina ruxsat beradi. GC ham shu yerda."""
    now = time.time()
    ttl = max(30, int(settings.ALERT_DEDUP_SECONDS or 300))
    with _dedup_lock:
        # Eski yozuvlarni tozalash
        stale = [k for k, t in _dedup.items() if now - t > ttl]
        for k in stale:
            _dedup.pop(k, None)
        if key in _dedup:
            return False
        _dedup[key] = now
        return True


def _format_html(category: str, message: str, context: dict[str, Any]) -> str:
    safe_msg = (message or "").replace("<", "&lt;").replace(">", "&gt;")
    lines = [
        f"🚨 <b>CRITICAL [{category}]</b>",
        f"<i>{safe_msg}</i>",
    ]
    if context:
        ctx_lines = []
        for k, v in list(context.items())[:10]:  # haddan tashqari uzun bo'lmasin
            sv = str(v).replace("<", "&lt;").replace(">", "&gt;")
            if len(sv) > 200:
                sv = sv[:200] + "…"
            ctx_lines.append(f"  • <code>{k}</code> = {sv}")
        lines.append("\n".join(ctx_lines))
    return "\n".join(lines)


def _send_sync(text: str) -> None:
    """Sinxron HTTP — alohida thread'da ishlaydi."""
    if not _is_configured():
        return
    try:
        with httpx.Client(timeout=5.0) as client:
            client.post(
                _TELEGRAM_API.format(token=settings.ALERT_BOT_TOKEN),
                json={
                    "chat_id": settings.ALERT_CHAT_ID,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
    except Exception:
        # Asosiy ilovani buzmaslik uchun jim
        pass


def notify_critical(category: str, message: str, context: dict[str, Any] | None = None) -> None:
    """Kritik xato yuz berganda Telegram'ga jo'natadi (fire-and-forget).

    Bloklanmaydi: alohida daemon thread'da yuboriladi. Konfiguratsiya yo'q
    bo'lsa — no-op. Bir xil xato `ALERT_DEDUP_SECONDS` davomida bir martagina.
    """
    if not _is_configured():
        return
    key = _dedup_key(category, message)
    if not _should_send(key):
        return
    text = _format_html(category, message, context or {})
    threading.Thread(target=_send_sync, args=(text,), daemon=True).start()
