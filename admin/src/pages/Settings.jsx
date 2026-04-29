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
  const { setAuth, token, restaurantId } = useAuthStore()
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
      if (values.new_password) payload.new_password = values.new_password
      await updateProfile(payload, restParams)
      profileForm.setFieldValue('new_password', '')
      profileForm.setFieldValue('confirm_password', '')
      if (values.username) setAuth(token, { name: values.username }, restaurantId)
      message.success('✅ Profil yangilandi')
    } catch (err) {
      if (!err?.errorFields) message.error('Xato')
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

  const paymentTab = (
    <>
      {!selectedBranchId && (<>
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
        <Card title={<><CreditCardOutlined /> Catering to'lov kartasi (manual)</>} size="small">
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

  const tabItems = [
    { key: 'restaurant', label: <><ShopOutlined /> Restoran</>, children: restaurantTab },
    { key: 'hours', label: <><ClockCircleOutlined /> Ish vaqti</>, children: workHoursTab },
    { key: 'delivery', label: <><CarOutlined /> Dastavka</>, children: deliveryTab },
    { key: 'payment', label: <><CreditCardOutlined /> To'lov</>, children: paymentTab },
    { key: 'catering', label: <><GiftOutlined /> Catering</>, children: cateringTab },
    { key: 'ai', label: <><RobotOutlined /> AI Operator</>, children: aiAgentTab },
    { key: 'pos', label: <><PrinterOutlined /> Terminal/Printer</>, children: <POSSettings restaurantId={restaurantId} /> },
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
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item name="new_password" label="Yangi parol" extra="O'zgartirmoqchi bo'lsangiz kiriting">
                <Input.Password prefix={<LockOutlined />} />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="confirm_password" label="Parolni tasdiqlang" dependencies={['new_password']}
                rules={[({ getFieldValue }) => ({
                  validator(_, v) {
                    if (!v && !getFieldValue('new_password')) return Promise.resolve()
                    if (v === getFieldValue('new_password')) return Promise.resolve()
                    return Promise.reject('Parollar mos emas!')
                  },
                })]}>
                <Input.Password prefix={<LockOutlined />} />
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
