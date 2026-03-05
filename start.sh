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
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload &
API_PID=$!

sleep 2

echo "🤖 Bot ishga tushmoqda..."
python -m bot.main &
BOT_PID=$!

# Kuryer bot (agar token mavjud bo'lsa)
COURIER_PID=""
if [ -n "$COURIER_BOT_TOKEN" ]; then
  echo "🚗 Kuryer bot ishga tushmoqda..."
  python -m courier_bot.main &
  COURIER_PID=$!
fi

echo ""
echo "✅ Hammasi ishga tushdi!"
echo "   API:       http://localhost:8000"
echo "   API Docs:  http://localhost:8000/docs"
echo ""
echo "To'xtatish uchun: Ctrl+C"

trap "kill $API_PID $BOT_PID $COURIER_PID 2>/dev/null; echo '🛑 To\'xtatildi'" SIGINT SIGTERM
wait
