#!/bin/bash
# Muhsina Dollar Somsa — Ishga tushirish skripti

echo "🥟 Muhsina Dollar Somsa ishga tushmoqda..."

# .env mavjudligini tekshirish
if [ ! -f .env ]; then
  echo "❌ .env fayli topilmadi! .env.example dan nusxa oling:"
  echo "   cp .env.example .env"
  exit 1
fi

# Virtual muhit
if [ ! -d .venv ]; then
  echo "📦 Virtual muhit yaratilmoqda..."
  python3 -m venv .venv
fi

source .venv/bin/activate
echo "📦 Kutubxonalar o'rnatilmoqda..."
pip install -q -r requirements.txt

# API va Bot parallel ishga tushirish
echo "🚀 API ishga tushmoqda (port 8000)..."
PYTHON_BIN="$(command -v python || command -v python3)"
# Prefer virtualenv python if present
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
fi

# Start API using module runner to avoid broken shebangs in scripts
$PYTHON_BIN -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload &
API_PID=$!

sleep 2

# Bot menejeri — DB'dagi BARCHA restoran botlarini (customer + courier) boshqaradi.
# Har bir bot alohida subprocess'da; restart super-admin paneldan (bot_reload_at signali).
echo "🤖 Bot menejeri ishga tushmoqda (barcha restoran botlari)..."
# Ensure DB tables exist (create for SQLite) before starting bots
$PYTHON_BIN - <<'PY'
import asyncio
from api.database import create_tables
asyncio.run(create_tables())
PY

$PYTHON_BIN -m bot.manager &
BOT_PID=$!
COURIER_PID=""

echo ""
echo "✅ Hammasi ishga tushdi!"
echo "   API:       http://localhost:8000"
echo "   API Docs:  http://localhost:8000/docs"
echo ""
echo "To'xtatish uchun: Ctrl+C"

trap "kill $API_PID $BOT_PID $COURIER_PID 2>/dev/null; echo '🛑 To\'xtatildi'" SIGINT SIGTERM
wait
