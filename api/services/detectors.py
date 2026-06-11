"""Xavfsizlik signal detektorlari — hodisalarni agregatlab alert_router'ga uzatadi.

Maqsad: bir nechta mayda hodisani (masalan 12 ta login urinishi) BITTA mazmunli
bildirishnomaga jamlash — har biri uchun alohida xabar emas. In-memory sirpanuvchi
oyna ishlatiladi; chegaradan oshganda bitta agregat alert yuboriladi va qisqa
"cooldown" o'rnatiladi (spam bo'lmasligi uchun).

Barcha funksiyalar BLOKLAMAYDI va exception ko'tarmaydi — chaqirilgan joyni
(masalan login oqimini) hech qachon sindirmaydi.
"""
from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger(__name__)

_lock = threading.Lock()
# key -> {"hits": [epoch, ...], "cooldown_until": epoch}
_state: dict[str, dict] = {}


def _record(key: str, window: int, threshold: int, cooldown: int) -> int | None:
    """Hodisani qayd etadi. Chegara oshsa — jami sonni qaytaradi, aks holda None."""
    now = time.time()
    with _lock:
        st = _state.setdefault(key, {"hits": [], "cooldown_until": 0.0})
        if now < st["cooldown_until"]:
            st["hits"].append(now)
            return None
        st["hits"] = [t for t in st["hits"] if now - t <= window]
        st["hits"].append(now)
        if len(st["hits"]) >= threshold:
            count = len(st["hits"])
            st["hits"] = []
            st["cooldown_until"] = now + cooldown
            return count
        return None


def _dispatch(category: str, message: str, context: dict, severity: str) -> None:
    try:
        from api.services.alert_router import dispatch
        dispatch(category, message, context, severity_hint=severity, title=context.get("_title") or category.capitalize())
    except Exception as e:
        log.warning("detector dispatch xato: %s", e)


# ── Brute-force login ───────────────────────────────────

def failed_login(username: str, ip: str | None, *, is_super: bool = False) -> None:
    """Ketma-ket muvaffaqiyatsiz login urinishlarini kuzatadi."""
    try:
        # super-admin uchun sezgirroq chegara
        threshold = 4 if is_super else 6
        window = 300       # 5 daqiqa
        cooldown = 600     # 10 daqiqa
        key = f"login:{'super' if is_super else 'admin'}:{username or '?'}"
        count = _record(key, window, threshold, cooldown)
        if count:
            who = "super-admin" if is_super else "admin"
            _dispatch(
                "security",
                f"Ko'p marta muvaffaqiyatsiz {who} login urinishi: 5 daqiqada {count} marta "
                f"({username!r} foydalanuvchisi).",
                {"username": str(username), "ip": str(ip or "?"), "urinishlar": count,
                 "_title": "Brute-force urinish"},
                "critical" if is_super else "warning",
            )
    except Exception as e:
        log.warning("failed_login detector xato: %s", e)


# ── Webhook auth-fail to'lqini ──────────────────────────

def webhook_auth_failed(provider: str, ip: str | None) -> None:
    """To'lov/yetkazib berish webhook'larida ketma-ket auth rad etishlari."""
    try:
        window = 300
        threshold = 5
        cooldown = 600
        count = _record(f"webhook:{provider}", window, threshold, cooldown)
        if count:
            _dispatch(
                "security",
                f"{provider} webhook'ida ketma-ket autentifikatsiya xatosi: "
                f"5 daqiqada {count} marta. Soxta so'rovlar bo'lishi mumkin.",
                {"provider": provider, "ip": str(ip or "?"), "urinishlar": count,
                 "_title": "Webhook auth-fail to'lqini"},
                "warning",
            )
    except Exception as e:
        log.warning("webhook_auth_failed detector xato: %s", e)
