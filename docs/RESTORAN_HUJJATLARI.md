# 📋 Restoran hamkorlari uchun hujjatlar ro'yxati

**Platforma:** Muhsina Dollar Somsa (delivery SaaS)
**Integratsiyalar:** Click, Payme, Yandex Delivery

Har restoran hamkor bilan shartnoma tuzish uchun quyidagi hujjatlarni
yig'ib olish kerak. Hujjatlar har 3 platformaga deyarli bir xil.

---

## 🏢 1. Asosiy kompaniya hujjatlari (barchasida kerak)

### A. Yuridik shaxs (OOO/MChJ):

1. **Davlat ro'yxatidan o'tish guvohnomasi** (skan yoki nusxa)
2. **Ustav** (skan — barcha sahifalar)
3. **INN raqami** (ЎзК: Soliq identifikatsiya raqami)
4. **OKED** (Faoliyat turlari klassifikatori kod):
   - `56.10.0` — Oziq-ovqat xizmatlari (restoran)
   - `56.30.0` — Ichimlik xizmatlari
   - `47.99.9` — Boshqa chakana savdo
5. **Bank rekvizitlari:**
   - Hisob raqami (UZS)
   - Bank nomi
   - MFO
   - INN bank

### B. Jismoniy tadbirkor (YaTT):

1. **YaTT guvohnomasi**
2. **INN**
3. **Patent** (agar patent tizimida bo'lsa)
4. **Bank rekvizitlari** (biznes karta yoki hisob)

### C. Direktor/Rahbar hujjatlari (ikkalasida ham):

1. **Pasport** (to'liq skan — barcha sahifalar yoki rasmi bilan)
2. **Direktor tayinlanganligi haqida buyruq** (OOO uchun)
3. **Telefon raqami** (+998...)
4. **Email manzil**

---

## 🟡 2. Yandex Delivery uchun qo'shimcha

### Talablar:
1. **Barcha yuqoridagi hujjatlar** ✅
2. **Kompaniya logo** (PNG, 200×200+ px)
3. **Kompaniya manzili** (aniq — xarita coordinate bilan)
4. **Faoliyat sohasi:** "Restoran/Café" yoki "Oziq-ovqat yetkazib berish"

### EDO (Elektron Hujjat Aylanishi):
5. **ERI** — Elektron Raqamli Imzo (kerak)
   - O'zbekistonda provayderlar:
     - **E-IMZO** (https://e-imzo.uz) — davlat xizmati
     - **ID-Card** — elektron hujjatlar
     - **Didox** (https://didox.uz) — EDO
6. **EDO hisob** — Didox / Faktura / Raqam.uz'dan birida

### Yandex kabineti orqali:
7. **Korporativ hisob ochish** (https://dostavka.yandex.ru)
8. **Menejer bilan bog'lanish** — shartnoma tuzadi
9. **OAuth Token** — API integratsiya uchun

### Narx:
- Oylik abonement yo'q
- Har buyurtmadan komissiya: **~15,000 so'm** (masofaga qarab)
- Oxirgi narx Yandex API orqali real-time hisoblanadi

---

## 🔵 3. Click Merchant uchun qo'shimcha

### Hujjatlar:
1. **Yuqoridagi barcha** ✅
2. **Kompaniya logo** (PNG/JPG — 500×500 px)
3. **Faoliyat tavsifi** (1-2 paragraf)
4. **Sayt/Domen manzili** (webhook uchun)
5. **Public offerta matni** (mijozlar bilan shartnoma — shablon bor)

### Ariza:
1. **[merchant.click.uz](https://merchant.click.uz)** → "Ro'yxatdan o'tish"
2. Online shakl to'ldirish
3. Hujjatlar yuklash
4. Elektron shartnoma imzolash

### Berilgan credentials (test + prod):
- **Merchant ID**
- **Service ID**
- **Secret Key**
- **Webhook URL** (biz beramiz)

### Narx:
- **UzCard/Humo:** 0.8% komissiya
- **Visa/Mastercard:** 2.5% komissiya
- **Minimal oylik aylanma:** 5,000,000 so'm tavsiya qilinadi

### Muddat: 5-10 ish kuni

---

## 🟢 4. Payme Merchant uchun qo'shimcha

### Hujjatlar:
1. **Yuqoridagi barcha** ✅
2. **Kompaniya logo** (SVG/PNG)
3. **Faoliyat ma'lumoti** (qaysi mahsulot/xizmat)
4. **Sayt/Mobile app linki** (webhook uchun)
5. **Dodge Test muhit uchun test mijoz bilan shartnoma**

### Ariza:
1. **[business.paycom.uz](https://business.paycom.uz)** → "Hamkor bo'lish"
2. Online shakl
3. Hujjatlar yuklash
4. Menejer telefon orqali bog'lanadi
5. Shartnoma + ERI imzolash

### Berilgan credentials:
- **Cashbox ID** (test + prod)
- **Merchant key** 
- **Webhook URL**

### Narx:
- **UzCard/Humo:** 0.8% - 1.2%
- **Visa/Mastercard:** 2.5%
- **Minimal oylik aylanma:** 3,000,000 so'm

### Muddat: 3-7 ish kuni

---

## 📝 5. Yig'ish kerak bo'lgan ma'lumotlar (har restaurantdan)

Har bir restoran hamkor uchun **quyidagi ma'lumotlarni** yig'ing:

### 5.1 Kompaniya ma'lumotlari
```
Kompaniya nomi (rasmiy):     __________________________
Kompaniya nomi (brend):      __________________________
Yuridik shakli (OOO/YaTT):   __________________________
INN:                         __________________________
OKED:                        __________________________
Ro'yxatdan o'tish raqami:    __________________________
Yuridik manzil:              __________________________
Faktik manzil (restoran):    __________________________
Koordinatalar (lat, lon):    __________________________
Telefon:                     +998 ____________________
Email:                       __________________________
Kompaniya logo:              [rasmiy logo fayl]
```

### 5.2 Direktor ma'lumotlari
```
Ism-familiya:                __________________________
Pasport seriyasi/raqami:     __________________________
JShShIR (PINFL):             __________________________
Tug'ilgan sana:              __________________________
Direktor telefoni:           +998 ____________________
Pasport skan:                [fayl]
```

### 5.3 Bank rekvizitlari
```
Bank nomi:                   __________________________
MFO:                         __________________________
Hisob raqami (UZS):          __________________________
Korrespondent hisob:         __________________________
```

### 5.4 EDO va ERI
```
EDO provayder:               Didox / Faktura / Raqam / Boshqa
Login:                       __________________________
ERI bor:                     Ha / Yo'q
ERI serifitikat muddati:     __________________________
```

### 5.5 Restoran ish ma'lumotlari
```
Ish vaqti (ochilish):        ___:___
Ish vaqti (yopilish):        ___:___
Dam olish kunlari:           __________________________
Ish o'rinlari soni:          __________________________
Oylik buyurtma soni (takh):  __________________________
Oylik aylanma (takh):        __________________________
```

---

## 📅 6. Shartnoma tuzish tartibi

### 1-hafta:
- [ ] Restorandan barcha hujjatlarni yig'ish
- [ ] YaTT/OOO yo'q bo'lsa — ro'yxatdan o'tkazish
- [ ] ERI yo'q bo'lsa — buyurtma qilish

### 2-hafta:
- [ ] **Yandex Delivery** — kabinet ochish va menejerdan API token so'rash
- [ ] **Click merchant** — ariza yuborish
- [ ] **Payme merchant** — ariza yuborish

### 3-hafta:
- [ ] Barcha uchun credential'lar kelishi (token, secret key'lar)
- [ ] Test mode'da integratsiya sinash
- [ ] Jonli (production) mode ga o'tkazish

---

## ⚠️ Muhim eslatmalar

1. **Hujjatlarning nusxasi** (photocopy) emas, **skan** yoki **rasmi aniq** bo'lishi kerak (1080p+)
2. **ERI narxi:** ~300,000-500,000 so'm/yil (kompaniya uchun)
3. **Bank hisob raqami** aktiv bo'lishi shart (bir oy oldin ochilgan bo'lishi kerak)
4. **YaTT** lar uchun ayrim platformalar cheklangan limitlar qo'yadi (masalan, oylik 10 mln so'mgacha)
5. **Public offerta** — har 3 platforma uchun alohida kerak (oldindan to'lov shartlari, qaytarish politikasi)

---

## 💡 Maslahat

Kichik restoranlar uchun **bosqichli yondashuv**:
1. **Bosqich 1:** Faqat **Click** bilan ishga tushish (tez, oddiy)
2. **Bosqich 2:** 1-oydan keyin **Payme** qo'shish
3. **Bosqich 3:** Yandex Delivery — oylik buyurtma 50+ bo'lganda

---

## 📞 Yordam kontaktlari

- **Yandex Delivery:** support@delivery.yandex.ru
- **Click:** support@click.uz, +998 71 207 78 78
- **Payme:** support@paycom.uz, +998 78 777 77 77

---

*Oxirgi yangilanish: 2026-04-21*
*Hujjat: MuhsinaDollar platforma*
