"""O'zbekiston vaqti (Asia/Tashkent) yordamchilari.

DB da vaqt UTC (naive) saqlanadi. UI/biznes kunlari — Tashkent kalendari bo'yicha.
Server OS boshqa mamlakatda bo'lsa ham shu modul orqali bir xil natija chiqadi.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

UZ_TZ = ZoneInfo("Asia/Tashkent")
UTC = timezone.utc


def utc_now() -> datetime:
    """DB uchun naive UTC now."""
    return datetime.now(UTC).replace(tzinfo=None)


def uz_now() -> datetime:
    """Asia/Tashkent aware now."""
    return datetime.now(UZ_TZ)


def as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_uz(dt: datetime) -> datetime:
    return as_utc(dt).astimezone(UZ_TZ)


def iso_utc(dt: Optional[datetime]) -> Optional[str]:
    """Frontend uchun UTC ISO (Z suffix) — JS local deb o'qimasin."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.isoformat(sep="T") + "Z"
    return dt.astimezone(UTC).isoformat(sep="T").replace("+00:00", "Z")


def uz_day_bounds_utc(d: date) -> Tuple[datetime, datetime]:
    """Tashkent kunining [start, end) oralig'i — naive UTC (SQL filter uchun)."""
    start_uz = datetime.combine(d, time.min, tzinfo=UZ_TZ)
    end_uz = start_uz + timedelta(days=1)
    start_utc = start_uz.astimezone(UTC).replace(tzinfo=None)
    end_utc = end_uz.astimezone(UTC).replace(tzinfo=None)
    return start_utc, end_utc


def parse_yyyy_mm_dd(value: str) -> Optional[date]:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError, TypeError):
        return None
