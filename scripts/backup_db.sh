#!/usr/bin/env bash
# Muhsina Dollar Somsa — DB backup skripti.
#
# .env'dagi DATABASE_URL ni o'qiydi, drayverga qarab pg_dump yoki SQLite copy
# bajaradi, gzip qiladi va $BACKUP_DIR ga joylaydi. 30 kundan eski fayllarni
# avtomatik o'chiradi.
#
# Foydalanish:
#   ./scripts/backup_db.sh                # default: $PROJECT/backups
#   BACKUP_DIR=/var/backups/muhsina ./scripts/backup_db.sh
#   RETENTION_DAYS=14 ./scripts/backup_db.sh
#
# Cron (har kuni 03:00):
#   0 3 * * * cd /opt/muhsina && ./scripts/backup_db.sh >> logs/backup.log 2>&1

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

# ── Konfiguratsiya ─────────────────────────────────────
BACKUP_DIR="${BACKUP_DIR:-${PROJECT_ROOT}/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

mkdir -p "$BACKUP_DIR"

log()  { printf '[backup] %s %s\n' "$(date +'%F %T')" "$*"; }
fail() { printf '[backup] %s ERROR: %s\n' "$(date +'%F %T')" "$*" >&2; exit 1; }

# ── .env'dan DATABASE_URL ni o'qish (sodda parser) ────
if [[ ! -f .env ]]; then fail ".env topilmadi"; fi
DB_URL="$(grep -E '^DATABASE_URL=' .env | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
[[ -n "$DB_URL" ]] || fail "DATABASE_URL bo'sh"

# ── SQLite ────────────────────────────────────────────
if [[ "$DB_URL" == sqlite* ]]; then
  # sqlite+aiosqlite:///./muhsina_test.db  →  ./muhsina_test.db
  DB_PATH="${DB_URL#*///}"
  [[ -f "$DB_PATH" ]] || fail "SQLite fayl topilmadi: $DB_PATH"

  OUT="${BACKUP_DIR}/sqlite_${TIMESTAMP}.db.gz"
  log "SQLite backup: $DB_PATH → $OUT"
  # `.backup` Online (lock-free) backup — running API ni to'xtatmaydi
  TMP="$(mktemp).db"
  if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "$DB_PATH" ".backup '$TMP'"
  else
    cp "$DB_PATH" "$TMP"
  fi
  gzip -c "$TMP" > "$OUT"
  rm -f "$TMP"

# ── PostgreSQL ────────────────────────────────────────
elif [[ "$DB_URL" == postgresql* ]]; then
  # postgresql+asyncpg://user:pass@host:5432/dbname  →  postgresql://...
  PG_URL="$(echo "$DB_URL" | sed -E 's#postgresql\+[a-z0-9]+#postgresql#')"

  command -v pg_dump >/dev/null 2>&1 || fail "pg_dump topilmadi (postgresql-client o'rnating)"

  # DB nomini URL'dan ajratamiz (log uchun)
  DB_NAME="$(echo "$PG_URL" | sed -E 's#.*/([^?]+).*#\1#')"
  OUT="${BACKUP_DIR}/pg_${DB_NAME}_${TIMESTAMP}.sql.gz"
  log "Postgres backup: $DB_NAME → $OUT"
  # --no-owner --no-acl — boshqa serverga restore qilishni soddalashtiradi
  pg_dump --no-owner --no-acl --clean --if-exists "$PG_URL" | gzip > "$OUT"

else
  fail "Noma'lum DATABASE_URL drayveri: $DB_URL"
fi

# ── Hajm ──────────────────────────────────────────────
SIZE="$(du -h "$OUT" | cut -f1)"
log "OK: $OUT ($SIZE)"

# ── Eski backuplarni tozalash ────────────────────────
log "Retention: ${RETENTION_DAYS} kundan eski fayllar o'chiriladi"
find "$BACKUP_DIR" -type f \( -name 'sqlite_*.db.gz' -o -name 'pg_*.sql.gz' \) \
  -mtime +"$RETENTION_DAYS" -print -delete | sed 's/^/[backup]   purged: /' || true

log "Tugadi"
