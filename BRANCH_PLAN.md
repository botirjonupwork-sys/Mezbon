# FILIAL (BRANCH) TIZIMI — BATAFSIL REJA

## Hozirgi holat

- Serverda multi-restoran arxitekturasi bor (restaurant_id barcha jadvallarda)
- Lokal kod eski — single-restoran
- Filial tushunchasi hech qayerda yo'q
- Barcha sozlamalar restoran darajasida
- Kuryerlar umumiy (filialga bog'lanmagan)

---

## MAQSAD

Har bir restoran bir nechta filialga ega bo'ladi:
- Har filialning o'z menyusi, kuryerlari, sozlamalari
- Bot foydalanuvchidan joylashuv olib yaqin filialni tanlaydi
- Admin panel filial bo'yicha filter bilan ishlaydi
- Super admin restoran ichida filial qo'shadi/boshqaradi

---

## QADAM 1: Database — Branch modeli

**Fayl:** `database/models.py`

### 1.1 Yangi Branch jadvali
```python
class Branch(Base):
    __tablename__ = "branches"
    id              = Column(Integer, primary_key=True, index=True)
    restaurant_id   = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    name            = Column(String, nullable=False)       # "Chilonzor filiali"
    address         = Column(String)
    phone           = Column(String)
    latitude        = Column(Float)
    longitude       = Column(Float)
    work_hours_from = Column(String, default="09:00")
    work_hours_until= Column(String, default="22:00")
    min_order       = Column(Float, default=30000)
    delivery_base_fee = Column(Float, default=10000)
    delivery_per_km = Column(Float, default=3000)
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, server_default=func.now())

    # Relationships
    restaurant = relationship("Restaurant", backref="branches")
    categories = relationship("Category", backref="branch")
    products   = relationship("Product", backref="branch")
    orders     = relationship("Order", backref="branch")
    couriers   = relationship("Courier", backref="branch")
    reviews    = relationship("Review", backref="branch")
```

### 1.2 Mavjud jadvallarni o'zgartirish
Quyidagi jadvallarga `branch_id` ustuni qo'shiladi:
- `categories` → `branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)`
- `products` → `branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)`
- `orders` → `branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)`
- `couriers` → `branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)`
- `reviews` → `branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)`

> nullable=True — eski ma'lumotlar buzilmasligi uchun

### 1.3 Alembic migration
```
alembic revision --autogenerate -m "add branches table and branch_id FK"
alembic upgrade head
```

### 1.4 Default filial yaratish
Mavjud har bir restoran uchun bitta default filial yaratiladi.
Eski ma'lumotlar (categories, products, orders...) shu default filialga bog'lanadi.

**Natija:** Database tayyor, barcha jadvallar branch_id ni qo'llab-quvvatlaydi.

---

## QADAM 2: Backend API — Branch endpointlari

**Fayl:** `api/routes/branches.py` (yangi)

### 2.1 Super Admin uchun Branch CRUD
```
GET    /super/restaurants/{restaurant_id}/branches     — filiallar ro'yxati
POST   /super/restaurants/{restaurant_id}/branches     — filial qo'shish
PUT    /super/branches/{branch_id}                     — filial tahrirlash
DELETE /super/branches/{branch_id}                     — filial o'chirish
```

### 2.2 Admin Panel uchun Branch API
```
GET    /admin/branches                                 — joriy restoranlar filiallar
GET    /admin/branches/{branch_id}/settings            — filial sozlamalari
PUT    /admin/branches/{branch_id}/settings            — filial sozlamalarini yangilash
```

### 2.3 Bot uchun Branch API
```
GET    /branches/nearest?lat=X&lon=Y&restaurant_id=Z   — yaqin filiallar (masofasi bilan)
GET    /branches/{branch_id}                            — filial ma'lumotlari
GET    /branches/{branch_id}/categories                 — filial kategoriyalari
GET    /branches/{branch_id}/products                   — filial mahsulotlari
GET    /branches/{branch_id}/is-open                    — filial ochiqmi
```

**Natija:** Barcha kerakli backend endpointlar tayyor.

---

## QADAM 3: Mavjud API routelarni branch_id bilan yangilash

### 3.1 admin.py o'zgarishlari
**Fayl:** `api/routes/admin.py`

- `GET /admin/stats` → `?branch_id=X` parametri qo'shiladi
- `GET /admin/orders` → `?branch_id=X` filter
- `GET /admin/products` → `?branch_id=X` filter
- `GET /admin/categories` → `?branch_id=X` filter
- `GET /admin/users` → `?branch_id=X` (shu filialga buyurtma berganlar)
- `POST /admin/products` → `branch_id` body'da keladi
- `POST /admin/categories` → `branch_id` body'da keladi

### 3.2 orders.py o'zgarishlari
**Fayl:** `api/routes/orders.py`

- `POST /orders/` → `branch_id` body'da keladi, order shu filialga bog'lanadi
- Yetkazib berish narxi filial koordinatasidan hisoblanadi
- Ish vaqti filial bo'yicha tekshiriladi
- Kuryer notifikatsiyasi faqat shu filial kuryerlariga boradi

### 3.3 couriers.py o'zgarishlari
**Fayl:** `api/routes/couriers.py`

- `POST /couriers/register` → `branch_id` body'da keladi
- `GET /couriers/{telegram_id}/orders` → faqat o'z filiali zakazlari
- `GET /couriers/` (admin) → `?branch_id=X` filter
- `PATCH /couriers/{id}/status` → branch kontekstida

### 3.4 menu.py o'zgarishlari
**Fayl:** `api/routes/menu.py`

- `GET /menu/categories` → `?branch_id=X` filter
- `GET /menu/products` → `?branch_id=X` filter
- `GET /menu/categories/{id}/products` → branch kontekstida

### 3.5 reviews.py o'zgarishlari
**Fayl:** `api/routes/reviews.py`

- `POST /reviews/` → `branch_id` body'da
- `GET /reviews/` → `?branch_id=X` filter
- `GET /reviews/stats` → `?branch_id=X` filter

**Natija:** Barcha mavjud endpointlar branch_id ni qo'llab-quvvatlaydi.

---

## QADAM 4: Super Admin Panel — Filial boshqaruvi

**Fayl:** `super_admin/src/pages/RestaurantForm.jsx`

### 4.1 Filiallar bo'limi qo'shish
RestaurantForm sahifasiga "Filiallar" tab/section qo'shiladi:
- Filiallar jadvali: nom, manzil, ish vaqti, holat, kuryerlar soni
- "Filial qo'shish" tugmasi → Modal:
  - Nom (input)
  - Manzil (input)
  - Telefon (input)
  - Xarita (Yandex Map — koordinata tanlash)
  - Ish vaqti (TimePicker: dan — gacha)
  - Min buyurtma (InputNumber)
  - Yetkazib berish narxi: bazaviy + km boshiga (InputNumber)
- Tahrirlash tugmasi → shu modal
- O'chirish tugmasi → Popconfirm
- Holat toggle (faol/nofaol)

### 4.2 API funksiyalar
**Fayl:** `super_admin/src/api/index.js`
```javascript
export const getBranches = (restaurantId) => api.get(`/super/restaurants/${restaurantId}/branches`)
export const createBranch = (restaurantId, data) => api.post(`/super/restaurants/${restaurantId}/branches`, data)
export const updateBranch = (branchId, data) => api.put(`/super/branches/${branchId}`, data)
export const deleteBranch = (branchId) => api.delete(`/super/branches/${branchId}`)
```

**Natija:** Super admin restoran ichida filial yaratishi, tahrirlashi, o'chirishi mumkin.

---

## QADAM 5: Admin Panel — Sidebar Branch Select

### 5.1 Branch Store
**Fayl:** `admin/src/store/branch.js` (yangi)
```javascript
// Zustand store
{
  branches: [],           // barcha filiallar
  selectedBranch: null,   // null = "Barcha", id = tanlangan filial
  setBranch: (id) => ...,
  setBranches: (list) => ...,
}
```

### 5.2 Layout.jsx o'zgarishlari
**Fayl:** `admin/src/components/Layout.jsx`

Sidebar tepasiga Select qo'shiladi:
```
┌─────────────────┐
│ Muhsina Admin   │
│ ┌─────────────┐ │
│ │ Barcha ▼    │ │  ← filial tanlash
│ └─────────────┘ │
│ Dashboard       │
│ Zakazlar        │
│ Menyu           │
│ Mijozlar        │
│ Baholar         │
│ Kuryerlar       │
│ ─────────────── │
│ Adminlar        │
│ Sozlamalar      │
│ Filiallar       │  ← yangi sahifa
└─────────────────┘
```

- App yuklanganda `/admin/branches` dan filiallar olinadi
- Select o'zgarganda `selectedBranch` yangilanadi
- Barcha sahifalar avtomatik qayta yuklanadi

### 5.3 API index.js ga branch funksiyalar
**Fayl:** `admin/src/api/index.js`
```javascript
// Branch
export const getBranches = () => api.get('/admin/branches')
export const getBranchSettings = (id) => api.get(`/admin/branches/${id}/settings`)
export const updateBranchSettings = (id, data) => api.put(`/admin/branches/${id}/settings`, data)
```

### 5.4 Barcha mavjud API funksiyalarga branch_id qo'shish
```javascript
export const getStats = (params) => api.get('/admin/stats', { params })
// params ichiga branch_id qo'shiladi: { ...params, branch_id: selectedBranch }
```

**Natija:** Admin panel filial bo'yicha ishlaydi.

---

## QADAM 6: Admin Panel — Barcha sahifalarni branch filter bilan yangilash

### 6.1 Dashboard.jsx
- Statistika `branch_id` bo'yicha
- Zakazlar jadvali `branch_id` bo'yicha
- `selectedBranch` o'zgarganda qayta yuklash

### 6.2 Orders.jsx
- Zakazlar `branch_id` bo'yicha filter
- Filial ustuni qo'shiladi (agar "Barcha" tanlangan bo'lsa)

### 6.3 Menu.jsx
- Kategoriya va mahsulotlar `branch_id` bo'yicha
- Mahsulot qo'shganda `branch_id` yuboriladi

### 6.4 Users.jsx
- Foydalanuvchilar `branch_id` bo'yicha (kimlar shu filialga buyurtma bergan)

### 6.5 Reviews.jsx
- Baholar `branch_id` bo'yicha

### 6.6 Couriers.jsx
- Kuryerlar `branch_id` bo'yicha
- Kuryer qaysi filialga tegishli ekani ko'rinadi

### 6.7 Settings.jsx
- Filial tanlanganda → shu filial sozlamalari
- Ish vaqti, min buyurtma, yetkazib berish, manzil, xarita — hammas filialga alohida
- "Barcha" tanlanganda → umumiy restoran sozlamalari

**Natija:** Admin panelning barcha sahifalari filial bo'yicha ishlaydi.

---

## QADAM 7: Telegram Bot — Filial tanlash

### 7.1 States.py o'zgarishlari
**Fayl:** `bot/states.py`
```python
class BranchSelect(StatesGroup):
    waiting_location = State()    # joylashuv kutish
    choosing_branch = State()     # filial tanlash
```

### 7.2 Start flow o'zgarishlari
**Fayl:** `bot/handlers/start.py`

Ro'yxatdan o'tgandan keyin:
1. Bot: "Yaqin filialni topish uchun joylashuvingizni yuboring"
2. Foydalanuvchi: GPS lokatsiya yuboradi
3. Bot: API dan yaqin filiallarni oladi (`/branches/nearest`)
4. Bot: Inline buttonlar bilan ko'rsatadi:
   ```
   Sizga yaqin filiallar:
   [Chilonzor (0.8 km) ✅]
   [Sergeli (2.3 km) ✅]
   [Yunusobod (4.1 km) ⏰ Yopiq]
   ```
5. Foydalanuvchi tanlaydi → FSM data'ga `branch_id` saqlanadi

### 7.3 Main keyboard o'zgarishlari
**Fayl:** `bot/keyboards/main.py`

Yangi tugma qo'shiladi:
```
🍽 Menyu        | 🛒 Savat
📦 Zakazlarim   | 👤 Profil
🏪 Filial: [nom] | 📞 Bog'lanish
```

### 7.4 Menu handler o'zgarishlari
**Fayl:** `bot/handlers/menu.py`

- Menyu ochganda avval `branch_id` tekshiriladi
- Agar tanlangan bo'lmasa → filial tanlash ekraniga yo'naltiradi
- Kategoriya va mahsulotlar `/branches/{id}/categories` dan yuklanadi

### 7.5 Cart handler o'zgarishlari
**Fayl:** `bot/handlers/cart.py`

- Savatga qo'shganda `branch_id` saqlanadi
- Boshqa filial tanlansa savat tozalanadi (yoki ogohlantirish beriladi)

### 7.6 Order handler o'zgarishlari
**Fayl:** `bot/handlers/order.py`

- Buyurtma yaratganda `branch_id` yuboriladi
- Yetkazib berish narxi filial koordinatasidan hisoblanadi
- Ish vaqti filial bo'yicha tekshiriladi
- `_is_open()` → filial ish vaqtini tekshiradi

### 7.7 api_client.py o'zgarishlari
**Fayl:** `bot/api_client.py`

Yangi funksiyalar:
```python
async def get_nearest_branches(lat, lon, restaurant_id):
    ...
async def get_branch_categories(branch_id):
    ...
async def get_branch_products(branch_id):
    ...
async def is_branch_open(branch_id):
    ...
```

**Natija:** Bot filial tanlash va filial bo'yicha menyu ko'rsatadi.

---

## QADAM 8: Courier Bot — Filial bo'yicha ishlash

### 8.1 Ro'yxatdan o'tish o'zgarishlari
**Fayl:** `courier_bot/handlers/start.py`

- Kuryer ro'yxatdan o'tganda filial tanlaydi:
  ```
  Qaysi filialda ishlaysiz?
  [Chilonzor]
  [Sergeli]
  [Yunusobod]
  ```
- `branch_id` bilan `/couriers/register` ga yuboriladi

### 8.2 Orders handler o'zgarishlari
**Fayl:** `courier_bot/handlers/orders.py`

- Faqat o'z filiali zakazlari ko'rinadi
- Zakaz qabul qilganda filial tekshiriladi

**Natija:** Kuryerlar faqat o'z filiali zakazlarini ko'radi va qabul qiladi.

---

## QADAM 9: Migration va Deploy

### 9.1 Alembic migration yaratish
```bash
cd /Users/nazir/Desktop/MuhsinaDollar
alembic revision --autogenerate -m "add branches"
```

### 9.2 Migration script — default filial
```python
# Default filial yaratish skripti
# Har restoran uchun bitta "Asosiy" filial
# Eski ma'lumotlarni shu filialga bog'lash
```

### 9.3 Serverga deploy
```bash
# Fayllarni ko'chirish
scp -r database/ api/ bot/ courier_bot/ root@65.109.5.207:/opt/restaurant/

# Migrationni ishga tushirish
ssh root@65.109.5.207 "cd /opt/restaurant && alembic upgrade head"

# Servislarni qayta ishga tushirish
ssh root@65.109.5.207 "systemctl restart restaurant-api && systemctl restart restaurant-bots"

# Frontend rebuild
cd admin && npm run build
scp -r admin/dist/* root@65.109.5.207:/opt/restaurant/admin/dist/

cd super_admin && npm run build
scp -r super_admin/dist/* root@65.109.5.207:/opt/restaurant/super_admin/dist/
```

**Natija:** Serverda filial tizimi ishlaydi.

---

## ISH TARTIBI VA TAXMINIY HAJM

| # | Qadam | Fayllar soni | Prioritet |
|---|-------|-------------|-----------|
| 1 | Database: Branch modeli + migration | 2 | YUQORI |
| 2 | Backend: Branch API endpointlari (yangi) | 1 | YUQORI |
| 3 | Backend: Mavjud routelarni branch filter | 6 | YUQORI |
| 4 | Super Admin: Filial CRUD UI | 2 | YUQORI |
| 5 | Admin: Branch store + sidebar select | 3 | YUQORI |
| 6 | Admin: Barcha sahifalarni branch filter | 7 | O'RTA |
| 7 | Bot: Filial tanlash + menyu | 6 | O'RTA |
| 8 | Courier Bot: Filial bo'yicha | 2 | O'RTA |
| 9 | Migration + Deploy | 3 | OXIRGI |

---

## ESLATMALAR

- Server SQLite ishlatadi, lokal PostgreSQL — migration ikkala DB ga mos bo'lishi kerak
- Serverda allaqachon `restaurant_id` bor, `branch_id` qo'shiladi
- Eski ma'lumotlar uchun `branch_id` nullable bo'ladi, migration skript default filial yaratadi
- Frontend `selectedBranch = null` bo'lsa "Barcha" deb ishlaydi
- Bot savati filialga bog'langan — filial almashtirganda savat tozalanadi
