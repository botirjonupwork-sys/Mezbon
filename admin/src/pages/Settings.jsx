import { useEffect, useState, useRef, useCallback } from 'react'
import {
  Card, Form, Input, InputNumber, Select, Button, Typography,
  Row, Col, message, Spin, TimePicker, Space, Switch, Tabs, Alert
} from 'antd'
import {
  SaveOutlined, EnvironmentOutlined, PhoneOutlined,
  ShopOutlined, ClockCircleOutlined, CarOutlined,
  UserOutlined, LockOutlined, CreditCardOutlined,
  GiftOutlined, GlobalOutlined, DollarOutlined,
  RobotOutlined, PrinterOutlined,
} from '@ant-design/icons'
import POSSettings from '../components/POSSettings'
import { getSettings, updateSettings, getProfile, updateProfile, getBranchSettings, updateBranchSettings, getMyPlan } from '../api'
import { useAuthStore } from '../store/auth'
import { useBranchStore } from '../store/branch'
import dayjs from 'dayjs'

const { Title, Text } = Typography

// ── Yandex Map Component ────────────────────────────────
function YandexMap({ lat, lon, onChange }) {
  const mapRef = useRef(null)
  const mapInstance = useRef(null)
  const markerRef = useRef(null)

  const initMap = useCallback(() => {
    if (!window.ymaps || mapInstance.current) return
    window.ymaps.ready(() => {
      const map = new window.ymaps.Map(mapRef.current, {
        center: [lat || 41.2995, lon || 69.2401],
        zoom: 15,
        controls: ['zoomControl', 'searchControl', 'geolocationControl'],
      })
      const placemark = new window.ymaps.Placemark(
        [lat || 41.2995, lon || 69.2401],
        { hintContent: 'Restoran joylashuvi' },
        { preset: 'islands#redFoodIcon', draggable: true }
      )
      placemark.events.add('dragend', () => {
        const coords = placemark.geometry.getCoordinates()
        onChange?.(coords[0], coords[1])
      })
      map.events.add('click', (e) => {
        const coords = e.get('coords')
        placemark.geometry.setCoordinates(coords)
        onChange?.(coords[0], coords[1])
      })
      map.geoObjects.add(placemark)
      mapInstance.current = map
      markerRef.current = placemark
    })
  }, [lat, lon, onChange])

  useEffect(() => {
    if (window.ymaps) { initMap(); return }
    const script = document.createElement('script')
    script.src = 'https://api-maps.yandex.ru/2.1/?apikey=&lang=ru_RU'
    script.onload = initMap
    document.head.appendChild(script)
  }, [initMap])

  useEffect(() => {
    if (markerRef.current && lat && lon) {
      markerRef.current.geometry.setCoordinates([lat, lon])
      mapInstance.current?.setCenter([lat, lon])
    }
  }, [lat, lon])

  return (
    <div ref={mapRef} style={{
      width: '100%', height: 320, borderRadius: 8,
      overflow: 'hidden', border: '1px solid #d9d9d9',
    }} />
  )
}

// ── Main Settings Page ─────────────────────────────────
export default function Settings() {
  const [form] = Form.useForm()
  const [profileForm] = Form.useForm()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [savingProfile, setSavingProfile] = useState(false)
  const [mapLat, setMapLat] = useState(41.2995)
  const [mapLon, setMapLon] = useState(69.2401)
  const [activeTab, setActiveTab] = useState('restaurant')
  const [aiAllowed, setAiAllowed] = useState(false)  // Pro tarif bormi
  const [botStatus, setBotStatus] = useState(null)
  const [botChecking, setBotChecking] = useState(false)
  const { setAuth, token, currentRestaurantId: restaurantId } = useAuthStore()
  const selectedBranchId = useBranchStore((s) => s.selectedBranchId)
  const restParams = restaurantId ? { restaurant_id: restaurantId } : {}

  useEffect(() => {
    if (!restaurantId) { setAiAllowed(false); return }
    getMyPlan(restParams)
      .then((r) => setAiAllowed(!!r.data?.features?.ai_agent))
      .catch(() => setAiAllowed(false))
  }, [restaurantId])

  useEffect(() => {
    if (!restaurantId && !selectedBranchId) { setLoading(false); return }
    setLoading(true)
    const settingsPromise = selectedBranchId
      ? getBranchSettings(selectedBranchId)
      : getSettings(restParams)

    Promise.all([settingsPromise, getProfile(restParams)])
      .then(([settingsRes, profileRes]) => {
        const d = { ...(settingsRes.data || {}) }
        if (selectedBranchId) {
          d.restaurant_name = d.name || ''
          d.restaurant_lat = d.latitude
          d.restaurant_lon = d.longitude
        }
        if (d.work_hours_from) d.work_hours_from = dayjs(d.work_hours_from, 'HH:mm')
        if (d.work_hours_until) d.work_hours_until = dayjs(d.work_hours_until, 'HH:mm')
        if (!d.delivery_provider) d.delivery_provider = 'own'
        if (d.yandex_test_mode === undefined || d.yandex_test_mode === null) d.yandex_test_mode = true
        if (d.currency_auto === undefined || d.currency_auto === null) d.currency_auto = true
        form.setFieldsValue(d)
        if (d.restaurant_lat) setMapLat(d.restaurant_lat)
        if (d.restaurant_lon) setMapLon(d.restaurant_lon)

        const p = profileRes.data || {}
        profileForm.setFieldsValue({ username: p.username, name: p.name })
      })
      .catch(() => message.error('Sozlamalarni yuklashda xato'))
      .finally(() => setLoading(false))
  }, [selectedBranchId, restaurantId])

  const handleMapChange = useCallback((lat, lon) => {
    const r = (v) => Math.round(v * 10000) / 10000
    setMapLat(r(lat))
    setMapLon(r(lon))
    form.setFieldsValue({ restaurant_lat: r(lat), restaurant_lon: r(lon) })
  }, [form])

  const handleSave = async () => {
    setSaving(true)
    try {
      const values = await form.validateFields()
      if (values.work_hours_from) values.work_hours_from = values.work_hours_from.format('HH:mm')
      if (values.work_hours_until) values.work_hours_until = values.work_hours_until.format('HH:mm')
      if (selectedBranchId) {
        const b = { ...values, name: values.restaurant_name, latitude: values.restaurant_lat, longitude: values.restaurant_lon }
        delete b.restaurant_name; delete b.restaurant_lat; delete b.restaurant_lon
        await updateBranchSettings(selectedBranchId, b)
      } else {
        await updateSettings(values, restParams)
      }
      message.success('✅ Sozlamalar saqlandi')
    } catch (err) {
      if (!err?.errorFields) message.error('Saqlashda xato')
    } finally {
      setSaving(false)
    }
  }

  const handleProfileSave = async () => {
    setSavingProfile(true)
    try {
      const values = await profileForm.validateFields()
      const payload = {}
      if (values.username) payload.username = values.username
      if (values.new_password) {
        if (!values.current_password) {
          message.error('Parolni o\'zgartirish uchun eski parol kerak')
          setSavingProfile(false)
          return
        }
        if (values.new_password !== values.confirm_password) {
          message.error('Yangi parol va tasdiq mos kelmaydi')
          setSavingProfile(false)
          return
        }
        payload.new_password = values.new_password
        payload.current_password = values.current_password
      }
      await updateProfile(payload, restParams)
      profileForm.setFieldsValue({
        new_password: '', confirm_password: '', current_password: '',
      })
      if (values.username) setAuth(token, { name: values.username }, restaurantId)
      message.success('✅ Profil yangilandi')
    } catch (err) {
      if (err?.response?.data?.detail) message.error(err.response.data.detail)
      else if (!err?.errorFields) message.error('Xato')
    } finally {
      setSavingProfile(false)
    }
  }

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 100 }} />

  // ── Tab contents ─────────────────────────────────────

  const restaurantTab = (
    <>
      <Card title={<><ShopOutlined /> Restoran ma'lumotlari</>} size="small" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Form.Item name="restaurant_name" label="Nomi" rules={[{ required: true, message: 'Nom kiriting' }]}>
              <Input prefix={<ShopOutlined />} placeholder="Muhsina Dollar Somsa" />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item name="phone" label="Telefon" rules={[
              { required: true, message: 'Telefon kiriting' },
              { pattern: /^\+998\d{9}$/, message: '+998XXXXXXXXX formatida' }
            ]}>
              <Input prefix={<PhoneOutlined />} placeholder="+998901234567" maxLength={13} />
            </Form.Item>
          </Col>
          <Col xs={24}>
            <Form.Item name="address" label="Manzil" rules={[{ required: true, message: 'Manzil kiriting' }]}>
              <Input prefix={<EnvironmentOutlined />} placeholder="Toshkent sh., 7-mavze" />
            </Form.Item>
          </Col>
        </Row>
      </Card>

      <Card title={<><EnvironmentOutlined /> Joylashuv (xaritadan belgilang)</>} size="small">
        <YandexMap lat={mapLat} lon={mapLon} onChange={handleMapChange} />
        <Row gutter={16} style={{ marginTop: 12 }}>
          <Col xs={12}>
            <Form.Item name="restaurant_lat" label="Kenglik" style={{ marginBottom: 0 }}>
              <InputNumber style={{ width: '100%' }} step={0.0001} precision={4} onChange={(v) => v && setMapLat(v)} />
            </Form.Item>
          </Col>
          <Col xs={12}>
            <Form.Item name="restaurant_lon" label="Uzunlik" style={{ marginBottom: 0 }}>
              <InputNumber style={{ width: '100%' }} step={0.0001} precision={4} onChange={(v) => v && setMapLon(v)} />
            </Form.Item>
          </Col>
        </Row>
      </Card>
    </>
  )

  const workHoursTab = (
    <>
      <Card title={<><ClockCircleOutlined /> Ish vaqti</>} size="small" style={{ marginBottom: 16 }}>
        <Row gutter={16} align="middle">
          <Col>
            <Form.Item name="work_hours_from" label="Ochilish" rules={[{ required: true }]} style={{ marginBottom: 0 }}>
              <TimePicker format="HH:mm" minuteStep={15} style={{ width: 120 }} needConfirm={false} />
            </Form.Item>
          </Col>
          <Col><Text style={{ fontSize: 20, marginTop: 30, display: 'block' }}>—</Text></Col>
          <Col>
            <Form.Item name="work_hours_until" label="Yopilish" rules={[{ required: true }]} style={{ marginBottom: 0 }}>
              <TimePicker format="HH:mm" minuteStep={15} style={{ width: 120 }} needConfirm={false} />
            </Form.Item>
          </Col>
        </Row>
      </Card>

      <Card title={<><CarOutlined /> Minimal buyurtma summasi</>} size="small">
        <Form.Item name="min_order" label="Minimal buyurtma (so'm)" rules={[{ required: true }]}
          extra="Shu summadan past buyurtmalar qabul qilinmaydi" style={{ maxWidth: 400, marginBottom: 0 }}>
          <InputNumber style={{ width: '100%' }} min={0} max={1000000} step={5000}
            formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
            parser={(v) => v.replace(/,/g, '')} />
        </Form.Item>
      </Card>
    </>
  )

  const deliveryTab = (
    <>
      {!selectedBranchId && (
        <Card title={<><CarOutlined /> Dastavka xizmati</>} size="small" style={{ marginBottom: 16 }}>
          <Form.Item name="delivery_provider" label="Dastavka turi"
            extra="O'z kuryerlaringiz yoki Yandex Delivery. Narx kuryer bilan kelishiladi yoki Yandex avtomatik hisoblaydi.">
            <Select options={[
              { value: 'own', label: "🚗 O'z kuryerlarim (narx kuryer bilan kelishiladi)" },
              { value: 'yandex', label: '🟡 Yandex Delivery (avtomatik narx)' },
            ]} style={{ maxWidth: 400 }} />
          </Form.Item>

          <Form.Item noStyle shouldUpdate={(p, c) => p.delivery_provider !== c.delivery_provider}>
            {({ getFieldValue }) => getFieldValue('delivery_provider') === 'yandex' && (
              <>
                <Alert type="info" showIcon style={{ marginBottom: 16 }}
                  message="Yandex Delivery ulash"
                  description="OAuth token olish uchun dostavka.yandex.ru/account ga kiring. Kabinetda 'Integratsiya' bo'limi ochilgandan keyin token generatsiya qilinadi." />
                <Form.Item name="yandex_api_token" label="Yandex OAuth Token (y0_Ag...)"
                  extra="Shartnoma imzolangandan keyin beriladi. Bo'sh qoldirilsa test rejimi ishlaydi.">
                  <Input.Password placeholder="y0_Ag..." autoComplete="off" />
                </Form.Item>
                <Form.Item name="yandex_test_mode" label="Test rejimi" valuePropName="checked"
                  extra="Yoqilgan holatida haqiqiy buyurtma yaratilmaydi (sandbox)">
                  <Switch checkedChildren="Test" unCheckedChildren="Production" />
                </Form.Item>
              </>
            )}
          </Form.Item>
        </Card>
      )}
    </>
  )

  const apiBase = (() => {
    const env = import.meta.env.VITE_API_URL
    if (env) return env.startsWith('http') ? env : window.location.origin + env
    return window.location.origin + '/api'
  })()
  const clickWebhookUrl = `${apiBase.replace(/\/$/, '')}/payments/click/webhook`
  const paymeWebhookUrl = `${apiBase.replace(/\/$/, '')}/payments/payme/webhook`

  const copyToClipboard = (text, label) => {
    try {
      navigator.clipboard.writeText(text)
      message.success(`${label} nusxa olindi`)
    } catch {
      message.error('Nusxa olib bo\'lmadi')
    }
  }

  const paymentTab = (
    <>
      {!selectedBranchId && (<>
        {/* QQS / VAT */}
        <Card title={<><DollarOutlined /> Soliq (QQS / VAT)</>} size="small" style={{ marginBottom: 16 }}>
          <Alert type="info" showIcon style={{ marginBottom: 16 }}
            message="QQS to'lovchi flagi"
            description="Agar restoran QQS to'lovchi bo'lsa, har to'langan summadan QQS qismi avtomatik hisoblanadi va fiskal chekda alohida ko'rsatiladi. O'zR uchun standart: 12%." />
          <Row gutter={16}>
            <Col xs={24} md={8}>
              <Form.Item name="is_vat_payer" label="QQS to'lovchi" valuePropName="checked">
                <Switch checkedChildren="Ha" unCheckedChildren="Yo'q" />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item noStyle shouldUpdate={(p, c) => p.is_vat_payer !== c.is_vat_payer}>
                {({ getFieldValue }) => getFieldValue('is_vat_payer') && (
                  <Form.Item name="vat_percent" label="QQS foizi (%)">
                    <InputNumber min={0} max={100} step={0.5} style={{ width: '100%' }} />
                  </Form.Item>
                )}
              </Form.Item>
            </Col>
          </Row>
        </Card>

        {/* Test/Live rejim */}
        <Card title={<><DollarOutlined /> To'lov rejimi (Test / Live)</>} size="small" style={{ marginBottom: 16 }}>
          <Alert type="warning" showIcon style={{ marginBottom: 16 }}
            message="Test rejim — sandbox kartalar bilan sinov"
            description="Test rejimda Click/Payme/Telegram TEST tokenlari ishlaydi, real pul yechilmaydi. Live rejimda real to'lovlar amalga oshiriladi." />
          <Form.Item name="payment_test_mode" label="Test rejim" valuePropName="checked">
            <Switch checkedChildren="🧪 TEST" unCheckedChildren="💰 LIVE" />
          </Form.Item>
        </Card>

        {/* Telegram Native Payments tokenlari */}
        <Card title={<><CreditCardOutlined /> Telegram to'lov tokenlari (BotFather)</>} size="small" style={{ marginBottom: 16 }}>
          <Alert type="info" showIcon style={{ marginBottom: 16 }}
            message="BotFather → Payments → Click/Payme"
            description={<>
              <div>1. Telegram'da <Text code>@BotFather</Text> ni oching → <Text code>/mybots</Text> → bot tanlang</div>
              <div>2. <Text code>Payments</Text> tugmasini bosing → Click yoki Payme provayderini tanlang</div>
              <div>3. Token formati: <Text code>123:TEST:abc...</Text> (sandbox) yoki <Text code>123:LIVE:xyz...</Text> (real)</div>
              <div>4. Bu tokenni quyiga kiriting — Telegram orqali to'lovlar shu token bilan ishlaydi</div>
            </>} />
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item name="telegram_provider_token_click"
                label="Click TEST/LIVE token"
                tooltip="BotFather → Payments → Click">
                <Input.Password autoComplete="off" placeholder="123:TEST:abc..." />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="telegram_provider_token_payme"
                label="Payme TEST/LIVE token"
                tooltip="BotFather → Payments → Payme">
                <Input.Password autoComplete="off" placeholder="456:TEST:xyz..." />
              </Form.Item>
            </Col>
          </Row>
        </Card>

        {/* Webhook URLs */}
        <Card title={<><GlobalOutlined /> Webhook URL'lar (Click/Payme panellariga kiritish uchun)</>} size="small" style={{ marginBottom: 16 }}>
          <Alert type="info" showIcon style={{ marginBottom: 16 }}
            message="Bu URL'larni Click/Payme merchant kabineti'ga kiriting"
            description="Click yoki Payme to'lov o'tkazganda biz tomonga callback (webhook) yuboradi. URL'larni nusxalab merchant panel'iga joylashtiring." />
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item label="Click webhook URL">
                <Input.Group compact>
                  <Input value={clickWebhookUrl} readOnly style={{ width: 'calc(100% - 80px)' }} />
                  <Button onClick={() => copyToClipboard(clickWebhookUrl, 'Click webhook')}>Nusxa</Button>
                </Input.Group>
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item label="Payme webhook URL">
                <Input.Group compact>
                  <Input value={paymeWebhookUrl} readOnly style={{ width: 'calc(100% - 80px)' }} />
                  <Button onClick={() => copyToClipboard(paymeWebhookUrl, 'Payme webhook')}>Nusxa</Button>
                </Input.Group>
              </Form.Item>
            </Col>
          </Row>
        </Card>

        {/* Click */}
        <Card title={<><CreditCardOutlined /> Click Merchant</>} size="small" style={{ marginBottom: 16 }}>
          <Alert type="info" showIcon style={{ marginBottom: 16 }}
            message="Click.uz ulash"
            description="merchant.click.uz da ro'yxatdan o'ting. Merchant ID, Service ID va Secret Key beriladi. Komissiya: UzCard/Humo 0.8%, Visa 2.5%" />
          <Form.Item name="click_enabled" label="Click ulash" valuePropName="checked">
            <Switch checkedChildren="Yoqiq" unCheckedChildren="O'chiq" />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(p, c) => p.click_enabled !== c.click_enabled}>
            {({ getFieldValue }) => getFieldValue('click_enabled') && (
              <Row gutter={16}>
                <Col xs={24} md={8}>
                  <Form.Item name="click_merchant_id" label="Merchant ID"><Input placeholder="12345" /></Form.Item>
                </Col>
                <Col xs={24} md={8}>
                  <Form.Item name="click_service_id" label="Service ID"><Input placeholder="54321" /></Form.Item>
                </Col>
                <Col xs={24} md={8}>
                  <Form.Item name="click_secret_key" label="Secret Key"><Input.Password autoComplete="off" /></Form.Item>
                </Col>
              </Row>
            )}
          </Form.Item>
        </Card>

        {/* Payme */}
        <Card title={<><CreditCardOutlined /> Payme Merchant</>} size="small" style={{ marginBottom: 16 }}>
          <Alert type="info" showIcon style={{ marginBottom: 16 }}
            message="Payme.uz ulash"
            description="business.paycom.uz da ariza yuboring. Cashbox ID va Merchant Key beriladi. Komissiya: UzCard/Humo 0.8-1.2%" />
          <Form.Item name="payme_enabled" label="Payme ulash" valuePropName="checked">
            <Switch checkedChildren="Yoqiq" unCheckedChildren="O'chiq" />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(p, c) => p.payme_enabled !== c.payme_enabled}>
            {({ getFieldValue }) => getFieldValue('payme_enabled') && (
              <Row gutter={16}>
                <Col xs={24} md={12}>
                  <Form.Item name="payme_merchant_id" label="Cashbox ID (Merchant ID)"><Input placeholder="5e7c1e..." /></Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item name="payme_secret_key" label="Merchant Key"><Input.Password autoComplete="off" /></Form.Item>
                </Col>
              </Row>
            )}
          </Form.Item>
        </Card>

        {/* Catering karta */}
        <Card title={<><CreditCardOutlined /> Catering to'lov kartasi (manual)</>} size="small" style={{ marginBottom: 16 }}>
          <Alert type="warning" showIcon style={{ marginBottom: 16 }}
            message="Click/Payme ulanmaguncha" description="Catering 'Hozir to'lov' tanlanganda mijozga shu karta ko'rsatiladi." />
          <Row gutter={16}>
            <Col xs={24} md={14}>
              <Form.Item name="catering_payment_card" label="Karta raqami">
                <Input placeholder="8600 1234 5678 9012" maxLength={19} />
              </Form.Item>
            </Col>
            <Col xs={24} md={10}>
              <Form.Item name="catering_payment_owner" label="Karta egasi"><Input placeholder="TURSUNBOYEV B." /></Form.Item>
            </Col>
          </Row>
        </Card>

        {/* Faza 4-5: To'lov mantiqi sozlamalari */}
        <Card title={<><DollarOutlined /> To'lov mantiqi (Catering xizmat haqi va Prepayment)</>} size="small">
          <Alert type="info" showIcon style={{ marginBottom: 16 }}
            message="Avtomatik to'lov hisob-kitobi"
            description="Bu sozlamalar Telegram Native Payments paytida hisoblanadi. Click/Payme ulangan bo'lishi shart." />
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item name="catering_service_fee" label="Catering 'Borib xizmat ko'rsatish' haqi (so'm)"
                extra="Mijoz onsite catering tanlasa, asosiy chekka qo'shiladi">
                <InputNumber style={{ width: '100%' }} min={0} step={10000}
                  formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                  parser={(v) => v.replace(/,/g, '')}
                  placeholder="50000" />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="prepayment_required_above" label="Oldindan to'lov chegarasi (so'm)"
                extra="Buyurtma summasi shu chegaradan oshsa, mijozdan oldindan to'lov majburiy. 0 = yo'q">
                <InputNumber style={{ width: '100%' }} min={0} step={50000}
                  formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                  parser={(v) => v.replace(/,/g, '')}
                  placeholder="200000" />
              </Form.Item>
            </Col>
          </Row>
          <Alert type="warning" showIcon style={{ marginBottom: 16 }}
            message="Eslatma — oldindan to'lov foizi tarif darajasida"
            description="Pro tarif → 30%, Basic → 30% (Tariflar bo'limida o'zgartirish mumkin)." />

          <Alert type="success" showIcon style={{ marginBottom: 16 }}
            message="🚗 Yetkazib berish bo'yicha majburiy oldindan to'lov"
            description="Yoqilsa: dastavka, catering 'borib yopish' va catering dastavka uchun summa chegarasidan qat'i nazar oldindan to'lov majburiy. Saboy/pickup esa hech qachon prepayment talab qilmaydi." />
          <Form.Item name="enforce_prepayment_for_delivery" label="Yetkazib berishlarga prepayment majburiy" valuePropName="checked">
            <Switch checkedChildren="HA" unCheckedChildren="YO'Q" />
          </Form.Item>
        </Card>

        {/* Catering Notifier */}
        <Card title={<><GiftOutlined /> Catering bildirishnoma kanali</>} size="small" style={{ marginBottom: 16 }}>
          <Alert type="info" showIcon style={{ marginBottom: 16 }}
            message="Har kuni 20:00 da ertangi catering ro'yxati"
            description={<>
              <div>Bu yerga Telegram <b>kanal</b> yoki <b>guruh</b> chat ID kiriting.</div>
              <div style={{ marginTop: 6 }}>Har kuni soat 20:00 (Toshkent vaqti) da ertangi sanaga belgilangan barcha catering buyurtmalar (vaqti, mijozi, manzili) shu yerga yuboriladi.</div>
              <div style={{ marginTop: 6 }}>Chat ID olish: kanalga <Text code>@CateringNotifierBot</Text> botni admin qilib qo'shing → kanalga biron xabar yuboring → <Text code>https://api.telegram.org/bot&lt;TOKEN&gt;/getUpdates</Text> orqali chat ID ni oling.</div>
            </>} />
          <Row gutter={16}>
            <Col xs={24} md={16}>
              <Form.Item name="catering_notifier_chat_id" label="Chat ID (kanal/guruh)"
                extra="Misol: -1001234567890 yoki @my_channel">
                <Input placeholder="@my_channel yoki -1001234567890" />
              </Form.Item>
            </Col>
            <Col xs={24} md={8} style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: 24 }}>
              <Button onClick={async () => {
                try {
                  const r = await fetch('/api/admin/catering-notifier/test', {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${useAuthStore.getState().token}` },
                  })
                  const d = await r.json()
                  if (r.ok) message.success(`Yuborildi: ${d.orders_count} ta buyurtma`)
                  else message.error(d.detail || 'Xato')
                } catch (e) { message.error('Yuborib bo\'lmadi') }
              }}>🚀 Hozir sinab ko'rish</Button>
            </Col>
          </Row>
        </Card>
      </>)}
      {selectedBranchId && <Alert type="info" message="To'lov sozlamalari faqat asosiy restoran darajasida. Filial rejimidan chiqing." />}
    </>
  )

  const cateringTab = (
    <>
      {!selectedBranchId && (<>
        <Card title={<><DollarOutlined /> Valyuta kursi (USD → UZS)</>} size="small" style={{ marginBottom: 16 }}>
          <Form.Item name="currency_auto" label="Avtomatik kurs (CBU)" valuePropName="checked"
            extra="Yoqilgan bo'lsa Markaziy Bank kursi har soatda yangilanadi">
            <Switch checkedChildren="Auto (CBU)" unCheckedChildren="Qo'lda" />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(p, c) => p.currency_auto !== c.currency_auto}>
            {({ getFieldValue }) => !getFieldValue('currency_auto') && (
              <Form.Item name="currency_rate_manual" label="Qo'lda kurs (1 USD = ? so'm)"
                rules={[{ required: true, message: 'Kurs kiriting' }]}>
                <InputNumber min={0} style={{ maxWidth: 300 }} step={100}
                  formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                  parser={(v) => v.replace(/,/g, '')} placeholder="12500" />
              </Form.Item>
            )}
          </Form.Item>
        </Card>

        <Card title={<><GiftOutlined /> Catering miqdor sozlamalari</>} size="small">
          <Row gutter={16}>
            <Col xs={12} md={6}>
              <Form.Item name="catering_somsa_min" label="🥟 Somsa min"><InputNumber min={1} style={{ width: '100%' }} /></Form.Item>
            </Col>
            <Col xs={12} md={6}>
              <Form.Item name="catering_somsa_step" label="🥟 Somsa qadam"><InputNumber min={1} style={{ width: '100%' }} /></Form.Item>
            </Col>
            <Col xs={12} md={6}>
              <Form.Item name="catering_nan_min" label="🍞 Non min"><InputNumber min={1} style={{ width: '100%' }} /></Form.Item>
            </Col>
            <Col xs={12} md={6}>
              <Form.Item name="catering_nan_step" label="🍞 Non qadam"><InputNumber min={1} style={{ width: '100%' }} /></Form.Item>
            </Col>
          </Row>
          <Form.Item name="catering_delivery_per_km_uzs" label="🚗 Dastavka 1 km narxi (so'm)"
            extra="Yandex ulanmaganda ishlatiladi" style={{ maxWidth: 400 }}>
            <InputNumber min={0} style={{ width: '100%' }} step={1000}
              formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
              parser={(v) => v.replace(/,/g, '')} />
          </Form.Item>
        </Card>
      </>)}
      {selectedBranchId && <Alert type="info" message="Catering sozlamalari faqat asosiy restoran darajasida." />}
    </>
  )

  const aiAgentTab = (
    <>
      {selectedBranchId ? (
        <Alert type="info" message="AI Operator faqat asosiy restoran darajasida sozlanadi." />
      ) : !aiAllowed ? (
        <Alert
          type="warning"
          showIcon
          message="🔒 AI Operator faqat Pro tarifida"
          description="Tariflar bo'limidan Pro tarifga o'ting — telefon orqali avtomatik buyurtma qabul qilish uchun."
          style={{ marginBottom: 16 }}
        />
      ) : (
        <Card title={<><RobotOutlined /> AI Call Operator</>} size="small">
          <Alert type="info" showIcon style={{ marginBottom: 16 }}
            message="Telefon orqali AI operator"
            description="Mijoz qo'ng'iroq qilganda AI uning gapini eshitib, menyudan mahsulot tanlab, buyurtma qabul qiladi. Catering (≥100 somsa) buyurtmalari catering kanaliga yo'naltiriladi."
          />
          <Form.Item name="ai_agent_enabled" label="AI Operator yoqish" valuePropName="checked"
            extra="Yoqilgan bo'lsa kelayotgan qo'ng'iroqlar AI tomonidan qabul qilinadi.">
            <Switch checkedChildren="Yoqiq" unCheckedChildren="O'chiq" />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(p, c) => p.ai_agent_enabled !== c.ai_agent_enabled}>
            {({ getFieldValue }) => getFieldValue('ai_agent_enabled') && (
              <>
                <Form.Item name="ai_agent_prompt" label="AI ko'rsatmasi (system prompt)"
                  extra="AI mijoz bilan qanday ohangda gaplashishi kerak. Bo'sh qoldirilsa standart shablon ishlatiladi.">
                  <Input.TextArea
                    rows={4}
                    placeholder='Masalan: "Salom, men Muhsina Dollar Somsa restoranining AI operatori. Sizga qanday yordam bera olaman?"'
                  />
                </Form.Item>
                <Row gutter={16}>
                  <Col xs={24} md={8}>
                    <Form.Item name="ai_agent_voice" label="Ovoz"
                      extra="Provayderda mavjud bo'lgan ovoz">
                      <Select options={[
                        { value: 'female', label: '👩 Ayol ovozi' },
                        { value: 'male',   label: '👨 Erkak ovozi' },
                      ]} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={8}>
                    <Form.Item name="ai_agent_provider" label="Provayder">
                      <Select options={[
                        { value: 'openai', label: 'OpenAI (gpt-4o-mini)' },
                        { value: 'vapi',   label: 'Vapi.ai (premium)' },
                        { value: 'retell', label: 'Retell AI' },
                      ]} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={8}>
                    <Form.Item name="ai_agent_model" label="Model" extra="OpenAI uchun model nomi">
                      <Input placeholder="gpt-4o-mini" />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item name="ai_agent_api_key" label="API kalit"
                  extra="OpenAI/Vapi/Retell kalit. Bo'sh qoldirilsa server .env'dagi OPENAI_API_KEY ishlatiladi (test rejim uchun)">
                  <Input.Password placeholder="sk-..." autoComplete="off" />
                </Form.Item>
                <Alert type="info" showIcon
                  message="Webhook URL"
                  description={<code>POST {window.location.origin.replace('5173','8000')}/ai/process-call</code>}
                />
              </>
            )}
          </Form.Item>
        </Card>
      )}
    </>
  )

  const localeTab = (
    <Card title={<><GlobalOutlined /> Bot tili</>} size="small">
      <Form.Item name="language" style={{ maxWidth: 250, marginBottom: 0 }}>
        <Select options={[
          { value: 'uz', label: "🇺🇿 O'zbek tili" },
          { value: 'ru', label: '🇷🇺 Rus tili' },
        ]} />
      </Form.Item>
    </Card>
  )

  const checkBots = async () => {
    setBotChecking(true)
    try {
      const r = await fetch('/api/admin/bots/check?restaurant_id=' + restaurantId, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${useAuthStore.getState().token}` },
      })
      const d = await r.json()
      setBotStatus(d)
    } catch (e) {
      message.error('Tekshirib bo\'lmadi')
    } finally {
      setBotChecking(false)
    }
  }

  const renderBotStatus = (key, label) => {
    const s = botStatus?.[key]
    if (!s) return null
    if (!s.configured) return <Alert type="warning" message={`${label}: token kiritilmagan`} showIcon style={{ marginTop: 8 }} />
    if (s.online) return <Alert type="success" showIcon style={{ marginTop: 8 }}
      message={`${label}: ✅ Online — @${s.username || '?'} (${s.first_name || '?'})`} />
    return <Alert type="error" showIcon style={{ marginTop: 8 }}
      message={`${label}: ❌ Offline — ${s.error || 'Telegram javob bermadi'}`} />
  }

  const botsTab = (
    <>
      <Card title={<><RobotOutlined /> Telegram botlar</>} size="small">
        <Alert type="info" showIcon style={{ marginBottom: 16 }}
          message="BotFather'dan token olish"
          description={<>
            <div>1. Telegram'da <Text code>@BotFather</Text> ni oching → <Text code>/newbot</Text></div>
            <div>2. Bot nomi va username'ni bering</div>
            <div>3. Olingan tokenni quyiga kiriting (<Text code>1234567:ABC...</Text> formatda)</div>
            <div>4. Saqlagandan so'ng <b>"Tekshirish"</b> tugmasini bosing</div>
            <div style={{ marginTop: 6 }}>⚠️ Token o'zgartirilgandan so'ng super-admin'dan <b>"Bots service restart"</b> so'rang</div>
          </>} />
        <Form.Item name="bot_token" label="Customer (Mijoz) bot tokeni"
          extra="Mijozlar mahsulot va catering buyurtma berish uchun ishlatadi">
          <Input.Password placeholder="1234567:ABC..." autoComplete="off" />
        </Form.Item>
        <Form.Item name="courier_bot_token" label="Courier (Kuryer) bot tokeni"
          extra="Kuryerlar buyurtmalarni qabul qilish va status yangilash uchun">
          <Input.Password placeholder="1234567:DEF..." autoComplete="off" />
        </Form.Item>
        <Space>
          <Button onClick={checkBots} loading={botChecking} icon={<RobotOutlined />}>
            🔍 Telegram'da tekshirish
          </Button>
        </Space>
        {botStatus && (
          <div style={{ marginTop: 12 }}>
            {renderBotStatus('customer_bot', 'Customer bot')}
            {renderBotStatus('courier_bot', 'Courier bot')}
          </div>
        )}
      </Card>
    </>
  )

  const tabItems = [
    { key: 'restaurant', label: <><ShopOutlined /> Restoran</>, children: restaurantTab },
    { key: 'hours', label: <><ClockCircleOutlined /> Ish vaqti</>, children: workHoursTab },
    { key: 'delivery', label: <><CarOutlined /> Dastavka</>, children: deliveryTab },
    { key: 'payment', label: <><CreditCardOutlined /> To'lov</>, children: paymentTab },
    { key: 'catering', label: <><GiftOutlined /> Catering</>, children: cateringTab },
    { key: 'ai', label: <><RobotOutlined /> AI Operator</>, children: aiAgentTab },
    { key: 'pos', label: <><PrinterOutlined /> Terminal/Printer</>, children: <POSSettings restaurantId={restaurantId} /> },
    { key: 'bots', label: <><RobotOutlined /> Botlar</>, children: botsTab },
    { key: 'locale', label: <><GlobalOutlined /> Til</>, children: localeTab },
  ]

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto' }}>
      <Title level={4} style={{ marginBottom: 24 }}>⚙️ Sozlamalar</Title>

      <Form form={form} layout="vertical" requiredMark="optional">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          type="card"
          items={tabItems}
          style={{ marginBottom: 16 }}
        />
        <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSave}
          size="large" block
          style={{ background: '#fa8c16', borderColor: '#fa8c16', height: 48, fontSize: 16, fontWeight: 600, marginBottom: 32 }}>
          Sozlamalarni saqlash
        </Button>
      </Form>

      {/* Profil */}
      <Title level={4} style={{ marginBottom: 16 }}>👤 Profil</Title>
      <Form form={profileForm} layout="vertical" requiredMark="optional">
        <Card title={<><UserOutlined /> Admin profili</>} size="small" style={{ marginBottom: 16 }}>
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item name="username" label="Username (login)" rules={[{ required: true }]}>
                <Input prefix={<UserOutlined />} placeholder="admin" />
              </Form.Item>
            </Col>
          </Row>
          <Alert type="warning" showIcon style={{ marginBottom: 12 }}
            message="Parolni o'zgartirish uchun ESKI parolni kiritish majburiy" />
          <Row gutter={16}>
            <Col xs={24}>
              <Form.Item name="current_password" label="Eski parol"
                extra="Faqat parolni o'zgartirsangiz kerak">
                <Input.Password prefix={<LockOutlined />} placeholder="Eski parol" autoComplete="current-password" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item name="new_password" label="Yangi parol" extra="Bo'sh qoldirsangiz parol o'zgarmaydi">
                <Input.Password prefix={<LockOutlined />} autoComplete="new-password" />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="confirm_password" label="Yangi parolni tasdiqlang" dependencies={['new_password']}
                rules={[({ getFieldValue }) => ({
                  validator(_, v) {
                    if (!v && !getFieldValue('new_password')) return Promise.resolve()
                    if (v === getFieldValue('new_password')) return Promise.resolve()
                    return Promise.reject('Parollar mos emas!')
                  },
                })]}>
                <Input.Password prefix={<LockOutlined />} autoComplete="new-password" />
              </Form.Item>
            </Col>
          </Row>
        </Card>
        <Button type="primary" icon={<SaveOutlined />} loading={savingProfile} onClick={handleProfileSave}
          size="large" block style={{ height: 48, fontSize: 16, fontWeight: 600 }}>
          Profilni saqlash
        </Button>
      </Form>
    </div>
  )
}
