"""Bot menejeri — barcha restoran botlarini boshqaradi (har biri ALOHIDA subprocess).

Nega subprocess (asyncio task emas):
  bot/api_client.py global state (_restaurant_id, _auth_token) ishlatadi —
  bir process'da bir nechta bot ishlatib bo'lmaydi (restoranlar aralashib ketadi).
  Shuning uchun har bir bot o'z subprocess'ida (o'z xotirasi bilan) ishlaydi.

Boshqaruv:
  * DB'dagi bot_token bor barcha restoranlar uchun customer + courier bot spawn qilinadi
  * O'lib qolgan bot avtomatik qayta tiklanadi (crash backoff bilan)
  * Token o'zgarsa yoki API bot_reload_at ni yangilasa → bot restart
  * Yangi token qo'shilsa → spawn; token o'chirilsa/restoran blocklansa-da... bot ishlaydi
    (block xabarini ko'rsatishi uchun — ServiceGate middleware hal qiladi)

Ishga tushirish:  python -m bot.manager
Restart (API):    super_legacy.py POST /super/bots/restart  va  /super/bots/{rid}/restart
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select  # noqa: E402

from api.database import AsyncSessionLocal  # noqa: E402
from database.models import Restaurant  # noqa: E402

log = logging.getLogger("bot.manager")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

POLL_INTERVAL = 10           # DB'ni necha sekundda tekshirish
MIN_RESTART_INTERVAL = 30    # crash-loop himoyasi: o'lgan botni shu oraliqdan tez respawn qilmaymiz

# (kind, module, env_var, restaurant_attr)
BOT_KINDS = [
    ("customer", "bot.main", "BOT_TOKEN", "bot_token"),
    ("courier", "courier_bot.main", "COURIER_BOT_TOKEN", "courier_bot_token"),
]


class _Proc:
    __slots__ = ("proc", "token", "started_at")

    def __init__(self, proc, token: str, started_at: datetime):
        self.proc = proc
        self.token = token
        self.started_at = started_at


class BotManager:
    def __init__(self):
        self._procs: dict[tuple[int, str], _Proc] = {}
        self._last_attempt: dict[tuple[int, str], datetime] = {}

    async def _targets(self) -> dict[tuple[int, str], tuple]:
        """{(rid, kind): (rest, token, module, env_var)} — token bor barcha botlar."""
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(select(Restaurant))).scalars().all()
        out: dict[tuple[int, str], tuple] = {}
        for r in rows:
            for kind, module, env_var, attr in BOT_KINDS:
                token = (getattr(r, attr, None) or "").strip()
                if token:
                    out[(r.id, kind)] = (r, token, module, env_var)
        return out

    async def _spawn(self, key, rest, token, module, env_var):
        env = dict(os.environ)
        env[env_var] = token
        env["BOT_RESTAURANT_ID"] = str(rest.id)
        proc = await asyncio.create_subprocess_exec(sys.executable, "-m", module, env=env)
        self._procs[key] = _Proc(proc, token, datetime.utcnow())
        self._last_attempt[key] = datetime.utcnow()
        log.info("Spawn rid=%s kind=%s pid=%s (%s)", key[0], key[1], proc.pid, rest.name)

    async def _stop(self, key):
        p = self._procs.pop(key, None)
        if not p:
            return
        if p.proc.returncode is None:
            try:
                p.proc.terminate()
                await asyncio.wait_for(p.proc.wait(), timeout=10)
            except Exception:
                try:
                    p.proc.kill()
                except Exception:
                    pass
        log.info("Stop rid=%s kind=%s", key[0], key[1])

    def _backoff_ok(self, key) -> bool:
        last = self._last_attempt.get(key)
        return (not last) or (datetime.utcnow() - last > timedelta(seconds=MIN_RESTART_INTERVAL))

    async def reconcile(self):
        targets = await self._targets()

        # Endi kerak bo'lmagan botlarni to'xtatamiz (token o'chirilgan/restoran o'chirilgan)
        for key in list(self._procs):
            if key not in targets:
                await self._stop(key)

        # Start / restart
        for key, (rest, token, module, env_var) in targets.items():
            p = self._procs.get(key)
            reason = None
            if not p:
                reason = "new"
            elif p.proc.returncode is not None:
                reason = "died"
            elif p.token != token:
                reason = "token_changed"
            elif rest.bot_reload_at and rest.bot_reload_at > p.started_at:
                reason = "reload_signal"

            if not reason:
                continue
            if reason == "died" and not self._backoff_ok(key):
                continue  # crash-loop himoyasi
            if p:
                await self._stop(key)
            await self._spawn(key, rest, token, module, env_var)
            log.info("Restart rid=%s kind=%s sabab=%s", key[0], key[1], reason)

    async def run(self):
        log.info("BotManager ishga tushdi (poll=%ss)", POLL_INTERVAL)
        try:
            while True:
                try:
                    await self.reconcile()
                except Exception as e:
                    log.exception("reconcile xato: %s", e)
                await asyncio.sleep(POLL_INTERVAL)
        finally:
            for key in list(self._procs):
                await self._stop(key)


def main():
    asyncio.run(BotManager().run())


if __name__ == "__main__":
    main()
