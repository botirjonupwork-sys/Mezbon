"""Bildirishnoma kanali interfeysi va Alert ma'lumot strukturasi.

Har bir kanal (Telegram, kelajakda email/webhook/sms) shu interfeysga ergashadi:
`async send(alert)` — muvaffaqiyatli yuborsa qaytadi, aks holda Exception ko'taradi
(router uni ushlab, alert_history'ga "failed" yozadi va retry qiladi).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}
SEVERITY_EMOJI = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}


@dataclass
class Alert:
    """Yuboriladigan bildirishnoma — Security AI tahlilidan keyingi yakuniy shakl."""
    category: str                       # payment | auth | security | database | ...
    severity: str                       # info | warning | critical
    title: str                          # qisqa sarlavha
    summary: str                        # inson o'qiy oladigan xulosa (AI yoki fallback)
    raw_message: str                    # asl xom xabar
    context: dict = field(default_factory=dict)
    action: str = ""                    # tavsiya etilgan harakat (AI bersa)
    ai_used: bool = False               # LLM tahlil ishlatildimi


class Channel(ABC):
    type: str = ""

    @abstractmethod
    async def send(self, alert: Alert) -> None:
        """Bildirishnomani yuborish. Xatoda Exception ko'taradi."""
