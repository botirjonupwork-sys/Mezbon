"""Xprinter / LAN chek-printer AGENTI — kassa kompyuterida ishlaydi (Windows).

Vazifasi: bulutdagi serverga (WebSocket bridge) ulanadi va kelgan ESC/POS cheklarni
mahalliy tarmoqdagi printer IP:port (odatda 9100) ga uzatadi. Server printerga
to'g'ridan-to'g'ri ula olmaydi — shuning uchun shu agent kerak.

ORQA FONDA ISHLATISH (tavsiya etiladi):
  Agentni ko'rinadigan oyna OCHMASDAN, kompyuter yonishi bilan avtomatik,
  ishlamay qolsa o'zi qayta tiklanadigan qilib o'rnatish uchun:
        install_agent.bat   (administrator sifatida ishga tushiriladi)
  Boshqarish:
        stop_agent.bat      — to'xtatish (faqat shu buyruq bilan to'xtaydi)
        start_agent.bat     — qayta ishga tushirish
        status_agent.bat    — holat va oxirgi loglarni ko'rish
        uninstall_agent.bat — butunlay olib tashlash

QO'LDA / SOZLASH UCHUN (konsol rejimi, ekranga chiqaradi):
        python xprinter_agent.py

O'RNATISH (kassa kompyuterida, bir marta):
  1. Python 3 o'rnating (python.org — "Add Python to PATH" ni belgilang).
  2. Buyruq qatorida:  pip install websockets
  3. RID va TOKEN ni `agent_config.json` faylida ko'rsating (pastga qarang),
     keyin install_agent.bat ni administrator sifatida ishga tushiring.

SOZLAMALAR (administratordan oling):
  - RID   : restoran ID (Muhsina Somsa = 1)
  - TOKEN : POS_BRIDGE_TOKEN (printer-token — server administratoridan)

Printer IP/port admin paneldagi sozlamadan keladi (har chek bilan birga), shuning
uchun bu yerda printer IP yozish shart emas.
"""
import asyncio
import base64
import json
import logging
import os
import socket
import sys
from logging.handlers import RotatingFileHandler

# ── STANDART SOZLAMALAR ───────────────────────────────────────────────────
# Bularni shu yerda to'ldirishingiz YOKI (afzalroq) shu papkadagi
# `agent_config.json` faylida ko'rsatishingiz mumkin. JSON ustun keladi:
#       { "rid": 1, "token": "POS-BRIDGE-TOKEN" }
# Atrof-muhit (env) o'zgaruvchilari ham qo'llab-quvvatlanadi:
#       MEZBON_RID, MEZBON_TOKEN, MEZBON_SERVER
RID = 1                                   # restoran ID (Muhsina Somsa = 1)
TOKEN = "PUT-POS-BRIDGE-TOKEN-HERE"       # POS_BRIDGE_TOKEN (administratordan)
SERVER_BASE = "wss://api.tursunboyev.com"  # server manzili (sxema + host)
DEFAULT_PORT = 9100
# ─────────────────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_config():
    """agent_config.json / env bo'lsa RID, TOKEN, SERVER'ni undan oladi."""
    rid, token, base = RID, TOKEN, SERVER_BASE
    cfg_path = os.path.join(SCRIPT_DIR, "agent_config.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            rid = cfg.get("rid", rid)
            token = cfg.get("token", token)
            base = cfg.get("server_ws") or cfg.get("server_base") or base
        except Exception:
            pass  # buzilgan config — standart qiymatlarga qaytamiz
    rid = int(os.getenv("MEZBON_RID", rid))
    token = os.getenv("MEZBON_TOKEN", token)
    base = os.getenv("MEZBON_SERVER", base)
    return rid, token, base.rstrip("/")


def _setup_logging():
    """Fayl-log o'rnatadi (orqa fon rejimida ekran yo'q). Konsol bo'lsa unga ham yozadi."""
    base_dir = os.environ.get("PROGRAMDATA") or SCRIPT_DIR
    log_dir = os.path.join(base_dir, "MezbonPrinter")
    try:
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "agent.log")
    except Exception:
        log_path = os.path.join(SCRIPT_DIR, "agent.log")

    logger = logging.getLogger("mezbon_printer")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(message)s", "%Y-%m-%d %H:%M:%S")
    try:
        fh = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass  # fayl ochilmasa ham agent ishlayversin
    if sys.stdout is not None:  # konsol rejimida ekranda ham ko'rsatamiz
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger, log_path


RID, TOKEN, SERVER_BASE = _load_config()
SERVER_WS = f"{SERVER_BASE}/pos/bridge/{RID}?token={TOKEN}"
log, LOG_PATH = _setup_logging()

try:
    import websockets
except ImportError:
    raise SystemExit("Avval o'rnating:  pip install websockets")


def send_to_printer(ip: str, port: int, data: bytes) -> None:
    """ESC/POS bytes'ni printer IP:port ga TCP orqali yuborish."""
    with socket.create_connection((ip, port), timeout=8) as s:
        s.sendall(data)


async def handle(msg: dict) -> None:
    mtype = msg.get("type")
    if mtype == "print_escpos_tcp":
        ip = msg.get("printer_ip")
        port = int(msg.get("printer_port") or DEFAULT_PORT)
        data = base64.b64decode(msg.get("escpos_b64") or "")
        if not ip or not data:
            log.warning("[!] IP yoki ma'lumot yo'q, o'tkazib yuborildi")
            return
        try:
            send_to_printer(ip, port, data)
            log.info(f"[OK] Chek chiqdi -> {ip}:{port} ({len(data)} bayt), order #{msg.get('order_id')}")
        except Exception as e:
            log.error(f"[XATO] Printerga ulanib bo'lmadi {ip}:{port} — {e}")
    elif mtype == "print_escpos":
        # Bluetooth varianti — bu agent faqat LAN'ni qo'llab-quvvatlaydi
        log.info("[i] print_escpos (Bluetooth) — bu agent LAN uchun, o'tkazib yuborildi")
    else:
        log.info(f"[i] Signal: {mtype}")


async def main() -> None:
    log.info(f"Agent ishga tushdi. Log fayli: {LOG_PATH}")
    log.info(f"Ulanmoqda: {SERVER_WS.split('?')[0]} (RID={RID}) ...")
    while True:
        try:
            async with websockets.connect(SERVER_WS, ping_interval=20) as ws:
                log.info("[OK] Serverga ulandi. Cheklarni kutyapman...")
                async for raw in ws:
                    try:
                        await handle(json.loads(raw))
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            log.warning(f"[!] Ulanish uzildi: {e} — 5s dan keyin qayta urinaman")
            await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Agent to'xtatildi (Ctrl+C).")
