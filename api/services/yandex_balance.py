"""Yandex Delivery balance monitoring.

Yandex Express v2 hujjatlarida balansni o'qish metodi yo'q. Shu sababli hozir
balans qiymati manual/mock source orqali yuritiladi; real endpoint berilsa,
`fetch_yandex_balance()` ichida adapter almashtiriladi.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Restaurant


STATUS_OK = "ok"
STATUS_LOW = "low"
STATUS_CRITICAL = "critical"
STATUS_UNKNOWN = "unknown"
STATUS_DISABLED = "disabled"

DEFAULT_LOW_THRESHOLD = 300000.0
DEFAULT_CRITICAL_THRESHOLD = 100000.0
ALERT_COOLDOWN = timedelta(hours=6)


class YandexBalanceError(Exception):
    pass


def compute_balance_status(
    amount: float | None,
    *,
    low_threshold: float | None,
    critical_threshold: float | None,
) -> str:
    if amount is None:
        return STATUS_UNKNOWN
    critical = float(critical_threshold or DEFAULT_CRITICAL_THRESHOLD)
    low = float(low_threshold or DEFAULT_LOW_THRESHOLD)
    if amount <= critical:
        return STATUS_CRITICAL
    if amount <= low:
        return STATUS_LOW
    return STATUS_OK


def yandex_balance_snapshot(rest: Restaurant) -> dict[str, Any]:
    return {
        "restaurant_id": rest.id,
        "restaurant_name": rest.name,
        "monitor_enabled": bool(rest.yandex_balance_monitor_enabled),
        "amount": float(rest.yandex_balance_amount) if rest.yandex_balance_amount is not None else None,
        "currency": rest.yandex_balance_currency or "UZS",
        "checked_at": rest.yandex_balance_checked_at.isoformat() if rest.yandex_balance_checked_at else None,
        "low_threshold": float(rest.yandex_balance_low_threshold or DEFAULT_LOW_THRESHOLD),
        "critical_threshold": float(rest.yandex_balance_critical_threshold or DEFAULT_CRITICAL_THRESHOLD),
        "status": rest.yandex_balance_status or STATUS_UNKNOWN,
        "source": rest.yandex_balance_source or "manual",
        "last_alert_at": rest.yandex_balance_last_alert_at.isoformat() if rest.yandex_balance_last_alert_at else None,
        "block_on_critical": bool(rest.yandex_balance_block_on_critical),
        "delivery_provider": rest.delivery_provider or "own",
        "test_mode": bool(rest.yandex_test_mode),
    }


async def fetch_yandex_balance(rest: Restaurant) -> dict[str, Any]:
    """Fetch balance from configured source.

    Current implementation intentionally uses the stored manual/mock value,
    because the public Yandex Delivery Express API exposes order/claim methods
    but no confirmed account balance endpoint.
    """
    return {
        "amount": float(rest.yandex_balance_amount) if rest.yandex_balance_amount is not None else None,
        "currency": rest.yandex_balance_currency or "UZS",
        "source": "mock" if rest.yandex_test_mode else (rest.yandex_balance_source or "manual"),
    }


async def check_restaurant_yandex_balance(
    db: AsyncSession,
    rest: Restaurant,
    *,
    notify: bool = False,
) -> dict[str, Any]:
    previous_status = rest.yandex_balance_status or STATUS_UNKNOWN

    if not rest.yandex_balance_monitor_enabled:
        rest.yandex_balance_status = STATUS_DISABLED
        rest.yandex_balance_checked_at = datetime.utcnow()
        await db.commit()
        return yandex_balance_snapshot(rest)

    data = await fetch_yandex_balance(rest)
    rest.yandex_balance_amount = data.get("amount")
    rest.yandex_balance_currency = data.get("currency") or "UZS"
    rest.yandex_balance_source = data.get("source") or "manual"
    rest.yandex_balance_checked_at = datetime.utcnow()
    rest.yandex_balance_status = compute_balance_status(
        rest.yandex_balance_amount,
        low_threshold=rest.yandex_balance_low_threshold,
        critical_threshold=rest.yandex_balance_critical_threshold,
    )

    should_notify = notify and _should_notify_balance_status(rest, previous_status)
    if should_notify:
        await _notify_balance_status(rest, previous_status)
        rest.yandex_balance_last_alert_at = datetime.utcnow()

    await db.commit()
    return yandex_balance_snapshot(rest)


async def check_all_yandex_balances(db: AsyncSession, *, notify: bool = True) -> dict[str, Any]:
    result = await db.execute(
        select(Restaurant).where(
            Restaurant.delivery_provider == "yandex",
            Restaurant.yandex_balance_monitor_enabled == True,
        )
    )
    restaurants = result.scalars().all()
    checked: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for rest in restaurants:
        try:
            checked.append(await check_restaurant_yandex_balance(db, rest, notify=notify))
        except Exception as e:
            errors.append({"restaurant_id": rest.id, "restaurant_name": rest.name, "error": str(e)})

    return {
        "checked": len(checked),
        "errors": errors,
        "items": checked,
    }


def yandex_balance_ai_template() -> str:
    return (
        "Siz restoran operatorisiz. Buyurtma qabul qilasiz, menyudan tashqari mahsulot taklif qilmaysiz.\n"
        "Agar yetkazib berish Yandex orqali bo'lsa va tizim balans ogohlantirishini qaytarsa, "
        "mijozga ichki texnik tafsilotlarni aytmang.\n"
        "Balans kritik bo'lsa, buyurtmani operatorga/escalation kanaliga belgilang va mijozga pickup "
        "yoki keyinroq yetkazib berish variantini muloyim taklif qiling.\n"
        "Balans past bo'lsa, buyurtmani odatdagidek qabul qiling, lekin operatorni xabardor qiling."
    )


def _should_notify_balance_status(rest: Restaurant, previous_status: str) -> bool:
    current = rest.yandex_balance_status or STATUS_UNKNOWN
    if current not in {STATUS_LOW, STATUS_CRITICAL, STATUS_OK, STATUS_UNKNOWN}:
        return False
    if current == STATUS_OK and previous_status not in {STATUS_LOW, STATUS_CRITICAL, STATUS_UNKNOWN}:
        return False
    if current == previous_status and current not in {STATUS_LOW, STATUS_CRITICAL, STATUS_UNKNOWN}:
        return False
    if rest.yandex_balance_last_alert_at:
        if datetime.utcnow() - rest.yandex_balance_last_alert_at < ALERT_COOLDOWN and current == previous_status:
            return False
    return current in {STATUS_LOW, STATUS_CRITICAL, STATUS_UNKNOWN} or (
        current == STATUS_OK and previous_status in {STATUS_LOW, STATUS_CRITICAL, STATUS_UNKNOWN}
    )


async def _notify_balance_status(rest: Restaurant, previous_status: str) -> None:
    from api.services.notifier import (
        notify_platform_admin,
        notify_restaurant_owner,
        yandex_balance_text,
    )

    text = yandex_balance_text(rest, previous_status)
    await notify_restaurant_owner(rest, text)
    if (rest.yandex_balance_status or STATUS_UNKNOWN) in {STATUS_CRITICAL, STATUS_UNKNOWN}:
        await notify_platform_admin(text)
