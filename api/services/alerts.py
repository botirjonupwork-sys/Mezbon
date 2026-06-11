"""Kritik xato bildirishnomasi — endi ko'p-kanalli alert_router'ga delegatsiya qiladi.

`log_critical()` shu modulning `notify_critical()` funksiyasini chaqiradi (39+ joyda).
Tarixiy interfeys saqlangan: `notify_critical(category, message, context)`.

Haqiqiy ish endi `api/services/alert_router.py` da bajariladi:
  qoida filtri → dedup → Security AI tahlili → kanal(lar)ga yuborish → tarix.
Kanal sozlamasi DB'dan keladi; DB'da kanal bo'lmasa .env ALERT_BOT_TOKEN/ALERT_CHAT_ID
ga qaytadi (orqaga moslik).
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


def notify_critical(category: str, message: str, context: dict[str, Any] | None = None) -> None:
    """Kritik hodisa — ko'p-kanalli routerga uzatiladi (fire-and-forget, bloklamaydi).

    `log_critical` orqali keladigan hodisalar 'critical' severity bilan boradi;
    router qoida/severity/quiet-hours/dedup'ni o'zi hal qiladi.
    """
    try:
        from api.services.alert_router import dispatch
        dispatch(category, message, context or {}, severity_hint="critical", title=category.capitalize())
    except Exception as e:
        # Alert tizimi yiqilsa ham asosiy oqim buzilmaydi
        log.warning("notify_critical dispatch xato: %s", e)
