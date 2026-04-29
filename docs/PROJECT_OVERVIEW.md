# Muhsina Dollar Somsa — Project Documentation

> SaaS platform for restaurant food ordering & delivery in Uzbekistan, with Telegram bots as the primary user interface.

This document is intended for **AI agents and developers** evaluating how to integrate or extend the platform — for example, adding an AI call-operator agent for taking phone orders.

---

## 1. Mission

Sell food (samsa & bread) through Telegram bots:

- **Daily orders** — regular menu, immediate delivery or pickup
- **Catering** — large orders (100+ samsa, 40+ bread/tandir) for events, scheduled 24h+ in advance
- **Delivery providers** — own couriers (Telegram-driven) OR Yandex Delivery (auto-dispatched)
- **Payments** — Click + Payme (online), or cash on pickup

The system is **multi-tenant**: one platform can run multiple restaurants, each with its own Telegram bot, branches, menu, and admin.

---

## 2. Tech stack

| Layer | Tech |
|-------|------|
| Backend API | **FastAPI** (Python 3.12), SQLAlchemy async, SQLite (prod) |
| Telegram bots | **aiogram 3** (asyncio) |
| Admin panel | **React 18 + Vite + Ant Design** |
| Super-admin panel | React 18 + Vite (separate app) |
| Reverse proxy | nginx (TLS, static, API routing) |
| Auth | Static SECRET_KEY-based bearer token (`SECRET_KEY:restaurant_id`) |
| Currency | Real-time CBU API (`cbu.uz`), 1h cache |
| Maps | Yandex Maps (admin pin), Telegram native location (clients) |

Server: VPS at `65.109.5.207`, domain `restaurant.tursunboyev.com`.

---

## 3. Repository structure

```
MuhsinaDollar/
├── api/                        # FastAPI backend
│   ├── main.py                 # App entrypoint, CORS, router registration
│   ├── config.py               # Pydantic Settings (env vars)
│   ├── database.py             # AsyncSession, engine
│   ├── auth_deps.py            # Bearer token → restaurant_id (IDOR protection)
│   ├── routes/
│   │   ├── auth.py             # POST /auth/login, /auth/bot-login
│   │   ├── menu.py             # Public bot endpoints (categories, products)
│   │   ├── orders.py           # Order create/list/status updates
│   │   ├── catering.py         # Catering orders (somsa/nan groups, mixed items)
│   │   ├── reviews.py
│   │   ├── couriers.py         # Courier registration & dispatch
│   │   ├── branches.py         # Branch CRUD + nearest-branch search
│   │   ├── admin.py            # Restaurant-admin CRUD (products, categories, settings, ...)
│   │   ├── superadmin.py       # Platform-level (manage restaurants & bots)
│   │   └── users.py
│   └── services/
│       ├── currency.py         # CBU USD rate, cached
│       ├── yandex_delivery.py  # Yandex B2B Cargo API client (mock fallback)
│       └── delivery.py         # Provider orchestrator
├── bot/                        # Customer-facing Telegram bot
│   ├── main.py                 # Bot entrypoint (per-restaurant, run in subprocess)
│   ├── api_client.py           # HTTP client → backend
│   ├── states.py               # FSMs (Registration, OrderFlow, CateringFlow, ReviewFlow)
│   ├── utils.py                # clear_state_preserve_branch helper
│   ├── handlers/
│   │   ├── start.py            # /start, branch selection (location-based)
│   │   ├── menu.py             # Category/product browsing
│   │   ├── cart.py             # Cart & checkout
│   │   ├── order.py            # Address, payment, confirmation
│   │   ├── catering.py         # FSM for catering: group → items → date → time → ...
│   │   ├── review.py
│   │   └── profile.py
│   └── keyboards/              # ReplyKeyboard / InlineKeyboard builders
├── courier_bot/                # Separate bot for couriers (registration, accept order, mark delivered)
├── catering_bot/               # Separate bot for catering notifications
│   └── main.py                 # Subscribers, daily 20:00 scheduler, formatted notifications
├── admin/                      # React admin panel
│   └── src/pages/              # Dashboard, Orders, Menu, Couriers, Reviews, Settings, Admins, Users
├── super_admin/                # React super-admin panel (manage restaurants & their bots)
├── database/
│   └── models.py               # SQLAlchemy models — single source of truth for schema
├── static/                     # Uploaded product images, brand assets
├── docs/
│   ├── PROJECT_OVERVIEW.md     # This file
│   └── RESTORAN_HUJJATLARI.md  # Documents restaurants need for legal onboarding
└── scripts/
    └── run_all_bots.py         # Spawns one subprocess per active restaurant bot
```

---

## 4. Domain model (database)

Source of truth: [`database/models.py`](../database/models.py).

### Core entities

- **Restaurant** — tenant. Owns bot tokens (`bot_token`, `courier_bot_token`), admin credentials, work hours, delivery provider config (`own` | `yandex`), Yandex/Click/Payme keys, currency settings, catering pricing rules.
- **Branch** — physical location belonging to a restaurant. Has its own coords, work hours, optional override settings.
- **User** — Telegram end-user. Stores `telegram_id`, name, phone, language, last `selected_branch_id`.
- **Address** — saved delivery addresses per user.
- **Category** — menu category, scoped by `restaurant_id` and optionally `branch_id` (NULL = restaurant-wide).
- **Product** — menu item. `product_type='regular'` for daily menu, `'catering'` for event orders. Catering items have `catering_group ∈ {somsa, nan}`, `unit_price_usd`, `unit_price_pickup_uzs`.
- **Order** — unified for both daily & catering (`order_kind ∈ {regular, catering}`). Tracks status, delivery type/subtype, schedule (catering), payment status, total/items/Yandex claim id.
- **OrderItem** — line items.
- **Courier** — registered courier per branch, status `pending|active|blocked`, transport type.
- **Review** — rating + comment per branch.
- **Admin** — sub-admin accounts under a restaurant.
- **CateringSubscriber** — Telegram chats (private or group) that receive daily 20:00 catering digests.
- **Plan / CommissionPayment** — SaaS billing layer.

### Order lifecycle (state machine)

```
pending → confirmed → preparing → ready → delivering → delivered
                                                     ↘ cancelled (anytime)
```

Status changes are pushed to the customer via the restaurant's Telegram bot, and to couriers via the courier bot.

---

## 5. Bot flows (customer-facing)

### Daily order — `OrderFlow`
1. `/start` → if user has saved branch, jump to main menu; otherwise ask for location → list nearest branches → pick one.
2. **🍽 Menyu** → categories → products → add to cart (qty +/-).
3. **🛒 Savat** → review → checkout:
   - Delivery type: delivery / pickup
   - Address (Telegram location OR text)
   - Payment method (cash/card; online TBD)
   - Comment
4. Confirm → backend creates order → couriers notified via courier_bot.

### Catering order — `CateringFlow`
Trigger: **🎉 Tadbir uchun buyurtma** button.
1. **Group**: 🥟 Somsa (min 100) or 🍞 Non (min 40, step 40).
2. **Items**: per-product quick-add buttons (somsa: +10/+50/+100, non: +10/+20/+40). User can mix multiple types; total must hit group min and step.
3. **Delivery subtype**:
   - `onsite` — bakers come with tandir/oven and bake on-site (no Yandex)
   - `pickup` — customer picks up from restaurant
   - `delivery` — Yandex Delivery brings finished goods (auto-priced)
4. **Schedule**: date (must be ≥ 24h ahead — under 24h shows hotline `+998 98 000 06 04`), then time (08:00–22:00, 30-min steps, or custom `HH:MM`).
5. **Phone** (Telegram contact share or typed `+998...`).
6. **Location** + textual address.
7. **Payment**: method (cash/card) × timing (now/later). "Now" shows the configured restaurant card OR (future) opens a Click/Payme checkout URL.
8. **Confirm** → validates 24h rule + group min/step + (for delivery) calculates Yandex price → creates order → returns "bakers arrive 2 hours before" message.

### Courier flow (`courier_bot`)
- `/start` → register (name, phone, transport, branch) → status starts as `pending`.
- Admin promotes courier to `active` from admin panel.
- New `delivery`-type orders are pushed to all `active` couriers as a card with **Accept / Reject** inline buttons.
- On accept: order goes to `delivering`, courier sees customer location pin + address; on delivered: status `delivered`.

### Catering notifier flow (`catering_bot`)
- `/start` in DM or add-to-group → registers as `CateringSubscriber`.
- Internal scheduler: every day at **20:00 Asia/Tashkent** sends a digest of **tomorrow's** catering orders to all subscribers, one order per message (location pin + details), then a summary list.

---

## 6. API surface

Bearer token format: `<SECRET_KEY>` (super-admin) or `<SECRET_KEY>:<restaurant_id>` (restaurant admin). The `auth_deps.require_restaurant_admin` dependency rejects mismatches between token and `restaurant_id` query param (IDOR protection added during the security audit).

Catering POST endpoints additionally require `X-Bot-Secret: <SECRET_KEY>` to prevent telegram_id spoofing from outside callers.

### Public (bot)
- `POST /auth/bot-login` — bot exchanges its Telegram bot token for a restaurant-scoped token.
- `GET /menu/categories?branch_id=…` / `GET /menu/categories/{id}/products?branch_id=…`
- `POST /orders` (daily orders)
- `GET /catering/groups?restaurant_id=…`
- `POST /catering/calculate-price` (preview)
- `POST /catering/orders` (creates catering order; X-Bot-Secret required)
- `GET /branches/nearest?lat=…&lon=…`

### Admin (Bearer required)
- `GET/PUT /admin/settings` — full restaurant settings
- `GET/POST/PUT/DELETE /admin/products` (with `?product_type=regular|catering` filter)
- `GET/POST/PUT/DELETE /admin/categories`
- `POST/DELETE /admin/upload-image` (path-traversal-protected; 10 MB max)
- `GET /admin/orders` (with `?order_kind=regular|catering`)
- `PATCH /admin/orders/{id}/status`
- `GET /admin/users`, `GET /admin/admins`, `POST /admin/admins`, `DELETE /admin/admins/{id}`
- `GET /admin/stats`

### Super-admin
- CRUD over restaurants, manage their bots & plans (`/super/...`).

Full OpenAPI is auto-generated at `/docs` (FastAPI Swagger).

---

## 7. Integrations

### Yandex Delivery (B2B Cargo)
- Module: [`api/services/yandex_delivery.py`](../api/services/yandex_delivery.py)
- Endpoints used: `/claims/create`, `/claims/accept`, `/claims/info`, `/claims/cancel`
- **Mock mode** when token is empty / `"test"` / `"mock"` — returns a fake `claim_id` and a Tashkent demo tracking URL, so UI/order-flow can be exercised end-to-end before the real OAuth token is issued.
- Real token requires: Yandex business contract + EDO confirmation in `dostavka.yandex.ru/account` → "Integratsiya" → "Get token" (returns `y0_Ag…` token).
- Used only when `Restaurant.delivery_provider == 'yandex'` AND order is `delivery`-type. `onsite`/`pickup` never call Yandex.

### Click & Payme (online payments)
- Schemas added to `Restaurant` (`click_*`, `payme_*` columns) and Settings UI (collapsible cards under "💳 To'lov" tab).
- API clients & webhooks **not yet implemented** — pending real merchant credentials. Once credentials arrive, the plan is:
  - `POST /payments/click/create` → returns hosted-page URL → bot DMs it to customer
  - `POST /payments/click/callback` → idempotent webhook → flips `Order.payment_status='paid'` → triggers Yandex dispatch / courier notification
  - Same shape for Payme.

### Currency (CBU)
- `api/services/currency.py` — fetches `https://cbu.uz/uz/arkhiv-kursov-valyut/json/USD/`, caches per-restaurant for 1h. Falls back to `currency_rate_manual` if API unreachable or `currency_auto=False`.

### POS (Alice POS)
- Skeleton in `pos/alice.py` for pushing orders to a kitchen display system. Not active in production; orders are sent best-effort and failure is silenced.

---

## 8. Admin panel layout

Tabs in `Settings` (left sidebar item, scoped to the logged-in restaurant):

1. **🏪 Restoran** — name, address, phone, Yandex Maps pin
2. **⏰ Ish vaqti** — open/close time, minimum order amount
3. **🚗 Dastavka** — provider toggle (own/yandex), Yandex token & test-mode switch
4. **💳 To'lov** — Click cards (merchant_id/service_id/secret_key), Payme cards (merchant_id/key), catering manual card
5. **🎉 Catering** — currency (auto CBU vs manual), per-group min/step, delivery per-km
6. **🌐 Til** — bot language (uz/ru)

Other pages: Dashboard (stats), Orders (segmented by Regular/Catering, with order-detail modal showing embedded Yandex Map), Menu (Menyu / Kategoriyalar / Catering tabs), Couriers (3-dot actions: edit/approve/block/delete), Reviews, Users, Admins.

---

## 9. Deployment

Single VPS, no Docker (currently):
- API: `uvicorn api.main:app --host 127.0.0.1 --port 8086 --workers 2` (nginx in front for TLS + static)
- Bots: `python3 -m scripts.run_all_bots` — spawns one subprocess per restaurant `bot.main` + `courier_bot.main`. The catering bot is launched separately when its token is configured.
- Admin & super-admin panels: built with `npm run build` → served as static by nginx.
- DB: SQLite file at `/opt/restaurant/muhsina_somsa.db`. Migrations are applied as ad-hoc `ALTER TABLE` statements committed alongside the model change.
- Logs: `/opt/restaurant/api.log`, `/opt/restaurant/bots.log`.

CI/CD is manual: `git push` then `scp` changed files + restart on the server.

---

## 10. Security posture

A security audit (see commit `v13`) addressed:
- **IDOR** — admin endpoints now enforce token ↔ restaurant_id match via `auth_deps.require_restaurant_admin`.
- **CORS** — no longer wildcard; explicit allowlist of admin/super-admin/dev origins.
- **Path traversal** — image deletion validates UUID-shaped filenames + abspath check inside `UPLOAD_DIR`.
- **Catering spoofing** — `POST /catering/orders` requires `X-Bot-Secret`.
- **Upload size** — 10 MB cap on image uploads.

Open items: bcrypt password hashing (currently SHA-256), JWT with expiration (currently static SECRET_KEY token), rate limiting on `/auth/bot-login`, secret rotation away from `.env`.

---

## 11. Where an AI call-operator agent could plug in

The platform is well-suited for adding a **voice/phone AI agent** that takes orders by phone and inserts them into the existing pipeline, because:

1. **All order creation goes through HTTP APIs** that already accept structured input — `POST /orders` for daily and `POST /catering/orders` for catering. An AI agent's job reduces to filling those payloads.
2. **User identity isn't tied to Telegram** — `User` only requires `telegram_id`, `full_name`, `phone`. For phone-originated orders the agent can:
   - Match the caller's phone to an existing `User.phone`, OR
   - Create a synthetic user with `telegram_id = "phone:+998..."` so it doesn't collide with real Telegram IDs.
3. **Catering's 24h rule + hotline** is already exposed in the bot — the AI agent should be the recipient of those overflow calls (`+998 98 000 06 04`), so it handles exactly the cases the bot rejects.
4. **Branch logic is already centralised** — `GET /branches/nearest?lat=…&lon=…` returns ordered branches; the agent can ask the caller for the destination address, geocode it, pick the nearest branch, and reuse the same order-creation flow.
5. **Order-status notifications already exist** — once an order is created via API, the customer's Telegram bot (if linked) receives the same status messages. The AI agent can additionally send SMS or place an outbound confirmation call.

### Suggested integration points

- **Inbound call → STT → LLM agent → tool-calling**: tools = thin wrappers around the existing endpoints (`get_branches`, `get_menu_for_branch`, `add_to_cart`, `create_order`, `start_catering_order`, `quote_catering_price`, `confirm_payment_link`).
- **Authentication**: dedicate one bearer token for the agent (a "virtual restaurant admin" account or a new `phone-agent` token type) and pass `X-Bot-Secret` for catering POSTs.
- **Hand-off**: if the AI agent can't proceed (complex requests, complaints, refunds), it should route to a human operator — current refund policy is already manual ("kassirlar aloqaga chiqishadi").
- **Data**: the agent can read the same `Order` rows the admin panel displays, so its state is consistent with what staff sees.

### What the agent needs from us

- Ngrok-style or stable HTTPS endpoint for the API (`restaurant.tursunboyev.com/api`)
- A bearer token + `X-Bot-Secret`
- The list of restaurant IDs the agent is allowed to act on
- A short system prompt encoding the catering rules (min 100 somsa, min 40 nan with step 40, 24h advance, three delivery subtypes, Click/Payme/cash payment options)
- Optionally: read access to `GET /admin/products?product_type=catering&restaurant_id=…` so the agent can quote prices live

---

## 12. Quick reference for an external AI

If you're an external AI being asked to integrate with this platform, the minimum mental model is:

> Multi-tenant Telegram-first food ordering. Each restaurant has bot + admin panel. Two order kinds: regular (now) and catering (≥24h scheduled). Delivery is either own couriers (Telegram) or Yandex (auto). Payments are cash or — once merchant accounts are live — Click/Payme. All state lives in SQLite, all mutation goes through FastAPI. Add features by writing new routes + a thin client; don't write to the DB directly.

End of overview.
