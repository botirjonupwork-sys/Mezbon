# Muhsina Dollar Somsa — To'liq Texnik Topshiriq (TZ)

> Multi-tenant SaaS platform: O'zbekistondagi restoranlar uchun Telegram bot + admin panel + AI operator + POS integratsiya. Bitta kod bazasi, bir nechta restoranga xizmat qiladi.

**Holat (2026-04-30):**
- Backend va ikki frontend ishlab chiqilgan, lokal va **staging** muhitda ishlamoqda
- Production qisman ishlamoqda (legacy versiya), yangi xususiyatlar staging'dan promote qilinishi kerak
- Texnologiyalar: Python 3.12, FastAPI, SQLAlchemy async, React 18, AntD 5, aiogram 3, OpenAI

---

## 1. Biznes konteksti

**Foydalanuvchi**: O'zbekistondagi restoranlar (kichik-o'rta — somsa, choyxona, fast-food). Birinchi mijoz: **"Muhsina Dollar Somsa"**.

**Maqsad**: Restoranni "online" ga olib chiqish (Telegram bot orqali buyurtma qabul qilish, fiskallashtirish, dastavka), bir necha restoran bitta platformada SaaS modeli orqali xizmat qabul qiladi.

**Tarif modeli**:
- **Free**: 1 ta bot, 100 ta zakaz/oy
- **Basic**: cheksiz zakaz, Catering qo'shilgan
- **Pro**: hamma narsa + AI Operator + Yandex Delivery

**Daromad oqimi**:
- Oylik tarif to'lovi (Click/Payme)
- Komissiya % (har zakazdan, sozlanadigan, super-admin tomonidan)

---

## 2. Arxitektura

```
                              CloudFlare DNS
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         │                         │                         │
   restaurant.* /              super.* /              test-*. /
   (admin React)            (super_admin React)   (staging variantlar)
         │                         │                         │
         └────────── nginx (Hetzner 65.109.5.207) ──────────┘
                                   │
                         ┌─────────┴─────────┐
                         │ FastAPI uvicorn   │ ← /opt/restaurant/  (prod, port 8086)
                         │ + WebSocket bridge│ ← /opt/restaurant-staging/ (port 8087)
                         └─────────┬─────────┘
                                   │
            ┌──────────────────────┼──────────────────────┐
            │                      │                      │
       SQLite                  Telegram bots         Tashqi xizmatlar
   muhsina_somsa.db          (aiogram 3, FSM)        - OpenAI
   (target: Postgres)         - bot.main             - Click webhook
                              - courier_bot          - Payme JSON-RPC
                              - catering_bot         - Yandex B2B Cargo
                                                     - NeonAlisa Cloud
                                                     - CBU (currency)
```

### Asosiy komponentlar

| Component | Path | Texnologiya |
|---|---|---|
| API | `api/` | FastAPI 0.111, SQLAlchemy 2.0 async |
| Restaurant admin panel | `admin/` | React 18, Vite, AntD 5, zustand |
| Super-admin panel | `super_admin/` | React 18, Vite, AntD 5, @ant-design/charts |
| Telegram mijoz bot | `bot/` | aiogram 3.7 |
| Kuryer bot | `courier_bot/` | aiogram 3.7 |
| Catering bot | `catering_bot/` | aiogram 3.7 |
| DB modellari | `database/models.py` | SQLAlchemy declarative |
| Migratsiya | `database/migrations/` | Alembic 1.13 |
| Web App (mijoz UI) | `webapp/` | (PWA, hozircha yarim) |

---

## 3. Foydalanuvchi rollari va auth

### 3.1 Rollar

| Rol | Login | Qayerda kiradi | Token formati |
|---|---|---|---|
| Super admin | `superadmin` / `SuperAdmin2024!` (yoki .env'dagi `admin`/`admin123`) | super.* va admin.* | HMAC-SHA256 + `exp` (1 soat TTL) |
| Restaurant admin | restoran o'z admin user/pass'i (Restaurant.admin_username) | restaurant.* | `<SECRET_KEY>:<rid>` (statik) |
| Sub-admin | Admins jadvalida | restaurant.* | `<SECRET_KEY>:<rid>` |
| Customer | Telegram bot | bot orqali | telegram_id |
| Kuryer | Telegram bot | courier_bot orqali | telegram_id |
| AI agent customer | telefon raqami (Vapi/Retell) | API | `phone:+998...` (telegram_id) |

### 3.2 Auth tafsilotlari

- **Super admin token (`api/routes/auth.py:33`)**: `make_super_token()` payload `{u, exp, is_super}` ni base64-url + HMAC-SHA256 imzo. Default TTL 1 soat (`SUPER_TOKEN_TTL_SECONDS`).
- **Restaurant admin token**: hozir statik `SECRET_KEY:rid` formatida (TODO: JWT bilan almashtirish).
- **Backward compat**: legacy super-admin uchun bare `SECRET_KEY` ham qabul qilinadi (`api/auth_deps.py`).

---

## 4. Database sxemasi

**Drayver**: SQLite + aiosqlite (lokal/prod), PostgreSQL + asyncpg (target).

### 4.1 17 ta jadval

```
restaurants            ← Multi-tenant root (55 ustun)
  ├─ branches           Filiallar
  ├─ admins             Restoran ichidagi sub-adminlar
  ├─ products           Menyu (regular + catering tipida)
  ├─ categories         Menyu kategoriyalari
  ├─ orders             Buyurtmalar (regular + catering)
  │   └─ order_items
  ├─ couriers
  ├─ reviews
  ├─ catering_subscribers   Catering bot subscriberlar
  └─ commission_payments    Komissiya to'lovlari

users                  ← Mijoz (telegram_id orqali, restoranga emas, butun platformaga)
  └─ addresses

plans                  ← SaaS tariflar (free/basic/pro)
payments               ← Tarif to'lovlari (Click/Payme, amount_tiyin int)
super_admin_actions    ← Audit log
```

### 4.2 `restaurants` muhim ustunlari

```python
# Identity
id, name, slug, logo_url, address, phone

# Bot tokens
bot_token, courier_bot_token

# Admin auth
admin_username, admin_password_hash (sha256)

# Ish jadvali
work_hours_from, work_hours_until, min_order
restaurant_lat, restaurant_lon

# SaaS tarif
plan (legacy slug), plan_id (FK→plans),  plan_expires_at
status ('active' | 'blocked' | 'trial')
commission_percent

# Dastavka
delivery_provider ('own' | 'yandex' | 'customer_choice')
delivery_base_fee, delivery_per_km
yandex_api_token, yandex_test_mode

# Catering
currency_auto, currency_rate_manual, currency_rate_cache
catering_payment_card, catering_somsa_min, catering_nan_min, ...
catering_delivery_per_km_uzs

# To'lov gateway
click_merchant_id, click_service_id, click_secret_key, click_enabled
payme_merchant_id, payme_secret_key, payme_enabled

# AI Call Operator (Pro tarif)
ai_agent_enabled, ai_agent_prompt, ai_agent_voice
ai_agent_provider, ai_agent_model, ai_agent_api_key

# POS Hybrid Connect
pos_system_type ('NONE' | 'NEONALISA' | 'GENERIC_ANDROID' | 'BLUETOOTH_PRINTER')
pos_config (JSON: {api_key, merchant_id, terminal_ip, printer_mac, ...})
```

### 4.3 Pul birliklari

- `Order.total_price`, `delivery_fee`: **Float UZS** (legacy)
- `Payment.amount_tiyin`: **int** — 1 so'm = 100 tiyin (float xatolardan qochish)
- `Plan.monthly_price`, `commission_percent`: Float

### 4.4 Alembic migratsiyalar (3 ta head'da)

1. `2275d52643cd_initial_schema.py` — to'liq schema
2. `3b969d8e6afd_add_super_admin_actions.py` — audit log jadvali
3. `d420ebe024d7_add_pos_system_fields_to_restaurant.py` — POS

Production'da DB allaqachon mavjud — `scripts/sync_schema.py` idempotent ALTER + `alembic stamp head` orqali muvofiqlashtirildi.

---

## 5. API surface (FastAPI routerlar)

`api/main.py`'da ulangan 16 ta router. Auth har birida tegishli `Depends`.

### 5.1 Public / customer
```
POST  /auth/login                  Restaurant admin login
POST  /auth/super/login            Super admin login (qisqa muddatli token)
POST  /auth/bot-login              Bot orqali identity (token bilan)

POST  /users/                      Customer create/get
GET   /users/{telegram_id}
POST  /users/{telegram_id}/branch  Branch select
GET   /users/{tg}/addresses
POST  /users/{tg}/addresses

GET   /menu/categories             Restaurant menyu (bot uchun)
GET   /menu/products
GET   /restaurants/{rid}/info      Public info

POST  /orders/                     Customer zakaz
GET   /orders/user/{tg}
PATCH /orders/{id}/status          Admin (status update + POS dispatch)

GET   /reviews                     Reviews (paginated)
GET   /reviews/stats

GET   /catering/products
POST  /catering/orders             Catering buyurtma
GET   /catering/currency           CBU + cache
```

### 5.2 Restaurant admin (`require_restaurant_admin`)
```
GET   /admin/stats                 Statistika (orders, revenue, users, ratings)
GET   /admin/orders                Zakazlar (filter: status, date, branch, kind)
GET   /admin/products              Menyu mahsulotlari
POST  /admin/products
PUT   /admin/products/{id}
DELETE /admin/products/{id}
GET/POST/PUT/DELETE /admin/categories
GET   /admin/users                 Mijozlar (faqat shu restoranga zakaz bergan)
GET   /admin/users/{id}/orders

GET   /admin/settings              Restoran sozlamalari (55 maydon)
PUT   /admin/settings
GET   /admin/profile
PUT   /admin/profile
GET   /admin/me/plan               Joriy tarif + features

GET/POST/DELETE /admin/admins      Sub-admin boshqaruvi
GET/POST/PUT/DELETE /couriers/...

POST  /admin/upload-image          Path-traversal himoya bilan
DELETE /admin/upload-image

GET   /admin/billing/plans         Tariflar + joriy tarif
GET   /admin/billing/payments      To'lov tarixi
POST  /payments/create-invoice     Click/Payme uchun faktura
POST  /payments/click/webhook      Click PREPARE/COMPLETE (IP+sign)
POST  /payments/payme/webhook      Payme JSON-RPC (5 method, Basic auth)

GET   /admin/branches              Filiallar
PUT   /admin/branches/{id}/settings

GET/PUT /admin/pos/config          POS Hybrid Connect
POST  /admin/pos/test-print        "Salom Dunyo" testi
WS    /pos/bridge/{rid}            Android/agent ulanadi (token bilan)

POST  /ai/process-call             AI Call Agent (Vapi/Retell webhook)
POST  /ai/end-call
```

### 5.3 Super admin (`require_superuser`)
```
GET   /super-admin/stats           Platform stats + kunlik series
GET   /super-admin/restaurants     Barcha restoranlar (revenue, plan, status)
PATCH /super-admin/restaurants/{id}  Status/plan/extend_days/komissiya
GET/PUT /super-admin/maintenance   Maintenance Mode
GET   /super-admin/actions         Audit log

# Legacy compatibility (eski super_admin frontend uchun)
GET/POST/PUT/DELETE /super/plans   Tariflar CRUD
GET/PUT /super/profile             Super-admin profile
GET/PUT /super/platform-settings   Brendlash + global default'lar
GET/POST/PUT/DELETE /super/restaurants/{rid}/branches
GET/POST /super/bots/* (stub)
```

### 5.4 Health / system
```
GET   /health                      DB ping + OpenAI ping + Yandex ping + Tashkent vaqti
```

### 5.5 Maintenance Mode middleware

`api/main.py:maintenance_guard` — `platform.is_maintenance()` True bo'lsa 503 qaytaradi. **Allow-list**: `/super-admin/*`, `/auth/super/login`, `/auth/login`, `/health`, `/static/*`, `/docs`.

---

## 6. Modullar tafsiloti

### 6.1 Multi-tenant tizim
- Har **`Restaurant`** o'z menyusi, filiali, adminlari, botlarini boshqaradi
- Token formatida `restaurant_id` kodlangan (`SECRET_KEY:rid`) — backend `_parse_token` aniqlaydi
- IDOR himoyasi: `require_restaurant_admin` query'dagi `restaurant_id` token bilan mos kelishini tekshiradi

### 6.2 Plan feature gating

`api/auth_deps.py:require_plan_feature("catering" | "ai_agent" | "yandex")` factory. Tarif boolean flag'lariga bog'liq: `Plan.has_catering`, `has_ai_agent`, `has_yandex`. Super admin har doim ruxsat oladi (testlash).

### 6.3 Telegram botlar (3 ta)

**Mijoz bot (`bot/`)**: FSM bilan, language picker (uz/ru), branch select, menyu, savat, manzil (location), to'lov, status notification.

**Kuryer bot (`courier_bot/`)**: yangi zakaz xabari, qabul/rad inline tugmalar, location yuborish.

**Catering bot (`catering_bot/`)**: tadbir buyurtmalari (≥100 somsa, alohida narxlash USD/UZS, har kuni 20:00 da subscriberlarga ertangi kun zakazlari).

Bot api_client (`bot/api_client.py`) → REST API'ga so'rov yuboradi (token: `SECRET_KEY:rid`).

### 6.4 SaaS Billing

**Tariflar** (3 ta default): Free / Basic / Pro. Frontend (super_admin/Tariffs.jsx)'da CRUD.

**Click integratsiyasi (`api/services/billing.py`)**:
- MD5 signature: `click_signature(...)`
- IP allow-list: `is_click_ip_allowed()`
- 2 ta action: `PREPARE` (action=0) va `COMPLETE` (action=1)
- Mock mode: kalit yo'q bo'lsa `https://mock.payments.local/...` URL qaytariladi

**Payme integratsiyasi**: 5 ta JSON-RPC method (CheckPerformTransaction, CreateTransaction, PerformTransaction, CancelTransaction, CheckTransaction), Basic Auth.

**Plan extension**: To'lov muvaffaqiyatli bo'lsa `plan_expires_at = max(now, current) + 30 days` (cumulative).

### 6.5 AI Call Operator

`api/services/ai_agent.py`:
- OpenAI `gpt-4o-mini` (default), function calling bilan
- 7 ta tool: `add_to_cart`, `remove_from_cart`, `clear_cart`, `view_cart`, `set_address`, `confirm_order`, `transfer_to_catering`
- System prompt har turn'da menyu, ish vaqti, min_order'ni inject qiladi
- **Catering aniqlash**: 100+ somsa yoki 40+ non → `is_catering_cart()` True → catering kanaliga yo'naltirish
- Sessiya in-memory (TTL 30 daq). `phone:+998...` ko'rinishida `User` yaratiladi.
- Vapi/Retell/o'z gateway → `POST /ai/process-call` orqali transcript yuboradi

### 6.6 Yandex Delivery

`api/services/yandex_delivery.py`:
- B2B Cargo API
- OAuth token (test/prod mode)
- `claim` yaratish, status tracking, tracking URL

### 6.7 Catering

`api/routes/catering.py`:
- Mahsulotlar `product_type='catering'` bilan belgilangan
- USD/UZS valyuta o'tkazish (CBU API yoki qo'lda)
- Onsite / pickup / delivery 3 turi
- Har kuni 20:00 da scheduler ertangi kun catering zakazlarini subscriberlarga yuboradi

### 6.8 POS Hybrid Connect

`api/services/pos_adapter.py`:
- **UniversalOrder schema** (POS-agnostic)
- 4 ta drayver:
  - `NoneDriver` — no-op
  - `NeonAlisaDriver` — Cloud API + fiskal flag
  - `GenericAndroidDriver` — WebSocket bridge orqali Android tablet'ga signal
  - `BluetoothPrinterDriver` — ESC/POS bytes generatsiya + agent ilovaga base64
- `WebSocketBridge` — `restaurant_id` bo'yicha guruhlangan ulangan terminal'lar
- Order `confirmed` bo'lsa `pos_adapter.dispatch_order()` background task (asosiy oqimni bloklamaydi)
- ESC/POS generator: 58/80 mm chek printer uchun raw bytes

### 6.9 Super-admin paneli

`super_admin/` (port 3001 dev, super.tursunboyev.com prod):
- **Dashboard**: 4 ta stat kartochka, Health widget, Line chart (30 kun), Pie chart (tarif taqsimoti)
- **Restoranlar**: jadval, "Tahrir" modal — status/plan/extend_days/komissiya
- **Tariflar**: CRUD + features array tag editor
- **Bots**: status (hozircha stub)
- **Global sozlamalar**: Maintenance Mode toggle (tasdiq modal), Audit log (100 ta yozuv, JSON details)
- **Sozlamalar**: profil va platform brending

### 6.10 Restaurant admin paneli

`admin/` (port 3000 dev, restaurant.tursunboyev.com prod):
- **Dashboard**: stats + 30 kun chart
- **Zakazlar**: ovozli notification, filter, status update modal
- **Menyu**: mahsulot CRUD + rasm yuklash + catering bo'limi
- **Mijozlar**: jadval, qator bosilsa modal'da zakazlar tarixi (yangi rewrite)
- **Baholar**: rating + comment list
- **Kuryerlar**: telegram_id, status (active/pending/blocked)
- **Adminlar**: sub-admin CRUD (super-only)
- **Tariflar**: Click/Payme to'lov sahifasi
- **Sozlamalar**: 8 ta tab (Restoran, Ish vaqti, Dastavka, To'lov, Catering, AI Operator, POS, Til)
- **Super-admin uchun**: top sider'da "🏪 Restoran tanlang" dropdown — boshqa restoranni ko'rish/sozlash

### 6.11 Logging va alerts

`api/logging_config.py`:
- 3 ta handler: console, `logs/api.log` (10MB rotated), `logs/critical.log` (faqat ERROR+)
- `log_critical(category, message, **context)` — JSON formatida ctx
- Telegram alert (`api/services/alerts.py`): `ALERT_BOT_TOKEN` + `ALERT_CHAT_ID` env'da bo'lsa, dedup bilan (5 daq) HTML xabar
- Avtomatik chaqiriladi: payment webhook xato, AI OpenAI fail, POS not_configured, DB ping fail

### 6.12 Backup

`scripts/backup_db.sh`:
- SQLite → online `sqlite3 .backup` + gzip
- Postgres → `pg_dump --no-owner --no-acl --clean --if-exists` + gzip
- 30 kunlik retention
- Cron: `0 3 * * * cd /opt/restaurant && ./scripts/backup_db.sh >> logs/backup.log 2>&1`

---

## 7. Deployment

### 7.1 Server

- **Hetzner**: 65.109.5.207 (`ubuntu-16gb-hel1-4`), Ubuntu
- SSH: root key-based
- nginx + Certbot (Let's Encrypt)
- systemd unitlar yo'q — uvicorn nohup orqali ishlaydi

### 7.2 Domenlar (Cloudflare DNS, "DNS only" — proxy yo'q)

| Domain | Ishlatilishi |
|---|---|
| `restaurant.tursunboyev.com` | **Prod** restaurant admin |
| `super.tursunboyev.com` | **Prod** super admin |
| `test-restaurant.tursunboyev.com` | **Staging** restaurant admin |
| `test-super.tursunboyev.com` | **Staging** super admin |
| `api.tursunboyev.com` | (boshqa loyiha — ombor) |
| `app.tursunboyev.com` | (mijoz PWA, hozircha bo'sh) |

### 7.3 Server papkalari

```
/opt/restaurant/             ← Prod (port 8086, 2 worker)
  ├─ muhsina_somsa.db        ← SQLite (≈100KB)
  ├─ admin/dist/             ← Built admin
  ├─ super_admin/dist/       ← Built super_admin
  ├─ static/images/products/ ← Mahsulot rasmlari
  └─ .venv/

/opt/restaurant-staging/     ← Staging (port 8087, 1 worker)
  ├─ muhsina_staging.db      ← Prod DB nusxasi
  └─ ...
```

### 7.4 Nginx sites

- `restaurant` (prod) — `/admin/`, `/super/`, `/api/` → 8086
- `super` (prod, hali qurilmagan) — root → super_admin/dist, /api/ → 8086
- `test-restaurant` — root → staging admin/dist, /api/ → 8087, WebSocket upgrade enabled
- `test-super` — root → staging super_admin/dist, /api/ → 8087

### 7.5 Frontend env

```
admin/.env                # VITE_API_TARGET=https://restaurant.tursunboyev.com (prod build)
admin/.env.development    # VITE_API_TARGET=http://localhost:8000
admin/.env.production     # (server'da generatsiya qilinadi: VITE_API_URL=https://test-restaurant.../api)
```

Vite proxy `/api/*` → backend (rewrite bilan `/api` strip qilinadi).

### 7.6 Deploy.sh

`./deploy.sh` (lokal yoki server'da):
1. `git pull --ff-only`
2. `pip install -r requirements.txt`
3. `alembic upgrade head` + `alembic current` (sanity)
4. Admin/super_admin build (`npm install` + `npm run build`)
5. systemd unit'lar bo'lsa `systemctl restart` (yo'qsa qo'lda)

Bayroqlar: `--skip-build`, `--no-restart`.

---

## 8. Xavfsizlik

### 8.1 Mavjud himoya

- ✅ CORS: faqat `restaurant/super.tursunboyev.com` + dev portlar (env `CORS_EXTRA_ORIGINS`)
- ✅ Rate limiting: SlowAPI, default 300/min, login 5/min
- ✅ IDOR himoyasi: token'dagi `rid` query param bilan solishtiriladi
- ✅ Path traversal: rasm fayllar UUID format + abspath check
- ✅ Click webhook: MD5 signature + IP allow-list
- ✅ Payme webhook: Basic Auth (merchant_id:key)
- ✅ Super-admin: HMAC + exp 1 soat TTL
- ✅ Audit log: o'chirib bo'lmaydi, har mutatsiya yozuvga kiradi
- ✅ Maintenance mode: super-admin tashqari hammasi 503

### 8.2 To'liqlanmagan / TODO

- ⚠️ Restaurant admin token statik (`SECRET_KEY:rid`) — JWT'ga o'tish kerak
- ⚠️ Parol hashing **SHA-256** (zaif) — bcrypt'ga o'tish kerak
- ⚠️ Profil o'zgartirish (super-admin login/parol) `.env` orqali — tablega ko'chirish kerak
- ⚠️ HTTPS-only cookie + CSRF (frontend localStorage'da token) — keyinroq yaxshilash
- ⚠️ Input validatsiya bir nechta endpointlarda yetishmaydi (Pydantic schemas to'liq emas)

---

## 9. Mavjud va ishlamayotgan funksiyalar

### 9.1 To'liq ishlaydi
- ✅ Restoran admin paneli (CRUD, settings, billing, POS sozlash)
- ✅ Super-admin paneli (Dashboard, Restoranlar, Tariflar, Global sozlamalar)
- ✅ 3 ta Telegram bot (mijoz, kuryer, catering)
- ✅ Click/Payme mock to'lov (real keys'siz)
- ✅ AI agent mock mode (OpenAI key bilan ishlaydi)
- ✅ POS adapter (NeonAlisa stub, ESC/POS bytes, WebSocket bridge)
- ✅ Maintenance Mode + Audit log
- ✅ Health check + Telegram alerts (debounced)
- ✅ Backup skripti (SQLite va Postgres)

### 9.2 Yarim qurilgan / kelajakda
- 🟡 Webapp (PWA) — kataloga skelet bor, aslida ishlatilmaydi
- 🟡 super-admin paneldagi `/super/restaurants` — list va PATCH bor, lekin POST (yangi yaratish) va PUT (to'liq tahrir) yo'q. Mavjud `RestaurantForm.jsx` page bor lekin endpoint yo'q.
- 🟡 Bot management UI (start/stop/restart) — backend stub qaytaradi, manual systemd kerak
- 🟡 Commission to'lovlari (`/super/commission/*`) — frontend bor, backend yo'q
- 🟡 Postgres migration — alembic tayyor, lekin haqiqiy migration o'tkazilmagan

### 9.3 Production'ga o'tishdan oldin
- 🔴 Postgres'ga ko'chish (SQLite hozir 100KB, scale qilmaydi)
- 🔴 SECRET_KEY rotation (ikkalasi server'da statik default)
- 🔴 bcrypt password hashing
- 🔴 OpenAI key to'g'ri o'rnatish (hozir `.env`'da yo'q)
- 🔴 Yandex token (haqiqiy account ulashi kerak)
- 🔴 Click + Payme real merchant key'lari
- 🔴 systemd unit'lar (hozir nohup)

---

## 10. Konfiguratsiya (env o'zgaruvchilari)

```bash
# Database
DATABASE_URL=sqlite+aiosqlite:///./muhsina_somsa.db
# yoki: postgresql+asyncpg://user:pass@host:5432/dbname

# Telegram
BOT_TOKEN=...
COURIER_BOT_TOKEN=...

# Auth
SECRET_KEY=<32+ char random>
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
SUPER_ADMIN_USERNAME=superadmin
SUPER_ADMIN_PASSWORD=SuperAdmin2024!

# Tashqi xizmatlar (ixtiyoriy — yo'q bo'lsa modul mock rejimda ishlaydi)
OPENAI_API_KEY=sk-...
YANDEX_DELIVERY_TOKEN=y0_...

# Critical alerts (Telegram)
ALERT_BOT_TOKEN=
ALERT_CHAT_ID=
ALERT_DEDUP_SECONDS=300

# CORS qo'shimcha
CORS_EXTRA_ORIGINS=https://example.com,...

# Click webhook
CLICK_ALLOWED_IPS=  # comma-separated, bo'sh = tekshirilmaydi

# App
DEBUG=False
API_URL=http://localhost:8000
```

---

## 11. Texnik qarorlar (rationale)

| Qaror | Sabab |
|---|---|
| SQLite + aiosqlite (Postgres bo'lmagan) | Birinchi mijozlar oz, prod'da ham 100KB. Scale paytida Postgres'ga o'tishga tayyor. |
| Async SQLAlchemy + FastAPI | Telegram bot va REST API bir vaqtda ishlashi, I/O ko'p (DB + 3rd-party) |
| Money int (tiyin) | Click/Payme tiyin bilan ishlaydi, float xato yo'q |
| Token statik (restaurant admin) | Boshlang'ich versiya, simple. Production'ga JWT bilan migrate qilinadi |
| HMAC token (super-admin) | Kichik kod (no extra dep), 1 soatlik TTL — kerakli xavfsizlik darajasi |
| Maintenance JSON file | Qisqa, atomic, bittagina super yozadi/o'qidi (no race) |
| WebSocket bridge POS uchun | Server Bluetooth/Android'ga ulana olmaydi — agent ilova qiladi, biz signal yuboramiz |
| Two separate React projects | Auth oqimi, theme, rol — alohida domen, alohida bundle (kichikroq), prod'da nginx ham aniq |
| ESC/POS bytes server'da | Klient-side base64'da yetkaziladi (agent qaror oladi) |

---

## 12. Asosiy fayl yo'llari

```
api/
  main.py                       FastAPI app, middlewares, routers
  config.py                     Settings (BaseSettings)
  database.py                   AsyncEngine + SessionLocal
  auth_deps.py                  require_restaurant_admin / require_superuser / require_plan_feature
  logging_config.py             setup_logging + log_critical
  routes/
    auth.py                     login + super_login + token helpers
    users.py + public_router.py
    menu.py
    orders.py                   order CRUD + POS dispatch hook
    admin.py                    settings, products, categories, users (admin view)
    couriers.py
    branches.py
    catering.py
    billing.py
    reviews.py
    health.py
    super_admin.py              /super-admin/* (yangi)
    super_legacy.py             /super/* (eski frontend uchun)
    pos.py                      /admin/pos/* + WS bridge
    ai.py                       /ai/process-call
    superadmin.py               legacy (panel-name, bots JSON file)
  services/
    billing.py                  Click/Payme + create_invoice
    pos_adapter.py              UniversalOrder + 4 driver
    ai_agent.py                 OpenAI function calling
    yandex_delivery.py
    delivery.py                 dispatch_order_to_provider
    currency.py                 CBU API + cache
    alerts.py                   Telegram critical
    platform.py                 platform_settings.json (Maintenance)

database/
  models.py                     17 jadval
  migrations/
    env.py
    versions/*.py               3 ta migration

bot/                            aiogram 3, FSM, handlers, keyboards
courier_bot/                    aiogram 3
catering_bot/                   aiogram 3, scheduler

admin/                          React, Vite
  src/
    api/index.js                axios + 60+ endpoint
    store/{auth,branch}.js      zustand persist
    components/{Layout,POSSettings}.jsx
    pages/                      Dashboard, Orders, Menu, Users, Reviews, Settings, Admins, Couriers, Billing

super_admin/                    React, Vite, charts
  src/
    api/index.js
    store/auth.js
    components/Layout.jsx
    pages/                      Dashboard, Restaurants, Tariffs, Bots, Settings, GlobalSettings, RestaurantForm

scripts/
  backup_db.sh                  Daily DB backup
  sync_schema.py                Idempotent schema sync (alembic stamp head)
  run_all_bots.py               systemd alternative

deploy.sh                       Production deploy

docs/
  TZ.md                         (this file)
  PROJECT_OVERVIEW.md
  TECHNICAL_DOCS.md
  AI_CALL_OPERATOR_PLAN.md
  RESTORAN_HUJJATLARI.md        (Click/Payme/Yandex hujjatlar ro'yxati)
```

---

## 13. Boshqa AI bilan maslahatlashish uchun ochiq savollar

1. **Postgres'ga migration**: SQLite'dan eng xavfsiz ko'chish strategiyasi? `pgloader` vs custom script? Online migration kerakmi (downtime cheklash)?
2. **Bot management**: super-admin paneldan bot start/stop/restart qanday qilish kerak? systemd vs supervisor vs Docker? Real-time log streaming?
3. **JWT migration**: Hozir `SECRET_KEY:rid` static. JWT'ga o'tish refresh-token bilanmi yoki access-only? Cookie-based vs Authorization header?
4. **Multi-region**: Hetzner Helsinki — Tashkent foydalanuvchilarga 90ms latency. Mahalliy serverga (UzPak hosting) o'tish kerakmi yoki edge cache?
5. **AI Operator**: OpenAI orqali Vapi/Retell o'rniga to'g'ridan-to'g'ri Twilio Voice + OpenAI Realtime API ishlatish — narxi-foyda nisbati?
6. **POS protocol**: NeonAlisa Cloud API hujjatlari yopiq. WebSocket bridge'ni ESC/POS oldin Cloud'siz ishlatish (offline rejim) kerakmi?
7. **Catering bot**: 3 ta bot bitta server jarayonida — agar bittasi yiqilsa boshqalari ham yiqiladi. Ajratish kerakmi?
8. **Customer PWA**: Hozir `webapp/` bo'sh. Telegram WebApp (Telegram-only) yoki standalone PWA (xabar, Apple Pay) — qaysi biri?
9. **Rate limiting**: SlowAPI in-memory. Multi-worker'da to'g'ri ishlamaydi (har worker o'z hisoblagichi). Redis'ga o'tish kerakmi?
10. **Image storage**: Hozir `static/images/products/` lokal. S3/R2'ga o'tish (CDN)?

---

## 14. Hozirgi vaziyat (snapshot)

**2026-04-30 holati**:
- Lokal dev: ✅ to'liq ishlaydi
- Staging (`test-*.tursunboyev.com`): ✅ deployed, sinov uchun ochiq
- Production (`restaurant.tursunboyev.com`): hali eski versiya — yangi xususiyatlar (POS, AI, Super-admin, Maintenance) staging'da tasdiq olgandan keyin promote qilinadi
- DB: SQLite 100KB, 2 restoran (Muhsina Dollar, BRN), 23 zakaz, 14.7M so'm umumiy tushum
- Foydalanuvchi sinov bosqichida — bir necha xato topib bildirgan, ular tuzatilmoqda

**Birinchi mijoz**: tursunboyevofficial (botirjonupwork@gmail.com)
