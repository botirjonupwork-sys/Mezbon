#!/usr/bin/env bash
# Muhsina Dollar Somsa — Production deploy skripti.
#
# Bajaradi:
#   1) git pull
#   2) Python virtual env va dependencies (idempotent)
#   3) Alembic migratsiyalarni qo'llash (alembic upgrade head)
#   4) Admin va Super-admin frontend'larni build qilish (npm run build)
#   5) systemd unit'larni qayta ishga tushirish (yoki uvicorn'ni qayta ishga tushirish)
#
# Foydalanish:
#   ./deploy.sh                # to'liq deploy (default)
#   ./deploy.sh --skip-build   # frontend build'ni o'tkazib yuborish
#   ./deploy.sh --no-restart   # servislarni qayta yuklamaslik
#
# Kerak bo'lgan .env muhit:
#   DATABASE_URL  (postgresql+asyncpg://... yoki sqlite+aiosqlite://...)
#   SECRET_KEY, OPENAI_API_KEY, YANDEX_DELIVERY_TOKEN, ...

set -euo pipefail

# ── Argumentlar ─────────────────────────────────────────
SKIP_BUILD=0
NO_RESTART=0
for arg in "$@"; do
  case "$arg" in
    --skip-build) SKIP_BUILD=1 ;;
    --no-restart) NO_RESTART=1 ;;
    -h|--help)
      grep '^# ' "$0" | sed 's/^# \?//'
      exit 0
      ;;
  esac
done

# ── Yo'l-yo'riq ────────────────────────────────────────
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

log() { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# ── 1. Pre-checks ──────────────────────────────────────
[[ -f .env ]] || fail ".env topilmadi (DATABASE_URL kerak)"

# ── 2. Git pull ────────────────────────────────────────
log "git pull"
if [[ -d .git ]]; then
  git fetch --quiet
  git pull --ff-only
fi

# ── 3. Python deps ─────────────────────────────────────
log "Python virtual env"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

# ── 4. Alembic migration ───────────────────────────────
log "Alembic upgrade head"
# Alembic .env'dagi DATABASE_URL'ni env.py orqali o'zi oladi
alembic upgrade head

# Versiya holatini chiqaramiz (sanity)
alembic current

# ── 5. Frontend build ─────────────────────────────────
if [[ "$SKIP_BUILD" -eq 0 ]]; then
  if [[ -d admin && -f admin/package.json ]]; then
    log "Admin frontend build"
    (cd admin && npm install --no-audit --no-fund --silent && npm run build)
  fi
  if [[ -d super-admin && -f super-admin/package.json ]]; then
    log "Super-admin frontend build"
    (cd super-admin && npm install --no-audit --no-fund --silent && npm run build)
  fi
fi

# ── 6. Logs/static papkalari ──────────────────────────
mkdir -p logs static/images/products

# ── 7. Servislarni restart ────────────────────────────
if [[ "$NO_RESTART" -eq 0 ]]; then
  log "Servislarni qayta ishga tushirish"
  if command -v systemctl >/dev/null 2>&1; then
    # Production muhitida systemd unitlari kutilyapti
    for svc in muhsina-api muhsina-bot muhsina-courier muhsina-catering; do
      if systemctl list-unit-files | grep -q "^${svc}\.service"; then
        sudo systemctl restart "$svc" || true
        echo "  ✓ ${svc} restarted"
      fi
    done
  else
    echo "  systemctl topilmadi — servislarni qo'lda yuklang"
  fi
fi

log "Deploy yakunlandi ✅"
