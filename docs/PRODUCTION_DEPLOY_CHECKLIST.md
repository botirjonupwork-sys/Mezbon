# 🚀 Production Deploy Checklist

**Maqsad:** staging'dagi barcha o'zgarishlarni `/opt/restaurant/` ga xavfsiz ko'chirish.

---

## 📋 1. `.env` AUDIT (production server'da)

`/opt/restaurant/.env` faylga **yetishmayotgan** kalitlar:

### 🔴 KRITIK (deploy oldidan to'ldirish shart)

```bash
# Telegram Native Payments — BotFather'dan olingan token
# Format: <id>:TEST:<key> (sandbox) yoki <id>:LIVE:<key> (real)
TELEGRAM_PROVIDER_TOKEN_CLICK=
TELEGRAM_PROVIDER_TOKEN_PAYME=

# Scheduler — 4 ta cron job (subscription, auto-cancel, anomaly, monthly)
ENABLE_SCHEDULER=1

# Auto-cancel timeout (daqiqa) — to'lanmagan buyurtmalarni o'chirish
STALE_ORDER_MINUTES=30
```

### 🟠 KUCHLI tavsiya (alertlar uchun)

```bash
# Platforma admin uchun alohida bot token (BotFather'dan yangi bot yarating)
# Asosiy BOT_TOKEN bilan to'qnashmaslik uchun alohida
ALERT_BOT_TOKEN=

# Telegram chat/group ID (@username yoki -1001234567890 numeric)
# Anomaliya, daily summary, refund alertlar shu chatga keladi
ALERT_CHAT_ID=

# Click LIVE merchant (shartnoma tuzilganidan keyin)
CLICK_ALLOWED_IPS=185.232.66.0/24,...   # vergul bilan ajratilgan
```

### 🟡 KEYINCHALIK (LIVE'ga o'tganda)

```bash
# Soliq qo'mitasi rasmiy INN API kalit
SOLIQ_API_KEY=

# Yandex Delivery (agar ulanadigan bo'lsa)
YANDEX_DELIVERY_TOKEN=

# OpenAI (AI Operator faqat Pro tarifda)
OPENAI_API_KEY=
```

---

## 🤖 2. ALERT_BOT_TOKEN qanday olinadi

1. **Telegram'da @BotFather'ni oching**
2. `/newbot` → bot nomini kiriting (masalan, "Muhsina Alert")
3. `/setname` va `/setdescription` (ixtiyoriy)
4. Berilgan token: `123456:ABC...` — `.env` ga `ALERT_BOT_TOKEN=` ga yozing

5. **Chat ID olish:**
   - Yangi bot bilan suhbat boshlash (private) yoki guruhga qo'shish
   - Browser'da: `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - JSON ichida `"chat":{"id":123456789, ...}` ko'rasiz
   - Shu raqamni `ALERT_CHAT_ID=` ga yozing

6. **Sinash:**
   ```bash
   curl -X POST "https://api.telegram.org/bot<TOKEN>/sendMessage" \
     -d "chat_id=<CHAT_ID>&text=Test alert"
   ```

---

## 🗄 3. Database migratsiyasi (production'da)

Staging'da 3 ta yangi migratsiya bor:
- `a1b2c3d4e5f6` — Faza 1.4 (payment_test_mode + telegram tokenlari)
- `b2c3d4e5f6a7` — Faza 3 (refunds jadvali)
- `c3d4e5f6a7b8` — Faza 6 (VAT, fiscal QR, terms_accepted_at)
- `d4e5f6a7b8c9` — Faza 8 (enforce_prepayment_for_delivery)

**Deploy oldidan production'da:**

```bash
ssh root@65.109.5.207
cd /opt/restaurant

# 1. Backup
./scripts/backup_db.sh

# 2. Hozirgi versiya
.venv/bin/alembic current

# 3. Yangi versiyalar (kutiladi)
.venv/bin/alembic heads

# 4. Migratsiya
.venv/bin/alembic upgrade head

# 5. Tekshirish
.venv/bin/alembic current
```

---

## 📦 4. Kod deploy

```bash
# Lokaldan staging fayllar prod'ga ko'chirish
# (yoki git pull origin main, agar git push qilingan bo'lsa)

scp /Users/nazir/Desktop/MuhsinaDollar/database/models.py root@65.109.5.207:/opt/restaurant/database/
scp -r /Users/nazir/Desktop/MuhsinaDollar/database/migrations/versions/2026* root@65.109.5.207:/opt/restaurant/database/migrations/versions/
scp -r /Users/nazir/Desktop/MuhsinaDollar/api/services/* root@65.109.5.207:/opt/restaurant/api/services/
scp -r /Users/nazir/Desktop/MuhsinaDollar/api/routes/* root@65.109.5.207:/opt/restaurant/api/routes/
scp /Users/nazir/Desktop/MuhsinaDollar/api/main.py root@65.109.5.207:/opt/restaurant/api/
scp /Users/nazir/Desktop/MuhsinaDollar/api/schemas.py root@65.109.5.207:/opt/restaurant/api/
scp -r /Users/nazir/Desktop/MuhsinaDollar/bot/* root@65.109.5.207:/opt/restaurant/bot/
scp /Users/nazir/Desktop/MuhsinaDollar/scripts/reconciliation.py root@65.109.5.207:/opt/restaurant/scripts/
scp -r /Users/nazir/Desktop/MuhsinaDollar/docs/legal root@65.109.5.207:/opt/restaurant/docs/

# Frontend
cd /Users/nazir/Desktop/MuhsinaDollar/admin && npx vite build --base=/admin/
rsync -az --delete dist/ root@65.109.5.207:/opt/restaurant/admin/dist/

cd /Users/nazir/Desktop/MuhsinaDollar/super_admin && npx vite build --base=/super/
rsync -az --delete dist/ root@65.109.5.207:/opt/restaurant/super_admin/dist/

# Service restart
ssh root@65.109.5.207 "systemctl restart restaurant-api restaurant-bots"
```

---

## ✅ 5. Smoke testlar (deploy'dan keyin)

```bash
# 1. API jonli
curl https://api.tursunboyev.com/health

# 2. Migratsiya o'tdi
ssh root@65.109.5.207 "cd /opt/restaurant && .venv/bin/alembic current"
# Kutiladi: d4e5f6a7b8c9 (head)

# 3. Token yuklandi
ssh root@65.109.5.207 "systemctl show restaurant-api -p Environment | grep TOKEN"

# 4. Scheduler ishlayapti
ssh root@65.109.5.207 "tail -5 /opt/restaurant/api.log | grep Scheduler"

# 5. Bot Telegram'ga ulangan
ssh root@65.109.5.207 "tail -5 /opt/restaurant/bots.log"

# 6. Settings UI yangi maydonlar
# Browserda admin.tursunboyev.com → Settings → To'lov tab
# Tekshirish kerak: VAT toggle, Telegram tokenlar, prepayment-for-delivery
```

---

## 🔄 6. Rollback strategiyasi

Agar deploy noto'g'ri ketsa:

```bash
# 1. DB rollback (oxirgi backup'dan)
ssh root@65.109.5.207
cd /opt/restaurant
ls -lh backups/   # eng yangi backup'ni topish
gunzip -c backups/sqlite_LATEST.db.gz > muhsina_somsa.db.restored
mv muhsina_somsa.db muhsina_somsa.db.failed
mv muhsina_somsa.db.restored muhsina_somsa.db

# 2. Migration downgrade
.venv/bin/alembic downgrade -1   # bitta versiya orqaga
# yoki:
.venv/bin/alembic downgrade <prev_revision>

# 3. Kodni eski versiyaga qaytarish (git checkout yoki backup)

# 4. Service restart
systemctl restart restaurant-api restaurant-bots
```

---

## 🚨 7. Production cron'lar (qo'shildi 2026-05-01)

```bash
# Backup har kuni 03:00
0 3 * * * cd /opt/restaurant && ./scripts/backup_db.sh >> logs/backup.log 2>&1

# Reconciliation har kuni 04:00 UTC (09:00 Tashkent)
0 4 * * * cd /opt/restaurant && .venv/bin/python -m scripts.reconciliation --days 7 >> logs/reconciliation.log 2>&1
```

Tekshirish: `crontab -l`

---

## 📊 8. Monitoring deploy'dan keyin

- **`/super-admin/analytics/payments`** — payment metrics
- **`/super-admin/monitoring/webhooks`** — webhook latency
- **`/super-admin/finance/summary`** — daromad
- Telegram: `ALERT_CHAT_ID` chatda anomaliya alertlari (har 15 daq tekshiriladi)
- Loglar: `/opt/restaurant/logs/critical.log` (xatolar)
