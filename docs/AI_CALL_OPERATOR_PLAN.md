# AI Call-Operator Agent — Implementation Plan

> "Muhsina Dollar Somsa" loyihasi uchun ovozli AI agent qurish rejasi.
> Asosiy maqsad: telefon orqali kelgan zakazlarni avtomatik qabul qilish va
> mavjud FastAPI backend orqali tizimga qo'shish.

---

## Faza 0 — Telefoniya infratuzilmasi (PREREQUISITE)

> Reja boshlanmasdan oldin hal qilinishi shart.

### Telefon raqam va SIP
Vapi / Retell — bu faqat AI orkestrator. Ularga **O'zbekiston raqami** ulash kerak.

Variantlar:
- **Twilio** — global, lekin `+998` raqamlari cheklangan
- **Beeline Business / Uzmobile** — SIP trunk (mahalliy, eng tabiiy yo'l)
- **Voximplant** — O'zbekiston bilan ishlaydi, REST API bor
- **Plivo / SignalWire** — alternativlar

**Tavsiya:** Beeline Business SIP trunk + Voximplant orkestrator yoki Twilio-uyg'un raqam.

### Yozib olishga rozilik
O'zbekiston qonunchiligi bo'yicha qo'ng'iroq boshida ovozli e'lon majburiy:
> "Ushbu qo'ng'iroq sifat va o'qitish uchun yozib olinadi."

---

## Faza 1 — API infratuzilmasi va xavfsizlik

### 1.1 Maxsus AI agent token
Yangi token turi — `phone-agent` — alohida bearer token bilan ishlaydi.
`X-Bot-Secret` header catering POST'lar uchun majburiy (allaqachon mavjud).

### 1.2 Sintetik foydalanuvchilar
Telegram identifikatori bo'lmagan, faqat telefon orqali kelgan mijozlarni
`User.telegram_id = "phone:+998901234567"` formatida ro'yxatdan o'tkazish.
Real Telegram ID'lari bilan to'qnashmaydi.

### 1.3 Idempotency
`Order` modeliga `idempotency_key` qo'shish:
```python
idempotency_key = Column(String, unique=True, nullable=True)
# Format: "call:<call_session_id>:<timestamp>"
```
Qo'ng'iroq uzilib, mijoz qayta qo'ng'iroq qilsa — takroriy zakaz yaratilmaydi.

### 1.4 Endpointlar (mavjud, ammo agent uchun yangi tool wrapper'lar)
- `POST /orders` — kunlik
- `POST /catering/orders` — catering (X-Bot-Secret bilan)
- `POST /catering/calculate-price` — narx preview
- `GET /branches/nearest?lat=...&lon=...`
- `GET /admin/products?product_type=catering&restaurant_id=...`

---

## Faza 2 — Biznes logika va bilimlar bazasi

### 2.1 Catering qoidalari (system prompt'ga kiritish)
- 24 soat oldin band qilish (aks holda hotline `+998 98 000 06 04`)
- Min 100 ta somsa (har xil turlardan aralash bo'lishi mumkin)
- Min 40 ta non, 40 ga karrali (tandir bo'yicha)
- 3 yetkazib berish turi:
  - `onsite` — tandir bilan joyiga borib yopib berish
  - `pickup` — saboy (mijoz olib ketadi)
  - `delivery` — Yandex orqali tayyor mahsulot

### 2.2 Filiallar logikasi
Mijoz manzil aytadi → AI **Yandex Geocoder API** bilan koordinataga aylantiradi
→ `GET /branches/nearest` orqali eng yaqin filialni topadi → o'sha filialning
ish vaqti va menyusini tekshiradi.

### 2.3 To'lov tizimi
- Naqd (faqat pickup/delivery uchun)
- Click/Payme — AI to'lov havolasi yaratadi va mijozga SMS yoki Telegram orqali yuboradi
- Catering "hozir to'lov" — restaurant kartasi ko'rsatiladi

### 2.4 Read-back (majburiy)
**`confirm_order` toolidan oldin** AI butun buyurtmani o'qib chiqib, mijozdan tasdiq oladi:
> "Buyurtmangiz: 100 ta go'shtli somsa, ertaga soat 14:00 ga, manzil...
> Jami summa: 1,200,000 so'm. Tasdiqlaysizmi?"

---

## Faza 3 — Voice AI stack va latency optimallashtirish

### 3.1 Stack tanlovi (yangilangan)

| Layer | Tavsiya | Sabab |
|-------|---------|-------|
| **Orkestrator** | Vapi yoki Retell | Real-time WebSocket, tool-calling, streaming |
| **STT** | **Whisper Large-v3** yoki **Yandex SpeechKit** | Uzbek tilini yaxshi tushunadi (Gemini Flash o'zi qila olmaydi) |
| **LLM** | Gemini 1.5 Flash yoki GPT-4o-mini | Tezkor, arzon, tool-calling |
| **TTS** | **Yandex SpeechKit** | Uzbek erkak/ayol ovozi bor (ElevenLabs Uzbek hali zaif) |

⚠️ **Eski rejadagi ElevenLabs Multilingual v2 olib tashlandi** — Uzbek tili
sifatida hali yetarli emas. Yandex SpeechKit Uzbek+Russian uchun yaxshiroq.

### 3.2 Code-switching (Uz-Ru aralash nutq)
O'zbek mijozlari ko'pincha:
> "Menga 100 ta somsa keraк, на ужин 19:00 da"

STT `auto-detect` rejimida ishlasin. LLM system prompt'ga:
> "Mijoz Uz-Ru aralash gapirsa ham tushun va shu tilda javob ber."

### 3.3 Latency target (realistik)
- STT (streaming): ~300ms
- LLM (streaming first token): 400–800ms
- TTS (streaming): ~300ms
- Tool-calling: +500–1000ms

**Real total:** 1.0–1.5s gap turlari uchun, 2–3s tool-calling bilan.

### 3.4 Filler phrases
Tool-calling vaqtida AI pauza qilmasdan:
> "Bir soniya, tekshirib ko'rayapman..."
> "Eng yaqin filialni qidirayapman..."

deb gaplashsa, mijoz kutish sezmaydi.

---

## Faza 4 — Tool calling (funksional integratsiya)

AI agent uchun tool wrapper'lar (har biri 1 ta API endpointga mos):

### 4.1 Tools ro'yxati

| Tool | Endpoint | Maqsad |
|------|----------|--------|
| `geocode_address` | Yandex Geocoder API | Matn manzil → lat/lon |
| `find_nearest_branch` | `GET /branches/nearest` | Eng yaqin filial |
| `get_branch_menu` | `GET /admin/products?branch_id=...` | Menyu |
| `get_catering_groups` | `GET /catering/groups` | Somsa/Non guruh + qoidalar |
| `quote_catering_price` | `POST /catering/calculate-price` | Real-time narx |
| `find_or_create_user` | `GET/POST /users` | Telefon orqali user |
| `create_regular_order` | `POST /orders` | Kunlik zakaz |
| `create_catering_order` | `POST /catering/orders` | Catering zakaz |
| `generate_payment_link` | `POST /payments/click/create` (kelajak) | Click/Payme link |
| `transfer_to_human` | (telephony API) | Operator'ga yo'naltirish |

### 4.2 Order creation flow
1. Mijoz buyurtma haqida gapiradi
2. AI tool'lar bilan ma'lumotlarni to'plab boradi (manzil, vaqt, mahsulot)
3. **Read-back** — barcha ma'lumotlarni o'qib chiqadi
4. Mijoz tasdiqlaydi
5. AI `create_*_order` chaqiradi (idempotency_key bilan)
6. Order ID + tracking link mijozga aytiladi

---

## Faza 5 — Testlash va ishga tushirish

### 5.1 Ssenariylar testi (kamida 50 ta)
- ✅ **Standart catering:** "100 ta somsa ertaga 14:00 ga"
- ✅ **Aralash:** "33 go'shtli, 33 ko'kli, 34 ovashnoy"
- ✅ **Mijoz gapni bo'lganda** (interruption handling)
- ✅ **Sheva** (Toshkent / Farg'ona / Andijon)
- ✅ **Code-switching** (Uz-Ru aralash)
- ✅ **24 soat ichida zakaz** → operator'ga yo'naltirish
- ✅ **Noto'g'ri raqam aytish** → qayta so'rash
- ✅ **Mijoz noto'g'ri tushunish** → tuzatish
- ✅ **Aloqaning uzilishi** → idempotency tekshiruvi
- ✅ **Shovqinli muhit** (ko'cha, restoran)

### 5.2 Xatoliklarni boshqarish (fallback chain)
1. AI tushunmasa → 1 marta qayta so'rash
2. 2 marta tushunmasa → "Sizni operator bilan ulayman" + transfer
3. Catering 24 soat ichida → darhol hotline `+998 98 000 06 04`
4. Tool xatosi → "Texnik nosozlik, qaytadan urinib ko'ring"

### 5.3 Monitoring va loglar
- Har qo'ng'iroq: `call_id`, transcript, tool calls, total cost, duration
- Failure rate, average duration, customer satisfaction (post-call sms)
- Anomalies dashboard — qaysi qadamlarda ko'p uziladi

---

## 💰 Narx baholash (realistik)

| Komponent | Narxi |
|-----------|-------|
| Vapi/Retell | $0.08–0.15/daq |
| OpenAI/Gemini token | $0.01–0.03/daq |
| TTS (Yandex SpeechKit) | ~$5/1M belgi |
| STT (Whisper API) | $0.006/daq |
| Telefon raqami (oyiga) | $5–20 |
| **Jami:** ~$0.15–0.25/qo'ng'iroq (3 daq) | |

**100 qo'ng'iroq/kun × 3 daq × $0.20 = $60/kun ≈ $1,800/oy**

ROI strategiyasi: **birinchi davrda faqat catering** uchun — chunki har
catering buyurtma o'rtacha $120, AI'ga sarflangan ~$0.20 esa <0.2%. Kunlik
oddiy zakazlar (3,000–5,000 so'm/dona) — nisbat past, vaqtinchalik
operatorlar yaxshiroq.

---

## ✅ Boshlashdan oldin javob beriladigan savollar

1. **Inbound** (mijoz bizga qo'ng'iroq qiladi) yoki **outbound** (AI mijozga
   qo'ng'iroq qilib zakaz tasdiqlaydi)?
2. **Faqat catering** uchunmi yoki **kunlik zakazlar** ham?
3. **Telefon raqam** sizda allaqachon bormi (Beeline / Uzmobile)?
4. **Yandex Geocoder API key** bormi yoki ochish kerakmi?
5. **Click/Payme** integratsiya tugatilganmi yoki AI agent boshqa to'lov
   formatidan foydalansinmi?

Shu 5 ta javobdan keyin reja **kod-darajali plan'ga** aylanadi: qaysi
provider, qaysi model, qancha xarajat, integratsiya sxemasi.

---

## 📋 Yaxshilangan faza tartibi (qisqa)

| Faza | Asosiy o'zgarish |
|------|-----------------|
| **0 (yangi)** | Telefon raqam + telefoniya provayderini hal qilish |
| **1** | + `idempotency_key` Order modelida + `phone:+998...` user format |
| **2** | + Read-back script (har catering orderdan oldin) |
| **3** | STT: **Whisper / Yandex**, TTS: **Yandex SpeechKit** (ElevenLabs emas) + filler phrases |
| **4** | + Geocoder (Yandex Geocoder API key kerak) + Click/Payme link tool |
| **5** | + 50 ta dialogue ssenariy + recording consent + cost dashboard |

---

*Hujjat: MuhsinaDollar platforma — AI Call-Operator integratsiya rejasi*
*Oxirgi yangilanish: 2026-04-24*
