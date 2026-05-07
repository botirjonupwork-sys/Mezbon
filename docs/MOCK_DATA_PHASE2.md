# Faza 2 — Telegram WebApp uchun mock JSON

Endpoint javoblarining real-formatdagi misollari. Frontend dasturchi shu shakldagi
ma'lumotni kutib UI yaratsin.

---

## 1. `GET /catering/available-slots?date=2026-05-15&restaurant_id=1`

**Telegram WebApp** — sana tanlanganda 14 ta vaqt-cardchasi:

```json
{
  "date": "2026-05-15",
  "restaurant_id": 1,
  "slots": [
    { "time": "08:00", "status": "active" },
    { "time": "09:00", "status": "active" },
    { "time": "10:00", "status": "active" },
    { "time": "11:00", "status": "busy"   },
    { "time": "12:00", "status": "busy"   },
    { "time": "13:00", "status": "active" },
    { "time": "14:00", "status": "active" },
    { "time": "15:00", "status": "busy"   },
    { "time": "16:00", "status": "active" },
    { "time": "17:00", "status": "active" },
    { "time": "18:00", "status": "active" },
    { "time": "19:00", "status": "active" },
    { "time": "20:00", "status": "busy"   },
    { "time": "21:00", "status": "active" }
  ]
}
```

**Frontend rendering qoidasi**:
- `status === "active"` → yashil/ko'k card, bosish mumkin
- `status === "busy"` → kulrang, disabled, "Band" tooltip

**Bo'sh javob (sana to'liq band)**:
```json
{
  "date": "2026-05-15",
  "restaurant_id": 1,
  "slots": [
    { "time": "08:00", "status": "busy" },
    /* ...hammasi busy... */
    { "time": "21:00", "status": "busy" }
  ]
}
```

**Xato javoblar**:
```json
// Past date
{ "detail": "O'tgan sanada slot bo'lmaydi" }     // 400

// Format xato
{ "detail": "Sana formati: YYYY-MM-DD" }          // 400

// Catering tarif yo'q
{ "detail": "Catering tarifda mavjud emas" }      // 403
```

---

## 2. `GET /admin/stats/resources` (X-Restaurant-Context: 1)

**Admin Dashboard widget** — 5 ta mashina holati:

```json
{
  "restaurant_id": 1,
  "total": 5,
  "busy": 2,
  "available": 3,
  "as_of": "2026-04-30T14:23:45.123456",
  "next_free_at": null,
  "cars": [
    {
      "index": 0,
      "label": "Mashina #1",
      "status": "busy",
      "order_id": 142,
      "reserved_from": "2026-04-30T13:30:00",
      "reserved_until": "2026-04-30T15:30:00",
      "minutes_left": 67
    },
    {
      "index": 1,
      "label": "Mashina #2",
      "status": "busy",
      "order_id": 143,
      "reserved_from": "2026-04-30T14:00:00",
      "reserved_until": "2026-04-30T16:00:00",
      "minutes_left": 97
    },
    {
      "index": 2,
      "label": "Mashina #3",
      "status": "available",
      "order_id": null,
      "reserved_from": null,
      "reserved_until": null,
      "minutes_left": 0
    },
    {
      "index": 3,
      "label": "Mashina #4",
      "status": "available",
      "order_id": null,
      "reserved_from": null,
      "reserved_until": null,
      "minutes_left": 0
    },
    {
      "index": 4,
      "label": "Mashina #5",
      "status": "available",
      "order_id": null,
      "reserved_from": null,
      "reserved_until": null,
      "minutes_left": 0
    }
  ]
}
```

**To'liq band holati** (next_free_at to'ldiriladi):
```json
{
  "restaurant_id": 1,
  "total": 5,
  "busy": 5,
  "available": 0,
  "as_of": "2026-04-30T19:00:00",
  "next_free_at": "2026-04-30T19:23:00",
  "cars": [ /* hammasi busy */ ]
}
```

**Frontend rendering**:
- Statistic kartochkalari: "Jami: 5", "Band: 2", "Bo'sh: 3"
- Mashina kartochkalari: yashil (available), to'q sariq (busy + minutes_left), qizil (overtime)
- `next_free_at` bo'lsa: ⏰ "Keyingi bo'sh slot: 19:23"

---

## 3. `GET /admin/products?product_type=catering&catering_category=Somsalar`

**Catering tab — Somsalar bo'limi**:

```json
[
  {
    "id": 12,
    "name_uz": "Go'shtli somsa",
    "name_ru": "Самса с мясом",
    "description_uz": "Yangi pishirilgan, qo'l tandirda",
    "category_id": 4,
    "price": 7000,
    "image_url": "/static/images/products/abc-123.jpg",
    "is_stop": false,
    "is_active": true,
    "branch_id": null,
    "product_type": "catering",
    "catering_group": "somsa",
    "catering_category": "Somsalar",
    "unit_price_usd": 0.55,
    "unit_price_pickup_uzs": 6500,
    "unit_type": "piece",
    "min_quantity": 100,
    "quantity_step": 1,
    "price_onsite_usd": null,
    "price_pickup_uzs": null,
    "price_delivery_uzs": null,
    "price_per_km_uzs": null
  },
  {
    "id": 14,
    "name_uz": "Dollar somsa",
    "name_ru": "Доллар самса",
    "category_id": 4,
    "price": 12000,
    "image_url": "/static/images/products/dollar.jpg",
    "is_stop": false,
    "is_active": true,
    "product_type": "catering",
    "catering_group": "somsa",
    "catering_category": "Somsalar",
    "unit_price_usd": 1.0,
    "min_quantity": 100
  }
]
```

**Tab tuzilishi (frontend)**:

```jsx
const TABS = [
  { key: 'somsalar',    label: '🥟 Somsalar',     filter: 'Somsalar' },
  { key: 'nonlar',      label: '🍞 Nonlar',       filter: 'Nonlar' },
  { key: 'ichimliklar', label: '🥤 Ichimliklar',  filter: 'Ichimliklar' },
]

// Har tab uchun: api.get(`/admin/products?product_type=catering&catering_category=${tab.filter}`)
```

---

## 4. Telegram WebApp UI — Vaqt-slot tanlash sahifasi

**Mock data + rendering namuna**:

```html
<!-- Slot tanlash card grid -->
<div class="slot-grid">
  <div class="slot active">08:00</div>
  <div class="slot active">09:00</div>
  <div class="slot active">10:00</div>
  <div class="slot busy" title="Band">11:00</div>
  <div class="slot busy" title="Band">12:00</div>
  <div class="slot active selected">13:00</div>  <!-- foydalanuvchi tanladi -->
  <div class="slot active">14:00</div>
  <!-- ... -->
</div>
```

**CSS qoidalari**:
```css
.slot { padding: 12px 16px; border-radius: 8px; cursor: pointer; }
.slot.active   { background: #e6f7ff; border: 1px solid #1677ff; color: #1677ff; }
.slot.busy     { background: #f5f5f5; color: #999; cursor: not-allowed; }
.slot.selected { background: #1677ff; color: #fff; box-shadow: 0 2px 8px rgba(22,119,255,0.3); }
```

**JS oqim (Telegram WebApp)**:
```js
const tg = window.Telegram.WebApp
tg.ready()

// 1. Sana tanlandi
async function loadSlots(date) {
  const r = await fetch(`/api/catering/available-slots?date=${date}&restaurant_id=${rid}`, {
    headers: { Authorization: `Bearer ${token}` }
  })
  const data = await r.json()
  renderSlots(data.slots)
}

// 2. Slot tanlandi → keyingi qadamga
function selectSlot(time) {
  state.event_date = `${state.date}T${time}:00`
  tg.MainButton.setText(`Tasdiqlash (${time})`)
  tg.MainButton.show()
}
```

---

## 5. Admin Dashboard — Resource Widget React mock

```jsx
import { useEffect, useState } from 'react'
import { Card, Row, Col, Statistic, Tag, Progress, Tooltip } from 'antd'
import { CarOutlined, ClockCircleOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'

export function ResourcesWidget({ restaurantId }) {
  const [data, setData] = useState(null)

  useEffect(() => {
    const load = () => {
      fetch('/api/admin/stats/resources', {
        headers: {
          'Authorization': `Bearer ${token}`,
          'X-Restaurant-Context': String(restaurantId),
        },
      }).then((r) => r.json()).then(setData)
    }
    load()
    const t = setInterval(load, 30_000)  // har 30s yangilash
    return () => clearInterval(t)
  }, [restaurantId])

  if (!data) return null

  const usagePct = data.total > 0 ? Math.round((data.busy / data.total) * 100) : 0

  return (
    <Card title={<><CarOutlined /> Mashinalar holati</>} size="small">
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={8}><Statistic title="Jami" value={data.total} /></Col>
        <Col xs={8}><Statistic title="Band" value={data.busy} valueStyle={{ color: '#fa8c16' }} /></Col>
        <Col xs={8}><Statistic title="Bo'sh" value={data.available} valueStyle={{ color: '#52c41a' }} /></Col>
      </Row>
      <Progress percent={usagePct}
        status={usagePct >= 100 ? 'exception' : usagePct >= 80 ? 'normal' : 'success'} />
      {data.next_free_at && (
        <div style={{ marginTop: 8, color: '#999', fontSize: 12 }}>
          <ClockCircleOutlined /> Keyingi bo'sh slot: {dayjs(data.next_free_at).format('HH:mm')}
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(120px,1fr))', gap: 8, marginTop: 12 }}>
        {data.cars.map((car) => (
          <Tooltip key={car.index}
            title={car.status === 'busy'
              ? `Zakaz #${car.order_id} • ${car.minutes_left} daq qoldi`
              : "Bo'sh — yangi zakaz qabul qilish mumkin"}>
            <Card size="small" style={{
              background: car.status === 'busy' ? '#fff7e6' : '#f6ffed',
              borderColor: car.status === 'busy' ? '#ffd591' : '#b7eb8f',
            }}>
              <div style={{ fontWeight: 600 }}>{car.label}</div>
              <Tag color={car.status === 'busy' ? 'orange' : 'green'}>
                {car.status === 'busy' ? `🚗 Yo'lda • ${car.minutes_left} daq` : '✓ Bo\'sh'}
              </Tag>
              {car.status === 'busy' && (
                <div style={{ fontSize: 11, color: '#999', marginTop: 4 }}>
                  Zakaz #{car.order_id}
                </div>
              )}
            </Card>
          </Tooltip>
        ))}
      </div>
    </Card>
  )
}
```

---

## 6. Foydalanish va xavfsizlik qoidalari

| Endpoint | Auth | Header | Audit |
|---|---|---|---|
| `GET /catering/available-slots` | optional super | — | yo'q |
| `GET /admin/stats/resources` | majburiy | `X-Restaurant-Context` (super) | faqat mutatsiya |
| `GET /admin/products` | majburiy | `restaurant_id` query | yo'q |
| `PUT /admin/settings` | majburiy | `X-Restaurant-Context` (super) | **yoziladi** |
| `PUT /admin/pos/config` | majburiy | `X-Restaurant-Context` (super) | **yoziladi** |
| `POST /admin/pos/test-print` | majburiy | `X-Restaurant-Context` (super) | **yoziladi** |

**Rate limiting**: `/auth/login` 5/min IP, qolgan endpointlar 300/min IP (default).

**IDOR himoya scenariy**:
```bash
# Restaurant admin token (rid=1) + restaurant_id=2 query → 403
curl /api/admin/stats/resources?restaurant_id=2 \
  -H "Authorization: Bearer <jwt-rid-1>"
# → {"detail": "Siz boshqa restoran ma'lumotlariga kira olmaysiz"}

# Super-admin token + X-Restaurant-Context: 2 → 200 + audit
curl /api/admin/stats/resources \
  -H "Authorization: Bearer <super-jwt>" \
  -H "X-Restaurant-Context: 2"
# → 200, super_admin_actions ga yozuv tushadi (faqat mutatsiyada)
```

---

## 7. Test natijalari (lokal staging)

| Test | Natija |
|---|---|
| `/catering/available-slots?date=2026-05-15` | ✅ 14 ta slot, hammasi `active` (bo'sh DB) |
| `/admin/stats/resources` super + X-Restaurant-Context: 1 | ✅ 5 mashina hammasi available |
| `/admin/products?catering_category=Somsalar` | ✅ filter ishlaydi |
| Super-admin no header | ✅ 400 "X-Restaurant-Context kerak" |
| Past date | ✅ 400 |
| Restaurant admin + boshqa rid | ✅ 403 IDOR |
| Restaurant admin + own rid | ✅ 200 |
