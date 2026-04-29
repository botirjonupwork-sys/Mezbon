# Muhsina Dollar Somsa — Technical Documentation

> Comprehensive technical reference for AI agents and engineers integrating with or extending this codebase.
>
> Audience: an AI/LLM that needs to understand the system end-to-end without reading every source file.
> Read this once and you will know: what the system does, how it's structured, every entity in the database,
> every API endpoint, every Telegram bot flow, every integration, the deployment model, and the open work items.

**Repository:** `MuhsinaDollar`
**Production URL:** `https://restaurant.tursunboyev.com`
**Backend:** FastAPI (Python 3.12) on `127.0.0.1:8086`, behind nginx
**Stack:** FastAPI · aiogram 3 · React + Vite + Ant Design · SQLite · SQLAlchemy async
**Domain:** Restaurant food ordering & delivery (multi-tenant SaaS) for Uzbekistan
**Primary UI:** Telegram bots (per-restaurant); admin web panel for restaurants; super-admin web panel for platform operator

---

## 1. What this system does

Multi-tenant SaaS platform for Uzbek restaurants to sell food via Telegram bots. Each restaurant ("tenant") owns:

- Its own Telegram bot (different `bot_token` per restaurant)
- Its own courier Telegram bot (`courier_bot_token`)
- Branches (physical locations)
- Menu (categories + products)
- Delivery configuration (own couriers OR Yandex Delivery)
- Online payment configuration (Click, Payme — both being integrated)
- Catering settings (large event orders, scheduled ≥24h ahead)

The platform operator manages restaurants from a separate super-admin panel and bills them per plan or per order commission.

### Two distinct order kinds

1. **Regular orders** — daily menu, immediate delivery or pickup. Same as any food-delivery bot. Stored in `orders` table with `order_kind='regular'`.
2. **Catering orders** — large pre-scheduled orders for events (weddings, corporate). Minimum 100 samsa or 40 bread (tandir-baked). Three delivery sub-modes:
   - `onsite` — bakers come with portable tandir oven and bake fresh on location
   - `pickup` — customer picks up finished goods from the restaurant
   - `delivery` — Yandex Delivery brings finished goods to customer
   Stored in the same `orders` table with `order_kind='catering'`.

This distinction matters because:
- Catering uses **USD-based pricing** (CBU rate conversion) since prices are negotiated in dollars
- Catering enforces a **24-hour advance booking rule**
- Catering needs a **separate notification bot** that pushes tomorrow's orders to staff every evening at 20:00

---

## 2. Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                        END USERS                                    │
│  Telegram (customers)    │   Telegram (couriers)   │   Web admins  │
└────────┬─────────────────┴─────────┬────────────────┴───────┬──────┘
         │                           │                        │
   ┌─────▼──────┐            ┌───────▼──────┐         ┌──────▼──────┐
   │  bot/      │            │ courier_bot/ │         │   admin/    │
   │ (aiogram)  │            │  (aiogram)   │         │   (React)   │
   │ per-rest   │            │  per-rest    │         │  AntD SPA   │
   └─────┬──────┘            └───────┬──────┘         └──────┬──────┘
         │                           │                       │
         │      catering_bot/        │   super_admin/        │
         │      (notifications)      │   (React SPA)         │
         │           │               │       │               │
         └───────────┴───────────────┴───────┴───────────────┘
                     │ HTTPS / Authorization: Bearer
                     ▼
            ┌──────────────────┐
            │  FastAPI backend │
            │  api/            │
            │  port 8086       │
            └────────┬─────────┘
                     │
         ┌───────────┼─────────────────────────┐
         │           │                         │
   ┌─────▼──────┐ ┌──▼─────────┐   ┌──────────▼──────────┐
   │  SQLite    │ │ Yandex     │   │  Currency: cbu.uz   │
   │ database/  │ │ Delivery   │   │  (1h cache)         │
   │ models.py  │ │ B2B Cargo  │   │                     │
   └────────────┘ │ (mock OK)  │   └─────────────────────┘
                  └────────────┘
                                   ┌─────────────────────┐
                                   │  Click / Payme      │
                                   │  (planned, not yet) │
                                   └─────────────────────┘
```

Key architectural notes:

- **One bot per restaurant.** `scripts/run_all_bots.py` queries the DB at startup, then spawns one Python subprocess per active restaurant — each running `python -m bot.main` with that restaurant's `BOT_TOKEN` injected into the env. Subprocess isolation guarantees no FSM/state cross-contamination between restaurants.
- **Catering bot is separate** because it's notification-only and shared across restaurants (single global instance is fine).
- **Backend is the only database writer.** Bots and admin panels never touch SQLite directly; everything goes through HTTP. This keeps consistency invariants in one place.
- **Static auth tokens** for now. Format: `<SECRET_KEY>` (super-admin) or `<SECRET_KEY>:<restaurant_id>` (restaurant admin). JWT with expiration is a known TODO.
- **CORS allowlist** for the admin panels and `localhost` dev origins. Wildcard CORS was removed during the security audit.

---

## 3. Repository map

```
MuhsinaDollar/
├── api/                            # FastAPI backend
│   ├── main.py                     # App, CORS, router registration, static mount
│   ├── config.py                   # Pydantic Settings (env vars), extra="ignore"
│   ├── database.py                 # AsyncSession, engine, get_db dependency
│   ├── auth_deps.py                # Bearer token parser, IDOR guard
│   ├── schemas.py                  # Shared Pydantic schemas for request/response
│   ├── routes/
│   │   ├── auth.py                 # /auth/login, /auth/bot-login, /auth/super/login
│   │   ├── menu.py                 # /menu/categories, /menu/products (public, bot-facing)
│   │   ├── orders.py               # /orders/* (regular orders)
│   │   ├── catering.py             # /catering/* (groups, calc-price, orders) — X-Bot-Secret required for POST
│   │   ├── reviews.py              # /reviews/*
│   │   ├── couriers.py             # /couriers/* (registration, accept, deliver)
│   │   ├── branches.py             # /branches/*, /super/restaurants/{id}/branches/*, /admin/branches/*
│   │   ├── admin.py                # /admin/* (settings, products, categories, stats, orders, users, admins, upload-image)
│   │   ├── superadmin.py           # /super/* (manage restaurants & their bots & plans)
│   │   └── users.py                # /users/* (CRUD by telegram_id, addresses), /restaurants/*/info (public)
│   └── services/
│       ├── currency.py             # CBU USD/UZS rate, per-restaurant 1h cache
│       ├── yandex_delivery.py      # B2B Cargo client; mock when token in {None,"","test","mock"}
│       └── delivery.py             # Provider orchestrator: dispatch_order_to_provider()
│
├── bot/                            # Customer-facing Telegram bot
│   ├── main.py                     # run_bot(bot_token) — called per-restaurant via subprocess
│   ├── api_client.py               # HTTP client wrapping FastAPI; sets X-Bot-Secret header
│   ├── states.py                   # FSM state groups (Registration, OrderFlow, CateringFlow, ReviewFlow)
│   ├── utils.py                    # clear_state_preserve_branch(state) — keeps branch_id across resets
│   ├── handlers/
│   │   ├── start.py                # /start, branch selection (location-based + auto-pick if 1 branch)
│   │   ├── menu.py                 # browse categories/products, time-limited filtering
│   │   ├── cart.py                 # add/remove items, cart math
│   │   ├── order.py                # OrderFlow (delivery/pickup, address, payment, comment, confirm)
│   │   ├── catering.py             # CateringFlow (group → items → date → time → phone → loc → payment → confirm)
│   │   ├── review.py               # rating 1–5 + comment
│   │   └── profile.py              # /profile, registration FSM
│   └── keyboards/
│       ├── main.py                 # main_menu_kb, branch keyboards
│       ├── menu.py                 # category/product inline keyboards
│       ├── catering.py             # group selector, items selector with quick-add (+10/+50/+100), date/time pickers
│       └── ...
│
├── courier_bot/                    # Courier Telegram bot
│   ├── main.py                     # run_bot per-restaurant
│   └── handlers/                   # registration, view active orders, accept, mark delivered
│
├── catering_bot/                   # Notification-only Telegram bot
│   └── main.py                     # CommandStart subscribe, /stop unsubscribe, scheduler 20:00 daily push
│
├── admin/                          # Restaurant admin React SPA
│   └── src/
│       ├── App.jsx                 # routing
│       ├── api/index.js            # axios client; tokens via Authorization header
│       ├── store/auth.js           # zustand persist (token, restaurantId)
│       ├── store/branch.js         # zustand (selectedBranchId for scoped views)
│       ├── components/Layout.jsx   # sidebar, branch picker
│       └── pages/
│           ├── Login.jsx
│           ├── Dashboard.jsx
│           ├── Orders.jsx          # Segmented Regular/Catering, OrderDetailModal with embedded Yandex Map
│           ├── Menu.jsx            # Tabs: Menyu / Kategoriyalar / Catering
│           ├── Couriers.jsx        # 3-dot dropdown actions
│           ├── Reviews.jsx
│           ├── Settings.jsx        # Tabs: Restoran/Ish vaqti/Dastavka/To'lov/Catering/Til + Profile
│           ├── Users.jsx
│           └── Admins.jsx
│
├── super_admin/                    # Super-admin React SPA
│   └── src/pages/                  # Restaurants, Bots, Tariffs, Settings
│
├── database/
│   └── models.py                   # SQLAlchemy DeclarativeBase models — single source of truth for schema
│
├── pos/
│   ├── alice.py                    # Alice POS skeleton (best-effort, errors swallowed)
│   └── yandex.py                   # Legacy delivery client (superseded by api/services/yandex_delivery.py)
│
├── scripts/
│   ├── run_all_bots.py             # Spawns subprocess per restaurant for bot.main + courier_bot.main
│   └── migrate_plans.py            # Seed default subscription plans
│
├── static/
│   ├── images/products/<uuid>.jpg  # Uploaded product images
│   └── brand/                      # Brand assets (QR logo, etc.)
│
├── docs/
│   ├── PROJECT_OVERVIEW.md         # High-level overview (this file's predecessor)
│   ├── TECHNICAL_DOCS.md           # ← you are here
│   ├── AI_CALL_OPERATOR_PLAN.md    # 5-phase plan for adding voice AI
│   └── RESTORAN_HUJJATLARI.md      # Restaurant onboarding document checklist (Uzbek)
│
├── .env                            # Secrets (gitignored)
├── .env.example                    # Template
├── requirements.txt
├── docker-compose.yml              # Dev compose (api + bots + nginx)
├── Dockerfile.bots                 # Bots container
├── nginx.conf                      # Production nginx config
├── deploy.sh                       # One-shot deploy script
└── start.sh                        # Local dev startup
```

---

## 4. Database schema

Source of truth: [`database/models.py`](../database/models.py). All models inherit from a SQLAlchemy 2.x `DeclarativeBase`. Async engine, async sessions.

### Enums

```python
class OrderStatus(enum.Enum):
    pending, confirmed, preparing, ready, delivering, delivered, cancelled

class DeliveryType(enum.Enum):
    delivery, pickup

class CourierStatus(enum.Enum):
    pending, active, blocked
```

### Tables (key fields, omit relationships)

#### `restaurants` — tenants

| Column | Type | Purpose |
|---|---|---|
| `id` | int PK | |
| `name`, `slug` | str | display name + URL slug (unique) |
| `logo_url`, `address`, `phone` | str | brand info |
| `bot_token`, `courier_bot_token` | str | Telegram bot tokens |
| `admin_username`, `admin_password_hash` | str | restaurant-level admin login (SHA-256, will move to bcrypt) |
| `work_hours_from`, `work_hours_until` | str "HH:MM" | global hours |
| `min_order` | float | minimum order amount |
| `delivery_base_fee`, `delivery_per_km` | float | fallback delivery pricing when Yandex disabled |
| `restaurant_lat`, `restaurant_lon` | float | default coords |
| `plan`, `status`, `commission_percent` | str/float | SaaS billing |
| `payment_card_number`, `payment_card_name`, `payment_card_bank` | str | manual card display when online payment unavailable |
| `delivery_provider` | str | `'own'` \| `'yandex'` \| `'customer_choice'` |
| `yandex_api_token`, `yandex_test_mode` | str/bool | Yandex Delivery integration |
| `currency_auto`, `currency_rate_manual` | bool/float | USD→UZS rate config |
| `currency_rate_cache`, `currency_cache_updated_at` | float/dt | CBU API cache |
| `catering_payment_card`, `catering_payment_owner` | str | catering "now-pay" card |
| `catering_somsa_min`, `catering_somsa_step` | int | default 100, 1 |
| `catering_nan_min`, `catering_nan_step` | int | default 40, 40 |
| `catering_delivery_per_km_uzs` | float | default 5000 |
| `click_merchant_id`, `click_service_id`, `click_secret_key`, `click_enabled` | str/bool | Click Merchant API |
| `payme_merchant_id`, `payme_secret_key`, `payme_enabled` | str/bool | Payme Merchant API |

#### `branches` — physical locations

```python
id, restaurant_id (FK), name, address, phone, latitude, longitude,
work_hours_from, work_hours_until, min_order,
delivery_base_fee, delivery_per_km, is_active, created_at
```

A branch may override the restaurant-level work hours and pricing. `branch_id IS NULL` on a category/product means "applies to whole restaurant", filterable per-branch in queries.

#### `users` — customers (Telegram or phone-only)

```python
id, telegram_id (unique), full_name, phone, language ('uz'|'ru'),
selected_branch_id (FK→branches), created_at
```

Convention: phone-only users (e.g., AI call agent) use `telegram_id = "phone:+998..."` to avoid collision with real Telegram IDs.

#### `addresses` — saved delivery addresses

```python
id, user_id (FK), title, address, latitude, longitude
```

#### `categories`

```python
id, restaurant_id (FK, nullable), branch_id (FK, nullable),
name_uz, name_ru, alice_category_id, "order", is_active
```

#### `products`

```python
id, restaurant_id, branch_id, category_id (FK),
alice_product_id,
name_uz, name_ru, description_uz, description_ru,
price (float), image_url,
has_time_limit (bool), available_from "HH:MM", available_until "HH:MM",
is_active, is_stop,

# Catering-specific
product_type ('regular'|'catering'),
catering_group ('somsa'|'nan'),
unit_type ('piece'|'bunch_100'|'tandir_40'),
min_quantity, quantity_step,
unit_price_usd, unit_price_pickup_uzs,
price_onsite_usd, price_pickup_uzs, price_delivery_uzs, price_per_km_uzs
```

A `product_type='catering'` product:
- Always belongs to a `catering_group` (`somsa` or `nan`)
- Has `unit_price_usd` (used for `onsite` and `delivery` modes — converted to UZS via CBU rate at order time)
- Has `unit_price_pickup_uzs` (used directly for `pickup` mode in UZS)
- Min quantity / step rules come from the **restaurant-level** `catering_somsa_*` / `catering_nan_*` columns, NOT per-product

A `product_type='regular'` product uses `price` (UZS) directly.

#### `orders`

```python
id, restaurant_id, branch_id,
alice_order_id, yandex_claim_id, yandex_status, yandex_tracking_url, yandex_price,
user_id, courier_id,
status (OrderStatus), delivery_type (DeliveryType),
address, latitude, longitude, comment,
total_price (UZS), delivery_fee, created_at, updated_at,

# Catering-specific
order_kind ('regular'|'catering'),
schedule_date "YYYY-MM-DD", schedule_time "HH:MM",
delivery_subtype ('onsite'|'pickup'|'delivery'),
payment_method ('cash'|'card'),
payment_timing ('now'|'later'),
payment_status ('pending'|'paid'),
currency_rate_snapshot, total_price_usd
```

#### `order_items`

```python
id, order_id, product_id, quantity, price (per unit, snapshot at order time)
```

#### `couriers`

```python
id, restaurant_id, branch_id (nullable),
telegram_id (unique), full_name, phone,
transport_type ('car'|'motorcycle'|'bicycle'|'walk'),
status (CourierStatus),
created_at
```

#### `reviews`

```python
id, restaurant_id, branch_id, user_id, rating (1-5), comment, created_at
```

#### `admins` — sub-admins under a restaurant

```python
id, restaurant_id (FK, NOT NULL),
username, password_hash, role ('admin' default), created_at
```

#### `catering_subscribers` — who receives catering notifications

```python
id, restaurant_id, chat_id (unique str — can be Telegram user OR group),
chat_type ('private'|'group'|'supergroup'),
title, is_active, created_at
```

#### `plans`, `commission_payments` — SaaS billing layer

Mostly unused in current implementation; placeholder for billing-flavored features.

---

## 5. API endpoints

Base URL: `http://127.0.0.1:8086` (server) or `http://localhost:8000` (dev). Production: `https://restaurant.tursunboyev.com/api`.

OpenAPI is auto-generated at `GET /docs` (FastAPI Swagger UI).

### Authentication

```
Authorization: Bearer <SECRET_KEY>            # super-admin (full access)
Authorization: Bearer <SECRET_KEY>:<rest_id>  # restaurant admin (scoped)
X-Bot-Secret: <SECRET_KEY>                    # required for POST /catering/orders
```

The dependency `api.auth_deps.require_restaurant_admin` parses the bearer token and:
- Returns the `restaurant_id` from the token
- If a `restaurant_id` query param is also passed, **rejects mismatch** (IDOR guard)
- For super-admin tokens, allows any `restaurant_id` query (or returns None for "all restaurants")

### Public / bot-facing routes

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/auth/login` | Restaurant admin login by username/password → bearer token |
| `POST` | `/auth/super/login` | Super-admin login |
| `POST` | `/auth/bot-login` | Exchange Telegram bot token for restaurant-scoped API token |
| `GET` | `/users/{telegram_id}` | Lookup user |
| `POST` | `/users/` | Create user |
| `POST` | `/users/{telegram_id}/branch` | Save user's selected branch |
| `GET` | `/users/{telegram_id}/addresses` | Saved addresses |
| `POST` | `/users/{telegram_id}/addresses` | Add address |
| `GET` | `/restaurants/{id}/info` | Public restaurant info (no auth) |
| `GET` | `/menu/categories?restaurant_id=&branch_id=` | List categories (excludes catering) |
| `GET` | `/menu/products?restaurant_id=&branch_id=` | All regular products, filtered by time-of-day availability |
| `GET` | `/menu/categories/{id}/products?branch_id=` | Products in category |
| `GET` | `/menu/products/{id}` | Single product |
| `PATCH` | `/menu/products/{id}/stop?is_stop=true` | Toggle stop-list (admin convenience) |
| `POST` | `/orders/` | Create regular order. Triggers `dispatch_order_to_provider` after commit |
| `GET` | `/orders/user/{telegram_id}` | User's orders |
| `GET` | `/orders/{id}` | Single order |
| `PATCH` | `/orders/{id}/status?status=...` | Status transition (also re-notifies couriers on `ready`) |
| `POST` | `/reviews` | Create review |
| `GET` | `/reviews?restaurant_id=&branch_id=` | List reviews |
| `GET` | `/reviews/stats?restaurant_id=&branch_id=` | Avg rating, total count |
| `POST` | `/couriers/register` | Courier self-registration via courier bot |
| `GET` | `/couriers/{telegram_id}` | Courier lookup |
| `GET` | `/couriers/{telegram_id}/orders` | Active assignments |
| `POST` | `/couriers/{telegram_id}/accept/{order_id}` | Accept order |
| `POST` | `/couriers/{telegram_id}/delivered/{order_id}` | Mark delivered |
| `GET` | `/branches/nearest?lat=&lon=&restaurant_id=` | Nearest branches by Haversine, sorted by distance |
| `GET` | `/branches/{id}` | Branch info |
| `GET` | `/branches/{id}/is-open` | Open/closed check |
| `GET` | `/admin/branches?restaurant_id=` | Admin: list branches (auth required) |
| `GET` | `/admin/branches/{id}/settings` | Branch override settings |
| `PUT` | `/admin/branches/{id}/settings` | Update branch override |

### Catering routes

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/catering/groups?restaurant_id=` | Returns 2 groups (somsa, nan) with their min/step + products |
| `GET` | `/catering/products?restaurant_id=` | Legacy flat list |
| `GET` | `/catering/currency?restaurant_id=` | Current USD→UZS rate (auto from CBU or manual) |
| `POST` | `/catering/calculate-price?restaurant_id=` | Preview price for a mixed-item cart |
| `POST` | `/catering/orders?telegram_id=&restaurant_id=&branch_id=` | Create order (requires `X-Bot-Secret`) |

#### Catering price calculation contract

```jsonc
// POST /catering/calculate-price?restaurant_id=1
{
  "group": "somsa",                    // or "nan"
  "items": [
    {"product_id": 11, "quantity": 33},
    {"product_id": 12, "quantity": 34},
    {"product_id": 13, "quantity": 33}
  ],
  "delivery_subtype": "onsite",        // or "pickup" | "delivery"
  "distance_km": 5.5                   // only used when delivery_subtype="delivery" and Yandex disabled
}
```

```jsonc
// 200 OK
{
  "total_quantity": 100,
  "subtotal_uzs": 1451679,
  "subtotal_usd": 120.0,
  "delivery_fee_uzs": 0,
  "total_price_uzs": 1451679,
  "total_price_usd": 120.0,
  "currency_rate": 12097.33,
  "breakdown": [
    {"product_id": 11, "name_uz": "Go'shtli somsa", "quantity": 33, "unit_price_usd": 1.2, "item_usd": 39.6, "item_uzs": 479054},
    ...
  ]
}
```

Validation rules (enforced server-side):
- Sum of quantities ≥ `restaurant.catering_<group>_min`
- Sum of quantities is a multiple of `restaurant.catering_<group>_step`
- `delivery_subtype='pickup'` uses `unit_price_pickup_uzs`; others use `unit_price_usd × CBU rate`
- `delivery_subtype='delivery'` adds `distance_km × catering_delivery_per_km_uzs` (or Yandex's quote when wired)

### Admin routes (Bearer required, scoped by token)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/admin/upload-image` | UUID-named storage in `static/images/products/`, 10 MB cap |
| `DELETE` | `/admin/upload-image?url=` | Path-traversal-protected delete (UUID regex match + abspath check) |
| `GET` | `/admin/stats?restaurant_id=&branch_id=&date_from=&date_to=` | Today's orders count, revenue, active orders, avg rating |
| `GET` | `/admin/orders?restaurant_id=&branch_id=&order_kind=&status=&date_from=&date_to=` | Order list with items expanded |
| `PATCH` | `/admin/orders/{id}/status?status=` | (alias of `/orders/{id}/status`) |
| `GET` | `/admin/products?restaurant_id=&branch_id=&category_id=&product_type=` | All products (admin sees catering too) |
| `POST` | `/admin/products?restaurant_id=` | Create product |
| `PUT` | `/admin/products/{id}?restaurant_id=` | Update product (`exclude_unset` semantics) |
| `DELETE` | `/admin/products/{id}` | Soft delete (`is_active=False`) |
| `GET` | `/admin/categories?restaurant_id=&branch_id=` | List |
| `POST` | `/admin/categories?restaurant_id=` | Create |
| `PUT` | `/admin/categories/{id}` | Update |
| `DELETE` | `/admin/categories/{id}` | Soft delete |
| `GET` | `/admin/users?restaurant_id=&branch_id=` | List customers (scoped by orders to restaurant's branches) |
| `GET` | `/admin/users/{id}/orders` | Customer's order history |
| `GET` | `/admin/settings?restaurant_id=` | Full restaurant settings (~30 fields) |
| `PUT` | `/admin/settings?restaurant_id=` | Bulk update settings |
| `GET` | `/admin/profile?restaurant_id=` | Admin profile |
| `PUT` | `/admin/profile?restaurant_id=` | Update profile (username/password) |
| `GET` | `/admin/admins?restaurant_id=` | Sub-admins |
| `POST` | `/admin/admins?restaurant_id=` | Create sub-admin |
| `DELETE` | `/admin/admins/{id}` | Delete sub-admin |

### Super-admin routes (`Authorization: Bearer <SECRET_KEY>` only)

| Method | Path | Purpose |
|---|---|---|
| `GET/POST/PUT/DELETE` | `/super/restaurants` | Restaurant CRUD (one row per tenant) |
| `GET/PUT` | `/super/restaurants/{id}` | Tenant detail |
| `POST/DELETE` | `/super/restaurants/{id}/branches` | Branches under a restaurant |
| `GET/POST` | `/super/plans` | Subscription plans |
| `GET/POST` | `/super/commissions` | Commission payments |

---

## 6. Telegram bot flows

All flows use `aiogram.fsm` with `MemoryStorage`. State is local to each subprocess (one per restaurant). Branch ID is preserved across `state.clear()` via `bot.utils.clear_state_preserve_branch`.

### `Registration` (in `start.py`)
```
Registration.full_name → Registration.phone → done
```
Triggered by tapping "📝 Ro'yxatdan o'tish" or accessing /profile when no user exists.

### `OrderFlow` (regular orders, in `order.py`)
```
1. User taps "🛒 Savat" with cart filled
2. choosing_delivery: "🚗 Dastavka" or "🏪 Saboy"
3. entering_address (delivery only):
     - F.location → reverse-geocode → save coords
     - F.web_app_data → coords from inline map
     - F.text → free-text address
4. entering_comment (skip with "—")
5. choosing_payment: "💵 Naqd" (only path now; online TBD)
6. confirming → POST /orders/ → success message
```

### `CateringFlow` (in `catering.py`)
```
🎉 Tadbir uchun buyurtma → choosing_group
  ↓ (cat_g:somsa | cat_g:nan)
selecting_items
  ↓ +/- buttons; quick-add: somsa=[10,50,100], nan=[10,20,40]; or custom qty
  ↓ when total ≥ min and total % step == 0: "✅ Davom etish"
choosing_delivery
  ↓ onsite | pickup | delivery
choosing_date
  ↓ Tomorrow + next 28 days inline grid; or custom typed (DD.MM.YYYY)
  ↓ rejects dates < tomorrow → message with hotline +998 98 000 06 04
choosing_time
  ↓ 08:00-22:00 in 30-min steps; or custom typed (HH:MM)
entering_phone → contact button or +998... text
entering_location (delivery/onsite only) → F.location, then text address
choosing_payment_method (cash | card)
choosing_payment_timing (now | later)
confirming → POST /catering/orders → success + 2-hour-warning message
```

State diagram for CateringFlow, more compactly:

```
choose_group → select_items → choose_delivery → choose_date → choose_time
            → enter_phone → [enter_location] → pay_method → pay_timing → confirm
```

### Courier bot
```
/start → register (FSM): name → phone → transport → branch
admin promotes courier.status from 'pending' to 'active'

When admin order POST creates a delivery-type order, courier_bot
sends to all active couriers:
  • Location pin
  • Order details + Accept/Reject inline buttons
On accept: order.courier_id, status='delivering'
```

### Catering bot (notification-only)
```
/start in DM or group → CateringSubscriber row created (is_active=True)
/stop → is_active=False
/test → trigger send_daily_orders(target_chat_id=this) immediately

scheduler_loop():
  - sleep until next 20:00 Asia/Tashkent
  - send_daily_orders() with no target → broadcasts to all is_active subs
  - For each tomorrow-scheduled catering order (status != cancelled),
    sends to each subscriber:
      1. send_location(latitude, longitude)
      2. send_message with full details (items, time, customer, payment, comment)
  - Final summary list message at the end
```

---

## 7. Admin panel (React)

Stack: React 18, Vite, Ant Design 5, axios, zustand persist. State lives in localStorage.

### `store/auth.js`
```js
{ token, admin, isAuth, restaurantId }
setAuth(token, admin, restaurantId), logout()
```

### `store/branch.js`
```js
{ selectedBranchId }
setSelectedBranchId(id)  // null = "all branches" view
```

### Pages

- **Login** — restaurant admin or super-admin login form. Posts to `/auth/login` or `/auth/super/login`.
- **Dashboard** — KPI cards from `/admin/stats`.
- **Orders** — Segmented `Barchasi | 🍽 Oddiy | 🎉 Catering`, RangePicker, polling every 10s with audio cue on new orders, OrderDetailModal with embedded Yandex Map iframe pinned to the order's coords.
- **Menu** — three Tabs:
  - `Menyu` — regular products table with category filter
  - `Kategoriyalar` — category CRUD
  - `🎉 Catering` — at top: per-group min/step + delivery_per_km settings card; below: products list filtered by group (Segmented), CRUD with `catering_group` selector
- **Couriers** — table with 3-dot Dropdown actions (`tahrirlash | tasdiqlash | bloklash | blokdan chiqarish | o'chirish`).
- **Reviews** — list + stats card.
- **Settings** — six Tabs:
  - `🏪 Restoran` — name, phone, address, Yandex Maps pin
  - `⏰ Ish vaqti` — open/close time, minimum order amount
  - `🚗 Dastavka` — `delivery_provider` Select (`own | yandex`), Yandex token + test mode (collapsed under condition)
  - `💳 To'lov` — Click card (enabled switch + merchant_id/service_id/secret_key), Payme card, manual catering card
  - `🎉 Catering` — currency auto/manual + somsa/nan min&step + per-km
  - `🌐 Til` — bot UI language (uz/ru)
  + below: Profile section (admin username/password change)
- **Users** — customer list (scoped to restaurant by orders).
- **Admins** — sub-admin CRUD.

### Image upload pattern
- File picked → preview only (URL.createObjectURL)
- On Save: old image (if any) is deleted, new one uploaded, then product saved with new URL
- This avoids orphan files on the disk when a user changes mind without saving

---

## 8. Third-party integrations

### Yandex Delivery B2B Cargo (active, mock fallback)

File: [`api/services/yandex_delivery.py`](../api/services/yandex_delivery.py)

```python
PROD_URL = "https://b2b.taxi.yandex.net/b2b/cargo/integration/v2"
TEST_URL = "https://b2b.taxi.tst.yandex.net/b2b/cargo/integration/v2"

class YandexDeliveryClient:
    def __init__(self, api_token: str, test_mode: bool = True):
        self.mock_mode = not api_token or api_token in ("test", "mock")

    async def create_claim(...): ...   # POST /claims/create
    async def accept_claim(claim_id): ...  # POST /claims/accept
    async def get_claim_info(claim_id): ...  # POST /claims/info
    async def cancel_claim(claim_id, reason): ...  # POST /claims/cancel
```

When mock_mode=True, `create_claim` returns `{id: "mock-<uuid12>", status: "new", tracking_url: "https://dostavka.yandex.uz/track/mock-...", price: 15000.0}`.

Orchestrator: [`api/services/delivery.py`](../api/services/delivery.py)

```python
async def dispatch_order_to_provider(order, db) -> dict | None:
    # Returns None if order.delivery_type != 'delivery' OR provider == 'own'
    # When provider == 'yandex', calls YandexDeliveryClient.create_claim
    # and updates order.yandex_claim_id, yandex_status, yandex_tracking_url, yandex_price
```

Hook point: called from `orders.py::create_order` after the order is committed and only when `delivery_type == 'delivery'`. Catering's `onsite` and `pickup` modes never call Yandex; only `catering.delivery_subtype == 'delivery'` would (currently the catering router doesn't yet wire this — TODO).

To activate real Yandex:
1. Restaurant gets OAuth token from `dostavka.yandex.ru/account/integration` (requires EDO + payment method on the Yandex side).
2. Admin sets `restaurant.delivery_provider='yandex'`, pastes token into `yandex_api_token`, switches `yandex_test_mode` to false in Settings → Dastavka.
3. Same code path; mock_mode auto-disables when token is non-empty and not "test"/"mock".

### Currency (CBU)

File: [`api/services/currency.py`](../api/services/currency.py)

```python
async def get_currency_rate(restaurant_id, db) -> float:
    # If restaurant.currency_auto and cache is fresh (<1h): return cache
    # Else fetch https://cbu.uz/uz/arkhiv-kursov-valyut/json/USD/, update cache, return
    # Fallbacks: cache → manual → 12500.0
```

Used in catering price calculations and stored in each catering order as `currency_rate_snapshot` for historical accuracy.

### Click & Payme (planned, schemas in place)

`Restaurant` already has the columns; `Settings.jsx` Payments tab already collects credentials. Not yet wired:
- No `POST /payments/click/create` or `/payments/payme/create` route exists yet
- No webhook endpoint for confirmation
- `Order.payment_status` exists but isn't yet flipped by an external callback

Recommended implementation skeleton when credentials arrive:

```python
# api/services/click.py — new module
async def create_invoice(order: Order, restaurant: Restaurant) -> str:
    # Sign request with click_secret_key; return hosted-page URL
    pass

async def handle_callback(payload: dict) -> bool:
    # Verify HMAC, find order by transaction_id, set payment_status='paid'
    # Re-trigger dispatch_order_to_provider so courier/Yandex gets notified
    pass
```

### Alice POS (legacy, best-effort)

Skeleton in `pos/alice.py`. Order creation tries to push to Alice POS but errors are silenced. Treat this as optional/dormant.

---

## 9. Authentication & security model

### Token formats

```
<SECRET_KEY>                  → super-admin (full access to all restaurants)
<SECRET_KEY>:<restaurant_id>  → restaurant admin (scoped to that restaurant)
```

`SECRET_KEY` is the same value as the `.env` `SECRET_KEY` setting. **Same secret protects everything**, hence rotating it invalidates all sessions — currently no per-session JWT.

### Auth dependencies

[`api/auth_deps.py`](../api/auth_deps.py):

```python
async def require_restaurant_admin(authorization, restaurant_id: Optional[int] = Query(None)) -> int:
    # Parse token
    # If super: return restaurant_id (or None) as-is
    # If restaurant admin: ensure query restaurant_id matches token's; reject 403 otherwise
    # Returns the restaurant_id to use for the operation
```

This single dependency provides both authentication AND the IDOR guard. Every admin endpoint takes `restaurant_id: Optional[int] = Depends(require_restaurant_admin)`.

### `X-Bot-Secret` header

Required by `POST /catering/orders`. Bot's `api_client.py` reads `SECRET_KEY` from env and sets the header. This prevents external callers from spoofing `telegram_id` to create fake orders.

### CORS

Allowlist in [`api/main.py`](../api/main.py):
- `https://restaurant.tursunboyev.com`
- `https://super.tursunboyev.com`
- `http://localhost:5173`, `5174`, `3000`
- Plus any in `CORS_EXTRA_ORIGINS` env

`allow_credentials=True`, methods limited to the standard set, headers limited to `Authorization, Content-Type, Accept`.

### File upload safety

`/admin/upload-image`:
- 10 MB max (`_MAX_UPLOAD_SIZE`)
- Extension allowlist: jpg/jpeg/png/webp/gif
- Filename rewritten to `<uuid4>.<ext>` (user-supplied filename ignored)
- Content-type prefix check ("image/")

`DELETE /admin/upload-image?url=`:
- URL must start with `/static/images/products/`
- Filename must match `^[0-9a-f\-]{8,}\.(jpg|jpeg|png|webp|gif)$`
- `os.path.abspath` check ensures resolved path stays inside `UPLOAD_DIR`

### Open security TODOs

- Replace SHA-256 password hashing with bcrypt
- Replace static SECRET_KEY tokens with JWT (`exp` claim, signed)
- Rate-limit `/auth/bot-login` (currently brute-forceable in theory)
- Move secrets out of `.env` into a vault for production

---

## 10. Business rules (single source of truth)

These rules are enforced both server-side (validation in `api/routes/*.py`) and client-side (UI affordances). Server is authoritative.

### Regular orders
- `delivery_type='delivery'` requires `address` and (preferably) `latitude`/`longitude`
- Order total ≥ `restaurant.min_order` (default 30,000 UZS) — only enforced for `delivery_type='delivery'`
- Branch must be open (`work_hours_from ≤ now ≤ work_hours_until` in Asia/Tashkent)

### Catering orders
- Two groups: `somsa` (default min 100, step 1) and `nan` (default min 40, step 40)
- `sum(item.quantity) ≥ group_min` AND `sum % group_step == 0`
- `schedule_date + schedule_time` must be **at least 24 hours from now** (else server returns 400 with hotline message)
- Three delivery sub-modes:
  - `onsite` — bakers travel with tandir; price = `Σ qty × unit_price_usd × CBU rate`
  - `pickup` — customer picks up from restaurant; price = `Σ qty × unit_price_pickup_uzs`
  - `delivery` — Yandex (or fallback distance pricing); price = `Σ qty × unit_price_usd × rate + delivery_fee`
- Payment timing: `now` (manual card or future Click/Payme link) or `later` (cash on delivery / arrangement)
- Confirmation message includes the line: *"Belgilangan vaqtdan taxminan 2 soat oldin somsachilar tayyorgarlik ko'rish uchun yetib borishadi."* (Bakers arrive ~2h early to prep.)

### Time-of-day product availability
- A regular product with `has_time_limit=True` only appears in bot menu when current Asia/Tashkent time ∈ `[available_from, available_until]`
- If `available_from > available_until` (e.g., 22:00–06:00), the range wraps midnight

### Branch selection in bot
- On `/start`, the bot tries (in order): FSM state → DB `User.selected_branch_id` → if exactly 1 active branch in restaurant, auto-pick → else ask for location and show nearest branches
- "📍 Filial tanlash" button forces re-selection (location-based)

### Currency conversion
- USD prices are converted to UZS at order time using `CBU rate (cached 1h)` OR `manual_rate` if `currency_auto=False`
- The rate is **snapshotted** into `Order.currency_rate_snapshot` so historical totals don't drift

---

## 11. Deployment

Server: VPS `65.109.5.207`, Ubuntu, nginx + uvicorn, no Docker currently.

### Layout

```
/opt/restaurant/
├── api/, bot/, courier_bot/, catering_bot/, ...   # Python source
├── admin/dist/                                     # Built React assets
├── super_admin/dist/
├── static/                                         # Uploaded files served by nginx
├── muhsina_somsa.db                                # SQLite
├── api.log, bots.log
└── .venv/                                          # Python virtualenv
```

### Processes

```
.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8086 --workers 2

.venv/bin/python3 -m scripts.run_all_bots
   → spawns subprocess: .venv/bin/python3 -m bot.main          (per restaurant)
   → spawns subprocess: .venv/bin/python3 -m courier_bot.main  (per restaurant)

.venv/bin/python3 -m catering_bot.main                          (single instance, when configured)
```

### nginx role
- TLS termination
- Routes `/api/*` → uvicorn at `:8086`
- Serves `admin/dist/` and `super_admin/dist/` as static
- Serves `/static/` for uploaded images

### Deploy workflow (manual)
```
git push origin main
scp <changed files> root@server:/opt/restaurant/...
ssh server "cd /opt/restaurant/admin && npm run build"  # if frontend changed
ssh server "pkill -9 -f uvicorn; pkill -9 -f bot.main; ..."
ssh server "cd /opt/restaurant && nohup .venv/bin/uvicorn ... &"
ssh server "cd /opt/restaurant && nohup .venv/bin/python3 -m scripts.run_all_bots &"
```

(There's a `deploy.sh` for Docker compose but it's not actively used in production right now.)

### DB migrations
Currently ad-hoc: when `database/models.py` changes, the corresponding `ALTER TABLE` is committed alongside the model change and applied manually:
```bash
ssh server "sqlite3 /opt/restaurant/muhsina_somsa.db 'ALTER TABLE ... ADD COLUMN ...'"
```
No Alembic. This is fine for SQLite + small team but should be revisited if scale grows.

---

## 12. Environment variables

Defined in `.env` (template in `.env.example`). Loaded via `pydantic-settings` (`extra="ignore"`).

```bash
# Telegram
BOT_TOKEN=                  # Default bot token (used by single-bot dev mode)
COURIER_BOT_TOKEN=          # Courier bot
CATERING_BOT_TOKEN=         # Catering notification bot
WEBAPP_URL=                 # Telegram WebApp (mini-app) URL

# Database
DATABASE_URL=sqlite+aiosqlite:///./muhsina_somsa.db

# Auth
SECRET_KEY=                 # All bearer tokens use this
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
SUPER_ADMIN_USERNAME=superadmin
SUPER_ADMIN_PASSWORD=...

# CORS (optional extras)
CORS_EXTRA_ORIGINS=https://example.com

# Misc
DEBUG=True
API_URL=http://localhost:8000
ADMIN_CHAT_ID=

# Legacy / unused but tolerated
ALICE_API_URL=
ALICE_API_KEY=
ALICE_STORE_ID=
YANDEX_DELIVERY_TOKEN=      # Used as fallback when restaurant has no token
```

---

## 13. Known gaps / TODO

| Area | Status |
|---|---|
| Click integration | Schemas + UI ready; no service module / route / webhook yet |
| Payme integration | Schemas + UI ready; same as Click |
| Catering `delivery` subtype → Yandex | Not yet wired (only regular orders dispatch to Yandex) |
| JWT with expiration | Static `SECRET_KEY` token in use |
| Bcrypt password hashing | SHA-256 currently |
| Rate limiting | None |
| Alembic migrations | Manual ALTER TABLE |
| Order idempotency | Not enforced (would matter for AI call agent reconnects) |
| Refunds | Manual ("kassirlar aloqaga chiqishadi") |
| Push to POS (Alice) | Best-effort; errors swallowed |
| End-to-end tests | None |

---

## 14. Conventions

### Code
- Python: PEP 8, type hints used pragmatically, no strict mypy
- All DB access async (`AsyncSession`, `await db.execute(...)`, `await db.commit()`)
- Pydantic 2 models for request/response validation
- React: function components only, hooks for state; zustand for cross-page state with localStorage persist
- Antd's `Form` instances kept stable with `Form.useForm()`; no controlled inputs spread across files
- All Telegram bot text in Uzbek by default (admin can switch to Russian via `Restaurant.language`)

### Money & time
- Money stored as `float`. Trade-off chosen for simplicity; revisit if cents-precision matters
- All times stored as ISO strings or `datetime` UTC; display converted to Asia/Tashkent on the client and in catering schedulers
- Schedule strings are `"HH:MM"` (no seconds), date strings are `"YYYY-MM-DD"`

### Naming
- Snake_case for DB columns and Python identifiers
- camelCase for JSON request/response fields when useful (mostly snake_case in this codebase for backend↔frontend symmetry)
- Uzbek words OK in identifiers when they're domain-specific (e.g., `catering_somsa_min`, `catering_nan_step`)

### Error handling
- API: raise `HTTPException(status, detail)` with Uzbek messages (UI displays them as-is)
- Bots: try/except around outer handler, fall back to a generic apology message
- Best-effort integrations (Alice POS, Yandex when token missing) silently no-op rather than fail the order

---

## 15. Glossary (Uzbek terms used in code/UI)

| Uzbek | English | Meaning |
|---|---|---|
| Somsa | Samsa | Baked filled pastry, the main product |
| Tadbir | Event | Wedding, corporate, etc. — context for catering |
| Catering / Tadbir uchun buyurtma | Catering / Event order | Large pre-scheduled order |
| Tandir | Tandoor | Clay oven for baking, also used as unit (1 tandir = 40 breads) |
| Saboy | Pickup / take-out | Customer picks up the order |
| Onsite (joyiga borib yopish) | On-site baking | Bakers travel to the event with portable tandoor |
| Dastavka | Delivery | Courier/Yandex delivery |
| Filial | Branch | Physical restaurant location |
| Mijoz | Customer | End user |
| Kuryer | Courier | Delivery person |
| Buyurtma / Zakaz | Order | |
| Yetkazib berish | Delivery (verb) | |
| Naqd | Cash | |
| Bog'lam (100 dona) | Bunch (100 pcs) | Catering unit for samsa: `unit_type='bunch_100'` |
| Sozlamalar | Settings | |
| ERI | EDS (Electronic Digital Signature) | Required for Yandex/Click/Payme contracts |
| EDO | EDF (Electronic Document Flow) | Same context |
| YaTT (Yakka Tartibdagi Tadbirkor) | Sole proprietor | Legal entity type |
| OOO / MChJ | LLC | Legal entity type |
| INN | Tax ID | |

---

## 16. Extension points (where AI agents or new features plug in)

If you're an AI extending this system, here's where each kind of change goes:

| You want to... | Modify... |
|---|---|
| Add a new order channel (phone, web form, voice AI) | Create a new client of `POST /orders/` and/or `POST /catering/orders` (with `X-Bot-Secret`). Create users with `telegram_id="<channel>:<id>"` to keep namespaces clean. Reuse all existing validation. |
| Add a new payment provider | Create `api/services/<provider>.py` with `create_invoice(order)` and `handle_callback(payload)`. Add columns to `Restaurant` (e.g., `<provider>_*`). Add a tab in `Settings.jsx` Payments. Expose `POST /payments/<provider>/create` and `POST /payments/<provider>/callback`. Flip `Order.payment_status='paid'` in the callback and call `dispatch_order_to_provider`. |
| Add a new delivery provider | Add a client in `api/services/`. Add a branch in `delivery.py::dispatch_order_to_provider`. Add `<provider>_*` columns to `Restaurant`. Update the `delivery_provider` Select options in `Settings.jsx`. |
| Add a new bot command/flow | Add a state group in `bot/states.py`. Add a handler module under `bot/handlers/` and register the router in `bot/main.py`. **Register state-filtered routers BEFORE generic ones** — global `F.location` handlers (in `start.py`) intercept everything otherwise. |
| Add an admin page | Add the page under `admin/src/pages/`, route in `admin/src/App.jsx`, sidebar item in `admin/src/components/Layout.jsx`. Backend endpoints under `/admin/*` with `Depends(require_restaurant_admin)`. |
| Add a scheduled job | Use `asyncio.create_task` from a long-running process. The catering bot's `scheduler_loop` is the working pattern: compute next run-time in `Asia/Tashkent`, sleep until then, run, loop. Keep these inside the catering_bot or add a dedicated worker process — avoid putting them inside the API process (uvicorn workers don't share state). |

---

## 17. Quick start (read this if you have 60 seconds)

> Multi-tenant Telegram-first food ordering. Each restaurant has its own bot + admin panel. Two order kinds: **regular** (now) and **catering** (≥24h scheduled, USD-priced). Delivery is either **own couriers** (separate Telegram bot) or **Yandex Delivery** (auto, with mock fallback). Payments today are cash + manual card; **Click** and **Payme** are wired schema-wise but not yet routed. **All state lives in SQLite**; **all mutation goes through FastAPI**. Auth is bearer tokens of shape `<SECRET_KEY>` (super) or `<SECRET_KEY>:<restaurant_id>` (admin); catering POST also requires `X-Bot-Secret`. The IDOR guard rejects mismatches between token and `restaurant_id` query param. Add features by writing new routes + a thin client; don't write to the DB directly.

End of document. For onboarding-document checklist (legal docs needed from each restaurant) see [`RESTORAN_HUJJATLARI.md`](./RESTORAN_HUJJATLARI.md). For the AI call-operator integration plan see [`AI_CALL_OPERATOR_PLAN.md`](./AI_CALL_OPERATOR_PLAN.md).
