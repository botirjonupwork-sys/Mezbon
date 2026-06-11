"""Telegram bildirishnoma kanali.

Config (shifrlangan JSON'dan keladi):
  {"bot_token": "123:ABC", "chat_ids": ["111", "@kanal"]}

Konfiguratsiya bo'sh bo'lsa — .env'dagi ALERT_BOT_TOKEN/ALERT_CHAT_ID'ga qaytadi
(eski deploy'lar uchun orqaga moslik).
"""
from __future__ import annotations

import html

import httpx

from api.config import settings
from api.services.channels.base import Alert, Channel, SEVERITY_EMOJI

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _esc(s) -> str:
    return html.escape(str(s)) if s is not None else ""


def _format(alert: Alert) -> str:
    emoji = SEVERITY_EMOJI.get(alert.severity, "🔔")
    lines = [
        f"{emoji} <b>{alert.severity.upper()} · {_esc(alert.category)}</b>",
        f"<b>{_esc(alert.title)}</b>",
        _esc(alert.summary),
    ]
    if alert.action:
        lines.append(f"\n👉 <i>{_esc(alert.action)}</i>")
    if alert.context:
        ctx = []
        for k, v in list(alert.context.items())[:8]:
            sv = _esc(v)
            if len(sv) > 180:
                sv = sv[:180] + "…"
            ctx.append(f"  • <code>{_esc(k)}</code>: {sv}")
        if ctx:
            lines.append("\n" + "\n".join(ctx))
    if alert.ai_used:
        lines.append("\n<i>🤖 AI tahlil</i>")
    return "\n".join(lines)


class TelegramChannel(Channel):
    type = "telegram"

    def __init__(self, bot_token: str = "", chat_ids: list[str] | None = None):
        self.bot_token = (bot_token or "").strip() or (settings.ALERT_BOT_TOKEN or "").strip()
        ids = chat_ids if chat_ids else []
        if not ids and settings.ALERT_CHAT_ID:
            ids = [settings.ALERT_CHAT_ID]
        self.chat_ids = [str(c).strip() for c in ids if str(c).strip()]

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_ids)

    async def send(self, alert: Alert) -> None:
        if not self.is_configured():
            raise RuntimeError("Telegram kanal sozlanmagan (bot_token/chat_ids yo'q)")
        text = _format(alert)
        url = _TELEGRAM_API.format(token=self.bot_token)
        errors = []
        async with httpx.AsyncClient(timeout=8.0) as client:
            for chat_id in self.chat_ids:
                try:
                    r = await client.post(url, json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    })
                    if r.status_code != 200:
                        errors.append(f"{chat_id}: HTTP {r.status_code} {r.text[:120]}")
                except Exception as e:
                    errors.append(f"{chat_id}: {e}")
        if errors and len(errors) == len(self.chat_ids):
            # Hammasi muvaffaqiyatsiz bo'lsa — xato (router retry/failed yozadi)
            raise RuntimeError("; ".join(errors))
