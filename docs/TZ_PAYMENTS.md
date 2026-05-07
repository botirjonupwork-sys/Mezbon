# Muhsina Dollar Somsa — To'lov tizimi TZ

> Loyihaning to'lov qismi to'liq texnik tavsifi — boshqa AI yoki dasturchi bilan maslahatlashish uchun. **Ushbu hujjatda faqat to'lov bilan bog'liq qismlar yoritilgan.**

---

## 1. Umumiy ma'lumot

Loyihada **2 ta turdagi** to'lov tizimi bor:

| Tur | Maqsad | Yo'l |
|---|---|---|
| **A. SaaS Billing** | Restoranlar platformaga tarif uchun to'laydi (oylik) | `/payments/create-invoice` → Click/Payme webhook |
| **B. Customer Payments** | Mijozlar buyurtma uchun to'laydi (har zakaz) | Telegram Native Payments |

**Pul birligi**: hech qachon `float`. Har joyda **`int tiyin`** (1 so'm = 100 tiyin). Click/Payme API'lari ham tiyin bilan ishlaydi.

---

## 2. Database modellari

### 2.1 `Payment` (SaaS billing)

`database/models.py:391`

```python
class Payment(Base):
    """SaaS tarif uchun to'lov yozuvi."""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=True)
    amount_tiyin = Column(Integer, nullable=False)        # int — float emas
    status = Column(String, default="pending")             # pending | success | failed
    provider = Column(String)                              # click | payme
    external_id = Column(String)                           # provayder tx ID
    payment_url = Column(String)                           # mijoz to'lov sahifasi
    merchant_trans_id = Column(String, unique=True)        # idempotency key
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime)
```

### 2.2 `CommissionPayment` (har tranzaksiya komissiyasi)

`database/models.py:533`

```python
class CommissionPayment(Base):
    """Restoran tomonidan platformaga to'langan komissiya yozuvi.

    Ikki holat:
    1. Periodik — super-admin har oy oxirida hisoblaydi
    2. Tranzaksiya bo'yicha — har Telegram payment muvaffaqiyatli bo'lganda
    """
    __tablename__ = "commission_payments"

    id = Column(Integer, primary_key=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    amount = Column(Float, nullable=False)             # komissiya summasi (so'm)
    commission_percent = Column(Float, default=0.0)
    orders_revenue = Column(Float, default=0.0)
    period_from = Column(DateTime)
    paid_at = Column(DateTime, default=datetime.utcnow)
    note = Column(String)
    status = Column(String, default="confirmed")
    # Faza 4: tranzaksiya bo'yicha yozuv
    order_id = Column(Integer, ForeignKey("orders.id"))
    payment_charge_id = Column(String, index=True)     # Telegram tx ID
```

### 2.3 `Order` to'lov maydonlari

`database/models.py:280-310`

```python
# Asosiy
total_price = Column(Float, nullable=False)            # mahsulotlar narxi (so'm)
delivery_fee = Column(Float, default=0)                # yetkazib berish
service_type = Column(String, default="delivery")      # delivery | onsite_catering | pickup

# To'lov holati
payment_method = Column(String, default="cash")        # cash | card | telegram
payment_timing = Column(String, default="later")       # now | later
payment_status = Column(String, default="pending")     # pending | paid | partial

# Faza 4: Telegram Native Payments
payment_provider = Column(String)                      # click | payme
payment_charge_id = Column(String, index=True)         # Telegram tx (idempotency)
paid_amount_tiyin = Column(Integer, default=0)
is_prepayment = Column(Boolean, default=False)
prepayment_percent = Column(Integer)                   # snapshot
```

### 2.4 `Restaurant` to'lov sozlamalari

```python
# Click Merchant API
click_merchant_id = Column(String)
click_service_id = Column(String)
click_secret_key = Column(String)
click_enabled = Column(Boolean, default=False)

# Payme Merchant API
payme_merchant_id = Column(String)
payme_secret_key = Column(String)
payme_enabled = Column(Boolean, default=False)

# Catering xizmat haqi (onsite uchun)
catering_service_fee = Column(Float, default=0.0)

# Prepayment limit — bu summadan oshsa oldindan to'lov majburiy
prepayment_required_above = Column(Float, default=0.0)

# Karta (manual catering to'lov)
catering_payment_card = Column(String)
catering_payment_owner = Column(String)
payment_card_number = Column(String)
payment_card_name = Column(String)
payment_card_bank = Column(String)
```

### 2.5 `Plan` to'lov maydonlari

```python
monthly_price = Column(Float, default=0.0)             # so'm
commission_percent = Column(Float, default=0.0)        # 0..100
min_prepayment_percent = Column(Integer, default=30)   # Pro/Basic uchun
```

---

## 3. SaaS Billing — restoran platformaga to'laydi

### 3.1 Oqim

```
Restoran admin → Tariflar sahifasi → "Pro" tarifni tanlaydi → "Click" yoki "Payme"
   ↓
POST /payments/create-invoice {plan_id, provider}
   ↓
api/services/billing.py:create_payment_record()
   - merchant_trans_id avtomatik (`r{rid}-p{pid}-{hash}`)
   - URL yaratiladi (Click hosted page yoki Payme checkout)
   - Mock rejim: `https://mock.payments.local/...` (test uchun)
   ↓
Mijozga URL qaytadi → bot/web → Click/Payme sahifasiga yo'naltiriladi
   ↓
Mijoz to'lovni amalga oshiradi → Click/Payme webhook bizga yuboradi
   ↓
POST /payments/click/webhook (form-urlencoded)
   - IP allow-list tekshiruv
   - MD5 signature tekshiruv
   - Action: PREPARE (0) yoki COMPLETE (1)
   ↓
mark_payment_success() → Restaurant.plan_id va plan_expires_at = max(now, current) + 30 days
```

### 3.2 Click webhook

`api/services/billing.py:handle_click_webhook()`

**Algoritm**:
1. IP allow-list tekshiruv (`CLICK_ALLOWED_IPS` env)
2. Required maydonlarni olish: `merchant_trans_id, sign_string, action, amount`
3. DB'dan Payment topish
4. Signature qayta hisoblash MD5'da: `secret_key + click_trans_id + service_id + merchant_trans_id + amount + action + sign_time`
5. Compare → bad → `error: -1, "Bad sign"`
6. Amount mismatch → `error: -2`
7. Action 0 (PREPARE) → response yuborish (oddiy bron)
8. Action 1 (COMPLETE) → `mark_payment_success` → plan extend → 30 day cycle

**Idempotent**: agar `payment.status == "success"` bo'lsa, qaytadan kelgan webhook xato yuzasiga olib kelmaydi — mavjud success response qaytariladi.

### 3.3 Payme webhook (JSON-RPC)

`api/routes/billing.py:payme_webhook()`

5 ta method:
- `CheckPerformTransaction` — to'lov mumkinmi
- `CreateTransaction` — bron yaratish
- `PerformTransaction` — pulni hisobga olish (success)
- `CancelTransaction` — bekor qilish
- `CheckTransaction` — holatni tekshirish

**Auth**: HTTP Basic Auth `merchant_id:key` (Payme bizga shu credential bilan ulanadi).

### 3.4 Mock mode

Click yoki Payme key bo'lmasa (dev/test uchun):
```python
if is_mock_mode(rest, provider):
    payment.payment_url = "https://mock.payments.local/click/r1-p2-1497e8b5f3"
    payment.status = "pending"
```

Test uchun super-admin `POST /payments/mock/complete` chaqiradi → status='success'.

### 3.5 API endpoints

```
GET   /admin/billing/plans            Tariflar (features array bilan)
GET   /admin/billing/payments         Restoran to'lov tarixi
POST  /payments/create-invoice        Yangi faktura yaratish
POST  /payments/click/webhook         Click PREPARE/COMPLETE
POST  /payments/payme/webhook         Payme JSON-RPC
POST  /payments/mock/complete         Test uchun mock complete
```

---

## 4. Telegram Native Payments — Mijoz buyurtma uchun to'laydi

### 4.1 Arxitektura — 3 nuqtali zanjir

```
1. PREPARE (Bot → FastAPI)
   POST /payments/telegram/prepare {order_id, provider}
   → InvoicePayload {prices, provider_token, total_tiyin, ...}

2. PRE_CHECKOUT (Telegram → Bot → FastAPI)
   POST /payments/telegram/precheck {order_id}
   → {ok: bool, error_message, reason_code}
   - Resurs (mashina) tekshiruvi
   - Mashina band bo'lib qolsa Telegram to'lovni rad etadi

3. CONFIRM (Telegram → Bot → FastAPI)
   POST /payments/telegram/confirm {order_id, amount_tiyin, charge_id}
   → Order paid + book_car_for_order() + CommissionPayment yozuvi
```

### 4.2 To'lov hisob-kitobi

`api/services/telegram_payments.py:calculate_order_payment()`

```python
items_total   = order.total_price                # mahsulotlar
delivery_fee  = order.delivery_fee               # Haversine bo'yicha
service_fee   = restaurant.catering_service_fee  # FAQAT service_type='onsite_catering'
grand_total   = items_total + delivery_fee + service_fee

# Prepayment qoidasi (faqat Basic/Pro tarifda):
if plan.slug in ("basic", "pro") and grand_total >= restaurant.prepayment_required_above:
    pct = plan.min_prepayment_percent           # default 30%
    payable_now = grand_total * pct / 100
    is_prepayment = True
else:
    payable_now = grand_total
```

**Misol**:
- Order: 300,000 so'm + 20,000 delivery = 320,000
- Restoran limit: 200,000 (yuqori summa)
- Pro tarif: min_prepayment_percent = 30
- Mijoz to'laydi: **96,000 so'm** (oldindan), keyingisi yetkazib berilganda

### 4.3 InvoicePayload schema

`api/services/telegram_payments.py:InvoicePayload`

```python
@dataclass
class InvoicePayload:
    order_id: int
    title: str                   # "Buyurtma #142"
    description: str             # "Muhsina Dollar Somsa. Jami: 87,000 so'm"
    currency: str                # 'UZS'
    prices: list[LabeledPriceItem]  # har item: label + amount_tiyin
    payload: str                 # 'order_142' (idempotency uchun)
    provider_token: str          # Telegram payment provider token
    total_tiyin: int             # umumiy to'lanadigan summa
    is_prepayment: bool
    prepayment_percent: Optional[int]
    full_total_tiyin: int        # to'liq summa (info uchun)
```

### 4.4 Provider token

Telegram'ga to'lov gateway (Click/Payme) ulash uchun **provider token** kerak. Bu token **bot token'dan ALOHIDA** olinadi:

```
@BotFather → /mybots → bot tanlang → Payments → provider tanlang
```

Provider token format: `<merchant_id>:TEST:<key>` yoki `<merchant_id>:LIVE:<key>`.

**Saqlash joyi**:
1. **Restoran sozlamasida** (afzal): `Restaurant.pos_config["telegram_provider_token_<provider>"]`
2. **Env** (fallback): `TELEGRAM_PROVIDER_TOKEN_CLICK`, `TELEGRAM_PROVIDER_TOKEN_PAYME`

Resolver: `_resolve_provider_token()` (api/services/telegram_payments.py)

### 4.5 Pre-checkout — oxirgi marta resurs tekshiruv

`api/services/telegram_payments.py:precheck_invoice()`

Telegram bizdan to'lov o'tkazilishini tasdiqlashni so'raydi (`pre_checkout_query`). Biz **10 sekund** ichida `ok=True/False` qaytarishimiz kerak.

**Tekshiruvlar**:
- Order topiladimi
- `payment_status != "paid"` (idempotency)
- Status `cancelled` emas
- Delivery turi bo'lsa: filial mashinalari hali bo'shmi (`find_available_car`)

Mashina band bo'lib qolgan bo'lsa → `ok=False, error_message="Kechirasiz, mashinalarimiz to'liq band..."` → Telegram to'lovni rad etadi.

### 4.6 Successful payment — yakuniy zanjir

`api/services/telegram_payments.py:confirm_payment()`

Idempotent (Telegram event takrorlanishi mumkin).

**4 qadam**:
1. **Order yangilash**:
   - `payment_status = "paid"` (yoki `"partial"` agar prepayment)
   - `status = OrderStatus.confirmed` → POS dispatch trigger
   - `payment_charge_id`, `paid_amount_tiyin`, `is_prepayment` saqlash

2. **Mashina rasman band**: `book_car_for_order(order)`
   - Faqat delivery uchun
   - `DeliveryCarBooking` yaratiladi
   - Sig'im to'lganda log_critical (admin manual aralashish kerak)

3. **Komissiya yozuvi**: agar `restaurant.commission_percent > 0`:
   ```python
   commission = paid_uzs * commission_percent / 100
   CommissionPayment(
       restaurant_id, amount=commission, ..., 
       order_id, payment_charge_id, status="confirmed"
   )
   ```

4. **POS dispatch**: Order.status = confirmed bo'lsa, asynchronous:
   - `pos_adapter.dispatch_order()` chaqiriladi
   - NeonAlisa Cloud / Bluetooth printer'ga chek yuboriladi

### 4.7 API endpoints

| Endpoint | Maqsad | Auth |
|---|---|---|
| `POST /payments/telegram/summary` | UI ga ko'rsatish (chek emas) | X-Bot-Secret |
| `POST /payments/telegram/prepare` | Invoice payload + provider_token | X-Bot-Secret |
| `POST /payments/telegram/precheck` | pre_checkout resurs tekshiruv | X-Bot-Secret |
| `POST /payments/telegram/confirm` | Order paid + car booked + commission | X-Bot-Secret |

Bot uchun yopiq endpoint'lar — **`X-Bot-Secret`** header (env `BOT_API_SECRET` yoki fallback `SECRET_KEY`).

### 4.8 Bot handlerlari (aiogram 3)

`bot/handlers/payments.py`

```python
# 1. Mijoz "💳 Karta" tanladi → tasdiqlangach inline tugma
@router.callback_query(F.data.startswith("tgpay:"))
async def on_pay_callback(callback):
    """tgpay:<order_id>:<provider>"""
    # send_invoice_for_order chaqiradi

async def send_invoice_for_order(message, order_id, provider="click"):
    payload = await api_client.tg_payment_prepare(order_id, provider)
    await message.bot.send_invoice(
        chat_id=...,
        title=payload['title'],
        description=payload['description'],
        payload=payload['payload'],          # 'order_<id>'
        provider_token=payload['provider_token'],
        currency='UZS',
        prices=[LabeledPrice(...) for p in payload['prices']],
    )

# 2. pre_checkout_query
@router.pre_checkout_query()
async def on_pre_checkout(query):
    order_id = int(query.invoice_payload.split('_')[1])
    result = await api_client.tg_payment_precheck(order_id)
    await query.answer(ok=result['ok'], error_message=result.get('error_message'))

# 3. successful_payment
@router.message(F.successful_payment)
async def on_successful_payment(message):
    sp = message.successful_payment
    order_id = int(sp.invoice_payload.split('_')[1])
    await api_client.tg_payment_confirm(
        order_id=order_id,
        amount_tiyin=sp.total_amount,
        provider="click",
        telegram_payment_charge_id=sp.telegram_payment_charge_id,
        provider_payment_charge_id=sp.provider_payment_charge_id,
    )
    await message.answer("✅ To'lov qabul qilindi!")
```

### 4.9 Order flow (mijoz tomonidan)

```
1. Mijoz menyu → savatga qo'shish → "Buyurtma berish"
2. Manzil, telefon → To'lov turi tanlash
3. "💵 Naqd" yoki "💳 Karta" tanlanadi
4. Tasdiqlash → Order yaratiladi (status=pending, payment_status=pending)
5a. Naqd tanlasa: "Zakaz qabul qilindi! Tez orada xabar beramiz" — odatdagi flow
5b. Karta tanlasa:
    "Zakaz qabul qilindi! Summa: 87,000 so'm
     [💳 To'lashga o'tish (Click)]
     [💳 To'lashga o'tish (Payme)]"
6. Tugma bosilsa → tg_payment_prepare → bot.send_invoice
7. Telegram payment widget ochiladi
8. Mijoz kartasini kiritadi
9. Telegram → bot: pre_checkout_query → /precheck → ok
10. Telegram tranzaksiyani amalga oshiradi
11. Telegram → bot: successful_payment → /confirm
12. Order paid + mashina band + komissiya yozuvi
13. Mijozga: "✅ To'lov qabul qilindi! Mashina #3 yo'lda"
```

---

## 5. Idempotency va xavfsizlik

### 5.1 Idempotency

| Payment turi | Idempotency mexanizmi |
|---|---|
| **SaaS Click** | `Payment.merchant_trans_id` UNIQUE — bir xil tx 2 marta bo'lsa, mavjud holat qaytariladi |
| **SaaS Payme** | `external_id` orqali payme tx ID, JSON-RPC method'larda check |
| **Telegram order** | `Order.payment_charge_id` UNIQUE — bir xil charge_id 2 marta confirm chaqirilsa, "duplicate_event" log qiladi va silently OK qaytaradi |

### 5.2 Xavfsizlik

- **Click webhook IP allow-list** (`CLICK_ALLOWED_IPS` env)
- **Click MD5 signature** (har action uchun alohida algoritm)
- **Payme Basic Auth** (`merchant_id:key`)
- **Bot↔FastAPI** `X-Bot-Secret` header
- **Telegram provider token** har bot va har provider uchun alohida
- **Float xato yo'q** — har joyda `int tiyin`
- **`log_critical`** har payment xatosida → Telegram alert (debounced)

---

## 6. Hozirgi holat (2026-04-30)

### 6.1 Tayyor

- ✅ DB modellari (Payment, CommissionPayment, Order to'lov maydonlari)
- ✅ SaaS Click webhook handler (PREPARE + COMPLETE, signature, IP allow-list)
- ✅ SaaS Payme JSON-RPC dispatcher (5 method)
- ✅ Mock mode (Click/Payme keysiz test)
- ✅ Telegram Native Payments to'liq zanjir (prepare → precheck → confirm)
- ✅ Prepayment qoidasi (Basic/Pro + restoran limiti)
- ✅ Catering service_fee (onsite_catering uchun)
- ✅ CommissionPayment har tx'da yoziladi
- ✅ Bot handlers (pre_checkout_query, successful_payment, tgpay callback)
- ✅ Bot UI: "💳 To'lashga o'tish (Click/Payme)" inline tugmalar
- ✅ Tiyin matematika (1 so'm = 100 tiyin, hech qanday float)
- ✅ Idempotency

### 6.2 Hali sozlanmagan

- 🔴 **Click provider token** — BotFather'dan kerak (foydalanuvchi qiladi)
- 🔴 **Payme provider token** — BotFather'dan kerak
- 🔴 **Click merchant key** — Click bilan shartnoma kerak (haqiqiy webhook uchun)
- 🔴 **Payme merchant key** — paycom.uz da ariza kerak
- 🟡 **Restaurant Settings UI** — `catering_service_fee`, `prepayment_required_above` maydonlari hali admin panelda yo'q (kod bor, UI qoldirilgan)
- 🟡 **Refund** — to'liq qaytarish endpointi yo'q
- 🟡 **Partial payment finalization** — prepayment'dan keyin qolgan summani to'lash flow'i hali qurilmagan

---

## 7. Provider Token sozlash bo'yicha qo'llanma

### 7.1 BotFather orqali

```
1. @BotFather ni Telegram'da oching
2. /mybots
3. Bot tanlang (masalan @videoSearchbotbot)
4. Payments tugmasini bosing
5. Provider tanlang:
   - Click Test → real pul yo'q, sandbox
   - Click Live → real to'lov (Click bilan shartnoma kerak)
   - Payme Test/Live
6. Provider o'z formasini ochadi (merchant_id, key)
7. Token qaytariladi: <merchant_id>:TEST:<long_key>
```

### 7.2 Tokenni serverga yozish

**A) Restaurant darajada** (har restoran o'zining):
```sql
UPDATE restaurants
SET pos_config = json_set(
    coalesce(pos_config, '{}'),
    '$.telegram_provider_token_click', '12345:TEST:abc...'
)
WHERE id = 1;
```

Yoki [Settings.jsx UI](admin/src/pages/Settings.jsx) orqali (UI qo'shish kerak).

**B) Server-wide default** (.env):
```env
TELEGRAM_PROVIDER_TOKEN_CLICK=12345:TEST:abc...
TELEGRAM_PROVIDER_TOKEN_PAYME=67890:TEST:xyz...
```

### 7.3 Sinov

```bash
# 1. Bot orqali yangi zakaz berib, "💳 Karta" tanlang
# 2. "💳 To'lashga o'tish (Click)" tugmasini bosing
# 3. Telegram payment widget ochilishi kerak
# 4. Test rejimda: 8600 0000 0000 0000 / 12/25 / 123 (har xil test card'lar)
# 5. Pre-checkout → confirm → "✅ To'lov qabul qilindi!"
# 6. Admin panelda Order.payment_status='paid', commission_payments yangi yozuv
```

---

## 8. Test scenariy (mock mode)

### 8.1 Click mock cycle

```bash
# 1. Faktura yaratish
curl -X POST /payments/create-invoice \
  -d '{"plan_id": 2, "provider": "click"}' \
  -H "Authorization: Bearer <admin_token>" \
  -H "X-Restaurant-Context: 1"
# → {payment_id, merchant_trans_id, payment_url: "https://mock.payments.local/..."}

# 2. Mock complete (test rejim)
curl -X POST /payments/mock/complete \
  -d '{"merchant_trans_id": "r1-p2-abc..."}' \
  -H "Authorization: Bearer <admin_token>"
# → {success: true}

# 3. Verify
sqlite3 db "SELECT status, paid_at FROM payments;"
sqlite3 db "SELECT plan_id, plan_expires_at FROM restaurants WHERE id = 1;"
```

### 8.2 Telegram payment cycle (real Telegram bilan)

```
1. Bot'da yangi zakaz bering, "💳 Karta" tanlang
2. Inline "💳 To'lashga o'tish (Click)" tugmasini bosing
3. Telegram widget'da TEST card raqamini kiriting
4. To'lovni tasdiqlang
5. Bot: "✅ To'lov qabul qilindi! Mashina #X band qilindi"
6. DB tekshiruvi:
   - orders.payment_status = 'paid'
   - delivery_car_bookings yangi yozuv
   - commission_payments yangi yozuv
```

---

## 9. Fayl yo'llari (xulosa)

```
api/services/billing.py           # SaaS Click/Payme + create_payment_record + mark_success
api/services/telegram_payments.py # Telegram Native Payments (prepare/precheck/confirm)
api/routes/billing.py             # SaaS API + webhook handlers (Click + Payme)
api/routes/telegram_payments.py   # /payments/telegram/* endpoints
bot/handlers/payments.py          # aiogram payment handlers
bot/api_client.py                 # tg_payment_* helper functions
docs/TZ_PAYMENTS.md               # bu hujjat
```

---

## 10. Eslatmalar

### Pul ehtiyotkori bilan

- **Hech qachon `float * 100`** — har doim `int(round(uzs * 100))`
- **Click va Payme tiyin** ishlatadi — bizning `Payment.amount_tiyin` ham int
- **Telegram `LabeledPrice.amount`** ham minimal birlikda (UZS uchun tiyin)

### Webhook security

- Click webhook'ni bizdan tashqari kim ham chaqira oladi (HTTP)
- IP allow-list + MD5 signature himoyaning **ikki qatlami**
- Production'da `CLICK_ALLOWED_IPS=` ni Click'ning haqiqiy IPlari bilan to'ldiring

### Idempotency haqiqiy hayotda

- Telegram `successful_payment` event'ni qayta-qayta yuborishi mumkin (network)
- Click/Payme webhook'ni qayta yuborishi mumkin
- Har joyda **unique constraint** + early-return mantiq bor

### Failure mode

- Telegram payment muvaffaqiyatli, lekin server xato → mijoz `payment_charge_id`'ni admin'ga yuboradi (UI'da ko'rsatildi)
- Mashina band qilinmadi (capacity to'la) → `log_critical` → admin manual aralashishi kerak (CommissionPayment yozuvi yaratilgan, lekin booking yo'q — Bot xabar yuboradi)

---

**Asosiy chiqishlar boshqa AI bilan maslahatlashish uchun**:

1. **Idempotent webhook design'i to'g'ri qilinganmi?** — Click/Payme retry'larida double-charge xavfi
2. **Tiyin overflow** — Postgres `INTEGER` 32-bit (max ~2.1B). UZS tiyin sifatida 2.1B = 21M so'm = $1750. Bu yetarli, lekin BIGINT bo'lishi xavfsizroq
3. **Telegram WebApp** vs **bot.send_invoice()** — qaysi UX yaxshi?
4. **Click provider token** test rejimi haqiqiy pul olishi mumkinmi yoki sandbox?
5. **Refund** UI — admin panelda qanday ko'rinishi kerak?
