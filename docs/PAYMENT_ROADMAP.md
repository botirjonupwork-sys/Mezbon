# 💳 To'lov tizimini real ishga tushirish — TZ va Roadmap

> **Maqsad**: SaaS tarif to'lovlari va mijoz buyurtma to'lovlari haqiqiy pul bilan ishlasin.
> **Holat (2026-05-01)**: Mock mode + Telegram Native Payments framework tayyor. Provider tokenlari, real Click/Payme merchant kalitlari, va bir nechta asosiy oqim qoldirilgan.

---

## 📊 Hozirgi holat — nima tayyor

| # | Komponent | Holat |
|---|---|---|
| 1 | DB modellari (Payment, CommissionPayment, Order to'lov maydonlari) | ✅ |
| 2 | Click webhook handler (signature, IP allow-list, idempotent) | ✅ |
| 3 | Payme JSON-RPC webhook (5 method, Basic auth) | ✅ |
| 4 | Mock rejim (test uchun key'siz) | ✅ |
| 5 | Telegram Native Payments full chain (prepare → precheck → confirm) | ✅ |
| 6 | Bot UI: 💵 Naqd / 💳 Karta tugmalari | ✅ |
| 7 | Catering "card+now" → Telegram invoice | ✅ |
| 8 | `mark_payment_success` → auto-apply upgrade | ✅ |
| 9 | Tarif Variant A (immediate freeze) / Variant B (queued) | ✅ |
| 10 | APScheduler 10:00 daily check (grace, suspend, frozen, queued) | ✅ |
| 11 | Telegram alerts (success, error, daily summary) | ✅ |
| 12 | `is_verified` gate (INN tasdiqlanmagan → 403) | ✅ |
| 13 | Subscription middleware (suspended → 402) | ✅ |
| 14 | Idempotency (Payment.merchant_trans_id, Order.payment_charge_id UNIQUE) | ✅ |
| 15 | CommissionPayment har tx'da yoziladi | ✅ |
| 16 | Audit log (SecurityLog, SuperAdminAction) | ✅ |
| 17 | Tiyin matematika (1 so'm = 100 tiyin, int) | ✅ |

**Mavjud arxitektura sof va tayyor — endi real provayder kalitlari + qoldirilgan oqimlar kerak.**

---

# 🗺️ Roadmap — 7 ta faza

## 🔴 FAZA 1 — Provider Setup (KRITIK, BLOKLOVCHI)

**Maqsad**: Real to'lov amalga oshirilishi uchun zarur huquqiy va texnik konfiguratsiya.

### 1.1 Click Merchant ulanishi
- [ ] **Click bilan shartnoma tuzish** (yuridik shaxs sifatida — Restaurant.inn = 9 raqam)
  - merchant.click.uz da ariza
  - INN, kompaniya nomi, bank rekvizitlari
  - Komissiya: UzCard/Humo 0.8%, Visa/Mastercard 2.5%
  - Tasdiqlash: 1-3 ish kuni
- [ ] **Click test va live merchant key'larini olish**:
  - `merchant_id` (sonli)
  - `service_id` (sonli)
  - `secret_key` (32+ belgi)
  - Test rejim: real pul yo'q, sandbox kartalari
- [ ] **Webhook URL'ni Click panelda ro'yxatdan o'tkazish**:
  - `https://api.tursunboyev.com/payments/click/webhook`
  - **HTTPS majburiy** (✅ bizda nginx + Let's Encrypt)
- [ ] **Click haqiqiy IP'larini olish** va `.env`'da yozish:
  ```
  CLICK_ALLOWED_IPS=185.232.66.0/24,...
  ```

### 1.2 Payme Merchant ulanishi
- [ ] **Payme bilan shartnoma**: business.paycom.uz
  - INN + bank rekvizitlari
  - Cashbox ID + Merchant Key
  - Komissiya: 0.8-1.2%
- [ ] **Test va live cashbox** o'rnatish
- [ ] **Webhook URL** Payme panelda: `https://api.tursunboyev.com/payments/payme/webhook`
- [ ] **Basic auth credentials** (Paycom:<merchant_key>) himoyalash

### 1.3 Telegram Native Payments — Provider Tokenlar
**Bu eng tezkor qadam — Click/Payme shartnomasiz ham TEST tokenni olish mumkin.**

- [ ] **BotFather'dan token olish** (har bot uchun alohida):
  ```
  /mybots → @videoSearchbotbot → Payments
  Click Test → token: 12345:TEST:abc...
  Payme Test → token: 67890:TEST:xyz...
  ```
- [ ] **Tokenni saqlash**:
  - **A) `.env` server-wide**: `TELEGRAM_PROVIDER_TOKEN_CLICK=...`
  - **B) Per-restaurant**: `Restaurant.pos_config["telegram_provider_token_click"]`
- [ ] **Sinov**: Telegram'da invoice yaratish, test cardlar bilan to'lash:
  - Click test: `8600 0000 0000 0000` / `12/25` / `123`

### 1.4 Restaurant onboarding
- [ ] **Admin panelda Click/Payme kalit kiritish UI** (✅ qisman bor — Settings.jsx)
- [ ] **"Test rejim" / "Live rejim"** toggle (har restoran o'zi tanlaydi)
- [ ] **Webhook URL'ni admin panelda ko'rsatish** (copy tugma bilan)

**Yakuniy natija**: bitta restoran (Muhsina Dollar) real Click test rejimida zakaz oladi va Telegram orqali to'lov amalga oshiradi.

---

## 🟠 FAZA 2 — Provayder webhook qayta ishlash

**Maqsad**: Click va Payme webhook'larni production-grade qilish.

### 2.1 Click webhook to'liq sinov
- [ ] PREPARE va COMPLETE actionlari ishlashi
- [ ] Signature mismatch → 401 + audit log + Telegram alert
- [ ] IP allowlist tashqarisidan → 403 + audit log
- [ ] Amount mismatch → -2 + Payment.failed
- [ ] Idempotency (bir xil tx 2 marta) — already success qaytaradi
- [ ] Click cancel webhook (REVERSE) — refund flow uchun
- [ ] Click status check (test endpoint)

### 2.2 Payme webhook to'liq sinov
- [ ] CheckPerformTransaction
- [ ] CreateTransaction
- [ ] PerformTransaction
- [ ] CancelTransaction (cancel/refund)
- [ ] CheckTransaction
- [ ] Basic auth tekshiruvi
- [ ] JSON-RPC error code'lari to'g'ri qaytariladi

### 2.3 Reconciliation (mosligi)
- [ ] **Daily reconciliation script**: bizning Payment vs Click/Payme yozuvlari
- [ ] Topilgan farqlar uchun audit + alert
- [ ] Manual fix UI (super-admin)
- [ ] Settlement report (har oyda)

### 2.4 Webhook security
- [ ] Rate-limit har webhook endpoint (60/min)
- [ ] Replay attack himoyasi (timestamp window 5 min)
- [ ] Body size limit (10KB)
- [ ] HTTPS enforce (✅ nginx orqali)

---

## 🟡 FAZA 3 — Refund va Cancel oqimi

**Maqsad**: To'lovni qaytarish va bekor qilish UI + backend.

### 3.1 Backend
- [ ] `Refund` model (Payment'ga FK, amount_tiyin, reason, status)
- [ ] `POST /admin/billing/refund` (super-admin)
- [ ] `POST /admin/orders/{id}/refund` (restaurant admin)
- [ ] Click `REVERSE` action chaqirish
- [ ] Payme `CancelTransaction` chaqirish
- [ ] CommissionPayment qaytarish (orders_revenue manfiy)
- [ ] Restaurant.plan_expires_at qisqartirish (SaaS refund'da)
- [ ] Order.status = `cancelled` + booking release

### 3.2 Order avtomatik refund
- [ ] Order.status = `cancelled` bo'lganda payment paid bo'lsa → refund trigger
- [ ] Cancellation policy (kelajakdan 24 soat, x soatdan keyin no-refund)
- [ ] Partial refund (zakaz 50% tayyor → 50% qaytarish)

### 3.3 UI
- [ ] Restaurant admin: "Zakaz" → "Bekor qilish + qaytarish" tugmasi
- [ ] Super-admin: Payment list → "Refund" tugma
- [ ] Customer bot: status="cancelled" → "Pulingiz qaytariladi (1-3 ish kuni)"

---

## 🟢 FAZA 4 — Mijoz tomondan UX

**Maqsad**: Customer payment experience to'liq.

### 4.1 To'lov xato bo'lganda
- [ ] Bot: "❌ To'lov o'tmadi — qaytarmoqchimisiz?" + Retry tugma
- [ ] Sabab ko'rsatish (insufficient funds, expired card, ...)
- [ ] Timeout handling (Telegram 10s pre_checkout)

### 4.2 Status tracking
- [ ] `GET /orders/{id}/payment-status` — real-time holat
- [ ] Bot: "Mening zakazlarim" → har zakaz status (paid/pending/refunded)
- [ ] Web app (kelajakda): Payment receipt sahifasi

### 4.3 Chek va kvitansiya
- [ ] **Fiscal chek** — NeonAlisa Cloud (✅ bizda POS adapter bor!)
  - Order paid → POS dispatch → fiscal chek printer'ga
  - Mijozga PDF chek (telegram orqali)
- [ ] **Email/SMS chek** (kelajakda)

### 4.4 Multi-currency
- [ ] Catering USD narx ham qo'llab-quvvatlangan (✅ bor)
- [ ] To'lov UZS'da, lekin invoice'da USD ekvivalent ko'rinishi
- [ ] Currency rate snapshot (Order.currency_rate_snapshot ✅ bor)

---

## 🔵 FAZA 5 — Restoran moliyaviy hisob

**Maqsad**: Restoran to'plagan pulni o'ziga o'tkazish.

### 5.1 Settlement
- [ ] **Click avtomatik settlement**: Click har kuni/hafta restoran kartasiga o'tkazadi (Click konfiguratsiyasi)
- [ ] **Payme avtomatik settlement**: Payme settings'da
- [ ] Bizning platforma — faqat hisob beradi (komissiya hisobi)
- [ ] Restaurant.bank_account_number maydoni (kelajakda)

### 5.2 Settlement reporting
- [ ] `GET /admin/billing/settlement` — bu davrda restoran qancha pul olgan
- [ ] Excel/PDF eksport
- [ ] Komissiya hisoboti (jami, har provayder, har tarif)

### 5.3 Super-admin Financial Dashboard
- [ ] Jami platforma daromadi (har oyda)
- [ ] Tarif bo'yicha taqsimot
- [ ] Eng yuqori daromadli restoranlar (top-10)
- [ ] To'lanmagan komissiyalar (alert)
- [ ] Eksport (CSV/Excel)

---

## 🟣 FAZA 6 — Soliq va huquqiy

**Maqsad**: O'zR qonunchiligiga moslashtirish.

### 6.1 Fiscal compliance
- [ ] **Soliq qo'mitasi fiskal modul** (Cloud yoki Online ККМ)
  - NeonAlisa Cloud (✅ POS adapter tayyor)
  - Yoki MyCRM, alternativ provayder
- [ ] Har order paid → fiskal chek avtomatik
- [ ] Fiskal QR kod mijozga
- [ ] Soliq inspektorlari uchun audit log

### 6.2 VAT (QQS)
- [ ] QQS hisoblash (12%)
- [ ] QQS to'lovchi vs to'lovchi-emas restoranlar
- [ ] Receipt'da QQS ajratilishi

### 6.3 INN to'liq verifikatsiyasi
- [ ] Soliq qo'mitasi API ulanishi (`api.soliq.uz`) — ✅ placeholder bor
- [ ] Real API'dan tashkilot nomi va turi
- [ ] Auto `is_verified=True` agar API muvaffaqiyatli

### 6.4 Hujjatlar
- [ ] Maxfiylik siyosati (Privacy Policy)
- [ ] Foydalanish shartlari (Terms of Service)
- [ ] Qaytarish siyosati (Refund Policy)
- [ ] Mijoz akseptini saqlash (Order.terms_accepted_at)

---

## 🟤 FAZA 7 — Analytics va Monitoring

**Maqsad**: Moliyaviy KPI'larni kuzatish va optimallashtirish.

### 7.1 Payment Analytics
- [ ] Conversion rate (zakaz → to'langan zakaz)
- [ ] Average order value (AOV)
- [ ] Failed payments (sabab bo'yicha)
- [ ] Provayder taqqosi (Click vs Payme)
- [ ] Vaqt bo'yicha grafiklar (soat, kun, oy)

### 7.2 Real-time Monitoring
- [ ] Webhook latency (P50/P95/P99)
- [ ] To'lov muvaffaqiyat ko'rsatkichi
- [ ] Anomaliyani aniqlash (suddenly high failure rate → alert)
- [ ] Provider availability (Click/Payme down detection)

### 7.3 Alerting
- [ ] **Yuqori failure rate** (>5% bir soatda) → Telegram + email
- [ ] **Bitta foydalanuvchidan ko'p urinish** (>3/min) → soft block
- [ ] **Provider timeout** (Click 5s+) → degraded mode notification
- [ ] **Daily reconciliation farq** → super-admin'ga ogohlantirish

### 7.4 BI/Reporting
- [ ] Excel/PDF eksport
- [ ] Email-by-cron (oylik moliyaviy hisobot)
- [ ] Looker Studio yoki Metabase ulanishi (kelajakda)

---

# 🎯 To'lov tizimini "Real" qilish uchun MINIMAL ish

Eng kam ish bilan haqiqiy to'lov ishga tushishi:

### Sprint 1 (1-3 kun) — Telegram Test Mode
1. ✅ BotFather'dan `Click TEST` provider token
2. ✅ `.env`'ga yozish yoki Settings UI'da kiritish
3. ✅ Bot orqali test card bilan zakaz to'lash
4. ✅ Order paid + commission + book_car ishlashini tekshirish

**Natija**: Mijozlar TEST kartalar bilan to'lay oladi, real pul yo'q.

### Sprint 2 (1 hafta) — Click Merchant ariza
1. Click bilan shartnoma (INN bilan)
2. Live merchant key olish (1-3 kun)
3. `restaurant.click_merchant_id`, `secret_key` to'ldirish
4. Webhook URL Click panel'da ro'yxatdan o'tkazish
5. CLICK_ALLOWED_IPS env'da

**Natija**: Click orqali real to'lov ishlaydi.

### Sprint 3 (1-2 hafta) — Payme + UI
1. Payme shartnoma + cashbox
2. Refund flow backend + UI
3. Restaurant payment history UI to'liq
4. Super-admin financial dashboard

**Natija**: To'lov tizimi real biznes uchun tayyor.

---

# 📋 Yetishmaganlar — granular ro'yxat

## Backend
- [ ] `POST /admin/billing/refund` endpoint
- [ ] `POST /admin/orders/{id}/refund` endpoint
- [ ] `Refund` model
- [ ] Click REVERSE action wrapper
- [ ] Payme CancelTransaction wrapper
- [ ] Daily reconciliation script (`scripts/reconciliation.py`)
- [ ] Settlement report query
- [ ] Soliq qo'mitasi API real ulanishi
- [ ] QQS hisob-kitobi

## Frontend
- [ ] Restaurant admin: Payment Settings UI (Click/Payme keys, test/live)
- [ ] Restaurant admin: Refund tugmasi (har order'da)
- [ ] Restaurant admin: Settlement report sahifasi
- [ ] Super-admin: Refund button payments list'da
- [ ] Super-admin: Financial Dashboard
- [ ] Customer Web App: Payment receipt sahifasi
- [ ] Bot: Retry payment button (failure'dan keyin)

## DevOps
- [ ] Production `.env` audit (TELEGRAM_PROVIDER_TOKEN_*, CLICK_ALLOWED_IPS, ALERT_BOT_TOKEN)
- [ ] Webhook URL'larni Click/Payme panelda ro'yxatga olish
- [ ] HTTPS sertifikat amaldaligi (auto-renew)
- [ ] Log retention policy (logs/critical.log uchun)
- [ ] Backup strategiya (DB hozir 100KB, kelajakda > 1GB bo'lsa)
- [ ] Sentry yoki shunga o'xshash error tracking

## Test
- [ ] Click test card bilan e2e test (jonli)
- [ ] Payme test bilan e2e test
- [ ] Concurrent payment test (idempotency)
- [ ] Webhook retry storm test
- [ ] Failure recovery test

---

# 🔐 Xavfsizlik checklist

| Item | Holat | Eslatma |
|---|---|---|
| HTTPS | ✅ | nginx + Let's Encrypt |
| Click MD5 signature | ✅ | constant-time compare |
| Click IP allow-list | 🟡 | env'da `CLICK_ALLOWED_IPS` to'ldirish kerak |
| Payme Basic auth | ✅ | merchant_id:key |
| Idempotency | ✅ | UNIQUE constraint + early return |
| Rate limiting | ✅ | SlowAPI 300/min default, login 5/min |
| Audit log | ✅ | SecurityLog + SuperAdminAction |
| INN tasdiqlash gate | ✅ | is_verified=True talab |
| JWT (1 soat TTL) | ✅ | refresh token bilan |
| Bcrypt parol | ✅ | SHA-256 backward compat |
| Tiyin int (float yo'q) | ✅ | Pul matematika |
| Tenant isolation (IDOR) | ✅ | get_restaurant_context dep |
| Suspended → 402 | ✅ | Subscription middleware |
| Click webhook xato → alert | ✅ | Telegram notifier |
| Maintenance mode | ✅ | Super-admin toggle |
| Backup | ✅ | scripts/backup_db.sh |
| Soliq fiskal | ❌ | Phase 6 |
| Refund/dispute UI | ❌ | Phase 3 |
| PCI-DSS audit | N/A | Card data Telegram'da, biz saqlamaymiz |

---

# 💰 Hozirgi mock vs real to'lov solishtirish

## Mock rejim (hozir)
```
1. Foydalanuvchi "Pro tarif sotib olish" bossa
2. POST /payments/create-invoice
3. Payment yaratiladi (status='pending')
4. URL: https://mock.payments.local/click/r1-p3-abc...
5. Frontend modal: "Mock complete" tugma
6. POST /payments/mock/complete
7. mark_payment_success()
8. Tarif faollashadi
```

## Real rejim (Faza 1 dan keyin)
```
1. Foydalanuvchi "Pro tarif sotib olish" bossa
2. POST /payments/create-invoice
3. Payment yaratiladi (status='pending')
4. URL: https://my.click.uz/services/pay?service_id=12345&...
5. Click sahifasi ochiladi
6. Foydalanuvchi karta raqami kiritadi
7. Click tranzaksiyani amalga oshiradi
8. Click → POST /payments/click/webhook (PREPARE → COMPLETE)
9. Bizning handle_click_webhook() — signature tekshiruvi
10. mark_payment_success() — auto upgrade
11. Restaurant: tarif faollashadi
12. Telegram alert platforma adminga
```

Yagona kod farqi: `_resolve_provider_token()` mock yoki real URL qaytarishi. Boshqa hammasi bir xil.

---

# 📅 Tavsiya etilgan tartib

```
Hafta 1: Faza 1.3 (BotFather token) + sinov
Hafta 2: Faza 1.1, 1.2 (Click/Payme shartnoma — kutish)
Hafta 3: Faza 2 (webhook to'liq sinov)
Hafta 4: Faza 3 (refund flow)
Hafta 5-6: Faza 4 (UX yaxshilash)
Hafta 7-8: Faza 5 (settlement)
Hafta 9+: Faza 6, 7 (compliance, analytics)
```

**Tezkor MVP** uchun Faza 1.3 + 1.4 yetadi (1-3 kun ish).

---

# 🚀 Birinchi qadamlar (BUGUN)

1. **BotFather** ni Telegram'da oching
2. `/mybots` → @videoSearchbotbot → Payments
3. **Click Test** ni tanlang
4. Token'ni nusxalang (`12345:TEST:...`)
5. Tokenni shu chatda menga jo'nating yoki:
   ```bash
   ssh root@65.109.5.207
   echo "TELEGRAM_PROVIDER_TOKEN_CLICK=12345:TEST:..." >> /opt/restaurant-staging/.env
   ```
6. API qayta ishga tushiring
7. Bot orqali zakaz bering → "💳 Karta" → "Click" → **TEST karta** bilan to'lang:
   ```
   Card: 8600 0000 0000 0000
   Date: 12/25
   CVV:  123
   ```
8. Order paid bo'lishini admin panelda ko'ring + Telegram alert keladi

---

**Hujjat saqlandi**: `docs/PAYMENT_ROADMAP.md`
**Yangilandi**: 2026-05-01
**Holat**: Faza 1.3 (BotFather token) — keyingi qadam
