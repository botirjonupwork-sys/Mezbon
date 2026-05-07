# 📝 Click LIVE Merchant — Ariza materiallari

**Maqsad:** Click bilan rasmiy shartnoma tuzish va LIVE merchant kalitlarini olish.

---

## 1️⃣ Qaerga ariza beriladi

- **Sayt:** [merchant.click.uz](https://merchant.click.uz)
- **Telefon:** +998 71 231 08 80
- **Telegram:** [@click_uz_bot](https://t.me/click_uz_bot)
- **Email:** business@click.uz

---

## 2️⃣ Kerakli hujjatlar

### Yuridik shaxs ma'lumotlari
- [ ] Kompaniya nomi (rasmiy)
- [ ] **INN** (9 raqam)
- [ ] OKED kodi
- [ ] Yuridik manzil
- [ ] Faktik manzil (agar farq qilsa)
- [ ] Direktor F.I.Sh + INN

### Bank rekvizitlari
- [ ] Bank nomi
- [ ] MFO
- [ ] Hisob raqami (tinkalog)
- [ ] Valyuta (UZS)

### Faoliyat
- [ ] Faoliyat turi: **Restoran/Catering xizmatlari**
- [ ] Sayt yoki ilova: `https://muhsina-dollar.uz` (agar bor bo'lsa) yoki Telegram bot
- [ ] Telegram bot: `@videoSearchbotbot`
- [ ] Tasdiqlangan kunlik tushum (estimatsiya): **____ so'm**

### Texnik
- [ ] **Webhook URL:** `https://api.tursunboyev.com/payments/click/webhook`
- [ ] **HTTPS sertifikat:** ✅ bor (Let's Encrypt)
- [ ] **Idempotency:** ✅ qo'llab-quvvatlanadi (UNIQUE constraint)
- [ ] **MD5 signature tekshiruvi:** ✅ qo'llab-quvvatlanadi
- [ ] **IP allowlist:** ✅ env orqali sozlanadi

---

## 3️⃣ Komissiya stavkalari

Click standart komissiya:
- **UzCard / Humo:** 0.8%
- **Visa / Mastercard:** 2.5%
- **Click Wallet:** 1.5%

Yuqori hajm uchun individual stavka kelishish mumkin.

---

## 4️⃣ Ariza ko'rish muddati

- **Hujjatlar tekshiruvi:** 1-3 ish kuni
- **Test rejim aktivatsiyasi:** darhol (TEST token)
- **LIVE rejim:** shartnoma imzolanganidan keyin 1-2 ish kuni

---

## 5️⃣ Shartnoma imzolanganidan keyin Click beradi:

1. **Merchant ID** (sonli, masalan `12345`)
2. **Service ID** (sonli, masalan `54321`)
3. **Secret Key** (32+ belgi — bu webhook MD5 signature uchun)
4. **Click LIVE provider token** — BotFather orqali (alohida)
5. **Click IP'lari ro'yxati** (webhook'lar shu IP'lardan keladi)

---

## 6️⃣ Olganidan keyin nima qilish

### A. Restaurant settings (admin.tursunboyev.com → Settings → To'lov)
```
✅ Click ulash: YOQ
Merchant ID: 12345
Service ID: 54321
Secret Key: ••••••••••••••••••••••••••••••••
```

### B. Telegram Native Payments token (BotFather)
```
1. @BotFather → /mybots → @videoSearchbotbot
2. Payments → Click Test → "Connect Click"
3. Click LIVE Merchant ID + Service ID + Secret Key kiritiladi
4. Token shaklda chiqadi: 12345:LIVE:abc...
5. Adminda shu tokenni "Telegram Click LIVE token" maydoniga yozish
```

### C. Production .env yangilash
```bash
# /opt/restaurant/.env
TELEGRAM_PROVIDER_TOKEN_CLICK=12345:LIVE:abc...
CLICK_ALLOWED_IPS=185.232.66.123,185.232.66.124,...   # Click bergan ro'yxat
```

### D. Settings → Test rejimni o'chirish (Live rejimga o'tish)
```
🧪 Test rejim → 💰 LIVE rejim
```

### E. End-to-end test
- Bot orqali kichik (5,000 so'm) buyurtma
- Real karta bilan to'lash
- Pul tushganligini Click merchant kabinetda tasdiqlash
- Refund flow sinash (5,000 so'mni qaytarish)

---

## 7️⃣ Click qo'llab-quvvatlash

Muammo bo'lsa:

| Muammo | Kim hal qiladi |
|---|---|
| To'lov rad etildi | Mijoz kartasi → bank |
| Webhook kelmadi | Click texnik qo'llab-quvvatlash (24/7) |
| Pul yo'qoldi | Click rasmiy shikoyat (3 ish kuni) |
| Refund o'tmaydi | Click merchant manager |

**Tezkor aloqa:** [@click_uz_bot](https://t.me/click_uz_bot) — odatda 5-15 daqiqada javob

---

## 📋 Tayyor ariza shabloni (Click'ga email/Telegram)

```
Hurmatli Click jamoasi,

Biz "Muhsina Dollar SaaS" kompaniyamiz uchun Click merchant integratsiyasini
o'rnatishni xohlaymiz. Quyidagi ma'lumotlarni taqdim etamiz:

Kompaniya nomi: ____________________
INN: ____________________
Yuridik manzil: ____________________
Direktor F.I.Sh: ____________________
Telefon: ____________________

Faoliyat turi: Restoran va catering xizmatlari (multi-tenant SaaS platform)

Bank rekvizitlari:
- Bank: ____________________
- MFO: ____________________
- Hisob: ____________________

Texnik tafsilotlar:
- Webhook URL: https://api.tursunboyev.com/payments/click/webhook
- Telegram bot: @videoSearchbotbot
- Sayt: https://muhsina-dollar.uz (agar bor bo'lsa)

Hozir TEST rejimda integratsiya tugatdik (token: 398062629:TEST:...).
LIVE rejim uchun shartnoma jarayonini boshlashni so'raymiz.

Hurmat bilan,
[F.I.Sh]
```
