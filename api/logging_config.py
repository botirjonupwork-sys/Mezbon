"""Markazlashtirilgan logging.

Uchta handler ishlaydi:
- console (DEBUG/INFO) — terminalga oddiy chiqish
- logs/api.log (INFO+) — kunlik aylantiriluvchi (RotatingFileHandler)
- logs/critical.log (ERROR+) — kritik xato hodisalari (to'lov, AI, DB, integratsiya)

`get_critical_logger()` qaytaradigan logger barcha kritik xatolar uchun
markaziy nuqtaga yozadi — Sentry/Slack alert bilan keyin ulash oson bo'ladi.

`log_critical(category, message, **context)` — qulay yordamchi:
    log_critical("payment", "Click webhook signature mismatch",
                 payment_id=42, restaurant_id=1)
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from typing import Any


LOG_DIR = os.path.abspath(os.path.join(os.getcwd(), "logs"))
os.makedirs(LOG_DIR, exist_ok=True)

API_LOG = os.path.join(LOG_DIR, "api.log")
CRITICAL_LOG = os.path.join(LOG_DIR, "critical.log")

_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

_CONFIGURED = False


def setup_logging(level: int = logging.INFO) -> None:
    """API ishga tushganda bir martagina chaqirilishi kerak.

    Qayta chaqirilsa handler dublikatlari yaratilmaydi (idempotent).
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    formatter = logging.Formatter(_FMT, datefmt=_DATEFMT)

    # ── Root ─────────────────────────────────────────
    root = logging.getLogger()
    root.setLevel(level)
    # Eski handlerlarni tozalash (test/restart paytida)
    for h in list(root.handlers):
        root.removeHandler(h)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(formatter)
    root.addHandler(console)

    api_file = logging.handlers.RotatingFileHandler(
        API_LOG, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8",
    )
    api_file.setLevel(logging.INFO)
    api_file.setFormatter(formatter)
    root.addHandler(api_file)

    # ── Critical-only logger ────────────────────────
    critical = logging.getLogger("muhsina.critical")
    critical.setLevel(logging.ERROR)
    critical.propagate = True   # api.log ga ham tushsin
    critical_file = logging.handlers.RotatingFileHandler(
        CRITICAL_LOG, maxBytes=10 * 1024 * 1024, backupCount=10, encoding="utf-8",
    )
    critical_file.setLevel(logging.ERROR)
    critical_file.setFormatter(formatter)
    # Eski handlerlarni tozalab, yangisini qo'shamiz (idempotent)
    for h in list(critical.handlers):
        critical.removeHandler(h)
    critical.addHandler(critical_file)

    # SQLAlchemy va uvicorn loglarini biroz tinchlantiramiz
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    _CONFIGURED = True


def get_critical_logger() -> logging.Logger:
    """Kritik xato logger — to'lov, AI, integratsiya uzilishi uchun."""
    return logging.getLogger("muhsina.critical")


def log_critical(category: str, message: str, **context: Any) -> None:
    """Kritik xato yozish uchun qisqa yordamchi.

    Args:
        category: 'payment' | 'ai_agent' | 'yandex' | 'database' | 'auth' | ...
        message:  qisqa, inson o'qiy oladigan xato matni
        context:  qo'shimcha kontekst (JSON formatida log faylga yoziladi)

    Telegram alert kanali sozlangan bo'lsa, xabar shu kanalga ham
    yuboriladi (fire-and-forget, dedup bilan).
    """
    logger = get_critical_logger()
    try:
        ctx = json.dumps(context, ensure_ascii=False, default=str) if context else ""
    except Exception:
        ctx = str(context)
    logger.error("[%s] %s | ctx=%s", category, message, ctx)
    # Telegram bildirishnomasi — sokin, asosiy oqimni bloklamaydi
    try:
        from api.services.alerts import notify_critical
        notify_critical(category, message, context)
    except Exception:
        pass  # Alert tizimi yiqilsa ham log yozilgan bo'ladi
