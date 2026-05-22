# Yandex Delivery — Ulanish bo'yicha to'liq qo'llanma

Bu hujjat Mezbon platformasiga (yoki har qanday restoran) **Yandex Dostavka** xizmatini ulashni boshidan oxirigacha tushuntiradi.

---

## 📋 1-bosqich — Kerakli hujjatlar (oldindan tayyorlash)

Yandex Dostavka kabinet ochishdan oldin quyidagilar **albatta bo'lishi kerak**:

### Korxona ma'lumotlari
- [ ] **INN (STIR)** — `305 662 430` ✅ (Muhsina'da bor)
- [ ] **Bank hisob raqami** (20 raqamli)
- [ ] **MFO** (5 raqamli bank kodi)
- [ ] **OKED kodi** — `56290` (Muhsina'da bor)
- [ ] **Yuridik manzil** to'liq (Otchopar ko'chasi, 10-uy)
- [ ] **Direktor F.I.Sh** + pasport seriyasi (Isaxanov Dilshod, AC...)
- [ ] **Direktor telefon** raqami (+998 97 709 06 04)
- [ ] **Korxona email** (muhsina@umail.uz)

### Texnik ma'lumotlar
- [ ] **Restoran/filial GPS koordinatalari** (har biri uchun)
- [ ] **Pickup manzili** (kuryer keladigan joy — restoran)
- [ ] **Ishchi soat** (kuryer chaqirishingiz mumkin bo'lgan vaqt)

### Coverage (yetkazib berish hududi) tekshiruvi
- [ ] Yandex Dostavka qaysi shaharlarda ishlaydi tekshirish
- [ ] Sizning shaharingiz/rayoningiz ro'yxatda bormi?
- Status (2026): **Tashkent, Samarqand, Buxoro, Andijon, Farg'ona** — to'liq qamrov; boshqa viloyat markazlari — qisman

---

## 📝 2-bosqich — Kabinet ochish (1-2 kun)

### Qadam 1: Yandex korporativ hisob
1. **[dostavka.yandex.ru](https://dostavka.yandex.ru)** ga kiring
2. Yuqori o'ng burchakda **"Войти"** → Yandex ID bilan
3. Korporativ hisob yo'q bo'lsa: yangi yarating

### Qadam 2: Tashkilot ma'lumotlari
1. **"Бизнес-аккаунт"** → **"Создать организацию"**
2. To'ldiring:
   - Mamlakat: **O'zbekiston**
   - Tashkilot turi: **СП (Семейное предприятие)** ✅
   - Nomi: `"MUHSINA" oilaviy korxonasi`
   - INN: `305662430`
   - Bank rekvizitlari (h/r + MFO)
   - Yuridik manzil
   - Aloqa shaxsi (direktor)

### Qadam 3: Oferta tasdiqlash
1. Yandex ofertasini o'qing (juda muhim — komissiya va shartlar)
2. **Komissiya:** har yetkazib berish narxidan ~15-25%
3. **Hisob-kitob:** haftalik yoki oylik (Yandex sizga hisob beradi)
4. Elektron imzo bilan tasdiqlash

### Qadam 4: Hisob to'ldirish
Yandex **predoplata** bilan ishlaydi (har dastavka oldindan to'lanadi):
- **Minimal balans:** 100,000 so'm
- To'ldirish: bank o'tkazmasi yoki karta
- Hisob bo'sh bo'lsa kuryer chaqirib bo'lmaydi

---

## 🔑 3-bosqich — API Token olish (15 daqiqa)

### Kabinetda:
1. Yuqori o'ng burchak → **"Профиль"** → **"Интеграция"**
2. **"API tokenlar"** bo'limi
3. **"Создать токен"** tugmasini bosing
4. Sarlavha kiriting: `"Mezbon Production"` yoki `"Mezbon Test"`
5. Token formati: `y0_AgAAAAA...` (uzun OAuth token)
6. Bu tokenni **darhol saqlang** — qayta ko'rsatilmaydi
7. **Muhim:** Test va Live alohida tokenlar bo'lishi mumkin

### Tokenni admin paneliga kiritish:
1. `admin.tursunboyev.com` ga kiring (Muhsina admin hisobi bilan)
2. **Sozlamalar → Dastavka** tabini oching
3. **"Yetkazib berish turi"** → **`🟡 Yandex Delivery`**
4. **"Yandex OAuth Token"** ga `y0_Ag...` ni joylang
5. **"Test rejim"** — boshida YOQILGAN qoldiring (real pul ketmasin)
6. **Saqlash**

---

## 🔗 4-bosqich — Webhook URL sozlash

Yandex'dan **status yangilanishlarini** olish uchun webhook URL kerak.

### Kabinetda webhook qo'shish:
1. Kabinet → **"Интеграция"** → **"Webhooks"** yoki **"Уведомления"**
2. **URL kiriting:**
   ```
   https://api.tursunboyev.com/webhooks/yandex?token=<YANDEX_WEBHOOK_SECRET>
   ```
3. **`<YANDEX_WEBHOOK_SECRET>`** — server `.env` da o'rnatilgan random secret
4. **Event'larni tanlang:**
   - ✅ `claim_status_changed` (claim statusi o'zgarganda)
   - ✅ `performer_found` (kuryer topilganda)
   - ✅ `claim_cancelled` (bekor qilinganda)
   - ✅ `claim_delivered` (yetkazib berilganda)

### Server tomondan tayyorgarlik:
```bash
# .env'ga qo'shish (production va staging alohida)
YANDEX_WEBHOOK_SECRET=<32 belgili random string>
```

Token yaratish:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 🧪 5-bosqich — Test rejimda sinab ko'rish

### Test buyurtma yaratish:
1. Telegram bot orqali oddiy zakaz bering
2. **Manzilni** Yandex coverage zonasida tanlang
3. Click/Payme orqali to'lov qiling (test rejim)
4. Avtomatik:
   - Yandex'ga claim yuboriladi (test API)
   - `order.yandex_claim_id` DB'ga yoziladi
   - Mijozga "Kuryer izlanmoqda" xabari boradi

### Loglarda tekshirish:
```bash
ssh root@65.109.5.207
tail -f /opt/restaurant/api.log | grep -i yandex
```

Kutilgan loglar:
```
[Yandex] Claim created: claim-xxx for order #142
[delivery] Yandex feature enabled, dispatching order #142
```

### Webhook test (qo'lda):
```bash
# Yandex serveri kelishi kerakligini taqlid qilish
curl -X POST 'https://api.tursunboyev.com/webhooks/yandex?token=<SECRET>' \
  -H 'Content-Type: application/json' \
  -d '{
    "claim_id": "claim-xxx",
    "status": "performer_found",
    "performer_info": {
      "name": "Test Kuryer",
      "phone": "+998 90 123 45 67"
    }
  }'
```

Mijoz darhol Telegram orqali xabar olishi kerak: "🚗 Kuryer topildi..."

---

## 🚀 6-bosqich — Production'ga o'tish

Test rejimda 5-10 ta zakaz muvaffaqiyatli o'tgandan keyin:

1. **Yandex kabinet** → API tokenni **LIVE** versiyaga almashtiring (yoki yangi yarating)
2. **Admin panel** → Sozlamalar → Dastavka:
   - Tokenni LIVE bilan almashtiring
   - **"Test rejim"** ni **O'CHIRING**
   - Saqlash
3. **Kabinetda balansni to'ldiring** (kamida 200,000 so'm — birinchi kuni uchun)
4. **Webhook URL** ham LIVE bo'lib qoldi (faqat token o'zgarmasin)
5. Birinchi real zakaz — kichik summa bilan tekshiring

---

## 🛡 Xavfsizlik va monitoring

### Server tomonda:
- ✅ Webhook signature/token tekshiruvi
- ✅ Per-restaurant token izolatsiya (DB'da `Restaurant.yandex_api_token`)
- ✅ Test/Live rejim per-restaurant (`yandex_test_mode`)
- ✅ Buyurtma bekor qilinganda Yandex claim ham bekor qilinadi
- ✅ Webhook latency metrikasi (`webhook_metrics` jadval)
- ✅ Rate limit (300/min har IP)

### Yandex tomonda kuzatish:
- Kabinet → **"Заказы"** — har zakaz statusi
- Kabinet → **"Финансы"** — balans va to'lovlar
- Kabinet → **"Отчеты"** — kunlik/oylik hisobotlar

### Alarmlar (sozlash tavsiya etiladi):
- ⚠️ Balans 50,000 so'mdan kam → admin ga email
- ⚠️ 1 soatda 3+ failed dispatch → Telegram alert
- ⚠️ Webhook hech kelmayotgan bo'lsa (24 soat) → tekshirish

---

## 💰 Taxminiy narx hisoboti

### Yandex tomondan:
| Masofa | Narx (Tashkent) |
|--------|-----------------|
| 0-3 km | ~15,000-20,000 so'm |
| 3-7 km | ~20,000-30,000 so'm |
| 7-15 km | ~30,000-50,000 so'm |
| 15+ km | ~50,000+ so'm |

**Narxlar real vaqtda hisoblanadi** — kunning vaqtiga (pik soat) va talab/taklif darajasiga qarab o'zgaradi.

### Mezbon tomondan:
- **Mijozdan olinadigan summa:** Yandex narxi (zakaz vaqtida ko'rsatiladi)
- **Restoran komissiyasi:** 0% (Yandex'ga to'lanadi to'g'ridan-to'g'ri)
- **Sizning daromad:** mahsulotlar narxi (dastavka emas)

---

## ⚠️ Tez-tez uchraydigan muammolar

### 1. "Kuryer topilmadi" (`performer_not_found`)
**Sabab:** Pik soat, kuryer band yoki coverage zonasi tashqarisi  
**Yechim:**
- Coverage'ni tekshiring
- 3-5 daqiqa kutib, qayta dispatch qiling
- Yoki fallback `own` kuryer'ga avtomatik o'ting

### 2. "Insufficient balance"
**Sabab:** Yandex hisobida pul yo'q  
**Yechim:** Kabinetdan hisobni to'ldiring

### 3. "Invalid token"
**Sabab:** Test token Live'da ishlatilmoqda yoki muddati tugagan  
**Yechim:** Yangi token yarating va admin panelda yangilang

### 4. "Address out of coverage"
**Sabab:** Manzil Yandex zonasidan tashqarida  
**Yechim:** Bot mijozga "Bu manzilga yetkazib berib bo'lmaydi" deb xabar berib, alternative (pickup) ni taklif qilsin

---

## ✅ Yakuniy tekshiruv ro'yxati

**Texnik tomon (kod):**
- [x] Yandex API client (`yandex_delivery.py`)
- [x] Dispatcher (`delivery.py`)
- [x] Webhook endpoint (`yandex_webhook.py`)
- [x] Auto-cancel on order cancel
- [x] Tracking URL bot xabarida
- [x] Admin UI (token va test/live)
- [x] Plan feature flag (`has_yandex`)
- [ ] Pre-order narx hisoblash (kelajakda)
- [ ] Coverage tekshiruvi UI (kelajakda)

**Biznes tomon (siz):**
- [ ] Yandex Dostavka kabineti yarat
- [ ] Bank rekvizitlari kiritish
- [ ] Oferta tasdiqlash
- [ ] Hisob to'ldirish
- [ ] API token olish (test + live)
- [ ] Webhook URL'ni kabinetda ro'yxatdan o'tkazish

**Operatsion tomon:**
- [ ] Production .env'ga `YANDEX_WEBHOOK_SECRET` qo'shish
- [ ] Admin panelda tokenni kiritish
- [ ] Test rejimda 5 ta zakaz sinash
- [ ] Loglarni 24 soat kuzatish
- [ ] Live'ga o'tish

---

## 📞 Aloqa va yordam

**Yandex Dostavka B2B qo'llab-quvvatlash:**
- Telegram: `@yandex_delivery_support`
- Email: `delivery-support@yandex-team.ru`
- Sayt: https://yandex.com/support/delivery-profile/

**Texnik hujjat (rasmiy):**
- API: https://yandex.com/support/delivery-profile/en/api/express/
- Webhook: https://yandex.com/support/delivery-profile/en/api/express/v2/webhook-claim.html
