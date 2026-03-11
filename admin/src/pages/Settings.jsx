import { useEffect, useState, useRef, useCallback } from 'react'
import {
  Card, Form, Input, InputNumber, Select, Button, Typography,
  Row, Col, message, Spin, TimePicker, Tooltip, Space
} from 'antd'
import {
  SaveOutlined, EnvironmentOutlined, PhoneOutlined,
  ShopOutlined, ClockCircleOutlined, CarOutlined,
  UserOutlined, LockOutlined
} from '@ant-design/icons'
import { getSettings, updateSettings, getProfile, updateProfile, getBranchSettings, updateBranchSettings } from '../api'
import { useAuthStore } from '../store/auth'
import { useBranchStore } from '../store/branch'
import dayjs from 'dayjs'

const { Title, Text } = Typography

// ── Yandex Map Component ────────────────────────────────
function YandexMap({ lat, lon, onChange }) {
  const mapRef = useRef(null)
  const mapInstance = useRef(null)
  const markerRef = useRef(null)
  const [mapReady, setMapReady] = useState(false)

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
      setMapReady(true)
    })
  }, [lat, lon, onChange])

  useEffect(() => {
    if (window.ymaps) {
      initMap()
      return
    }
    const script = document.createElement('script')
    script.src = 'https://api-maps.yandex.ru/2.1/?apikey=&lang=ru_RU'
    script.onload = initMap
    document.head.appendChild(script)
  }, [initMap])

  // Tashqaridan lat/lon o'zgarganda markerni yangilash
  useEffect(() => {
    if (markerRef.current && lat && lon) {
      markerRef.current.geometry.setCoordinates([lat, lon])
      mapInstance.current?.setCenter([lat, lon])
    }
  }, [lat, lon])

  return (
    <div
      ref={mapRef}
      style={{
        width: '100%',
        height: 320,
        borderRadius: 8,
        overflow: 'hidden',
        border: '1px solid #d9d9d9',
      }}
    />
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
  const { setAuth, token } = useAuthStore()
  const selectedBranchId = useBranchStore((s) => s.selectedBranchId)

  useEffect(() => {
    setLoading(true)
    const settingsPromise = selectedBranchId
      ? getBranchSettings(selectedBranchId)
      : getSettings()

    Promise.all([settingsPromise, getProfile()])
      .then(([settingsRes, profileRes]) => {
        const d = settingsRes.data || {}
        if (d.work_hours_from) d.work_hours_from = dayjs(d.work_hours_from, 'HH:mm')
        if (d.work_hours_until) d.work_hours_until = dayjs(d.work_hours_until, 'HH:mm')
        form.setFieldsValue(d)
        if (selectedBranchId) {
          if (d.latitude) setMapLat(d.latitude)
          if (d.longitude) setMapLon(d.longitude)
        } else {
          if (d.restaurant_lat) setMapLat(d.restaurant_lat)
          if (d.restaurant_lon) setMapLon(d.restaurant_lon)
        }

        const p = profileRes.data || {}
        profileForm.setFieldsValue({ username: p.username, name: p.name })
      })
      .catch(() => message.error('Sozlamalarni yuklashda xato'))
      .finally(() => setLoading(false))
  }, [selectedBranchId])

  const handleMapChange = useCallback((lat, lon) => {
    const roundedLat = Math.round(lat * 10000) / 10000
    const roundedLon = Math.round(lon * 10000) / 10000
    setMapLat(roundedLat)
    setMapLon(roundedLon)
    form.setFieldsValue({ restaurant_lat: roundedLat, restaurant_lon: roundedLon })
  }, [form])

  const handleSave = async () => {
    setSaving(true)
    try {
      const values = await form.validateFields()
      // TimePicker dayjs → string
      if (values.work_hours_from) values.work_hours_from = values.work_hours_from.format('HH:mm')
      if (values.work_hours_until) values.work_hours_until = values.work_hours_until.format('HH:mm')
      if (selectedBranchId) {
        await updateBranchSettings(selectedBranchId, values)
      } else {
        await updateSettings(values)
      }
      message.success('✅ Sozlamalar muvaffaqiyatli saqlandi')
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

      await updateProfile(payload)
      profileForm.setFieldValue('new_password', '')
      profileForm.setFieldValue('confirm_password', '')

      if (values.username) {
        setAuth(token, { name: values.username })
      }
      message.success('✅ Profil muvaffaqiyatli yangilandi')
    } catch (err) {
      if (!err?.errorFields) message.error('Profilni saqlashda xato')
    } finally {
      setSavingProfile(false)
    }
  }

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 100 }} />

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <Title level={4} style={{ marginBottom: 24 }}>⚙️ Sozlamalar</Title>

      <Form form={form} layout="vertical" requiredMark="optional">

        {/* ── Restoran ma'lumotlari ── */}
        <Card
          title={<><ShopOutlined /> Restoran ma'lumotlari</>}
          style={{ marginBottom: 16 }}
          size="small"
        >
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item
                name="restaurant_name"
                label="Nomi"
                rules={[{ required: true, message: 'Nom kiriting' }]}
              >
                <Input prefix={<ShopOutlined />} placeholder="Muhsina Dollar Somsa" />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item
                name="phone"
                label="Telefon"
                rules={[
                  { required: true, message: 'Telefon kiriting' },
                  { pattern: /^\+998\d{9}$/, message: '+998XXXXXXXXX formatida' },
                ]}
              >
                <Input prefix={<PhoneOutlined />} placeholder="+998901234567" maxLength={13} />
              </Form.Item>
            </Col>
            <Col xs={24}>
              <Form.Item
                name="address"
                label="Manzil"
                rules={[{ required: true, message: 'Manzil kiriting' }]}
              >
                <Input prefix={<EnvironmentOutlined />} placeholder="Toshkent sh., Chilonzor tumani, 7-mavze" />
              </Form.Item>
            </Col>
          </Row>
        </Card>

        {/* ── Xarita ── */}
        <Card
          title={<><EnvironmentOutlined /> Restoran joylashuvi (xaritadan belgilang)</>}
          style={{ marginBottom: 16 }}
          size="small"
        >
          <YandexMap lat={mapLat} lon={mapLon} onChange={handleMapChange} />
          <Row gutter={16} style={{ marginTop: 12 }}>
            <Col xs={12}>
              <Form.Item name="restaurant_lat" label="Kenglik" style={{ marginBottom: 0 }}>
                <InputNumber
                  style={{ width: '100%' }}
                  step={0.0001}
                  precision={4}
                  onChange={(v) => v && setMapLat(v)}
                />
              </Form.Item>
            </Col>
            <Col xs={12}>
              <Form.Item name="restaurant_lon" label="Uzunlik" style={{ marginBottom: 0 }}>
                <InputNumber
                  style={{ width: '100%' }}
                  step={0.0001}
                  precision={4}
                  onChange={(v) => v && setMapLon(v)}
                />
              </Form.Item>
            </Col>
          </Row>
          <Text type="secondary" style={{ fontSize: 12, marginTop: 4, display: 'block' }}>
            Xaritani bosing yoki markerni suring — koordinatalar avtomatik yangilanadi
          </Text>
        </Card>

        {/* ── Ish vaqti ── */}
        <Card
          title={<><ClockCircleOutlined /> Ish vaqti</>}
          style={{ marginBottom: 16 }}
          size="small"
        >
          <Row gutter={16} align="middle">
            <Col>
              <Form.Item
                name="work_hours_from"
                label="Ochilish"
                rules={[{ required: true, message: 'Tanlang' }]}
                style={{ marginBottom: 0 }}
              >
                <TimePicker
                  format="HH:mm"
                  minuteStep={15}
                  placeholder="09:00"
                  style={{ width: 120 }}
                  needConfirm={false}
                />
              </Form.Item>
            </Col>
            <Col>
              <Text style={{ fontSize: 20, marginTop: 30, display: 'block' }}>—</Text>
            </Col>
            <Col>
              <Form.Item
                name="work_hours_until"
                label="Yopilish"
                rules={[{ required: true, message: 'Tanlang' }]}
                style={{ marginBottom: 0 }}
              >
                <TimePicker
                  format="HH:mm"
                  minuteStep={15}
                  placeholder="22:00"
                  style={{ width: 120 }}
                  needConfirm={false}
                />
              </Form.Item>
            </Col>
          </Row>
        </Card>

        {/* ── Yetkazib berish va buyurtma ── */}
        <Card
          title={<><CarOutlined /> Yetkazib berish</>}
          style={{ marginBottom: 16 }}
          size="small"
        >
          <Row gutter={16}>
            <Col xs={24} md={8}>
              <Form.Item
                name="min_order"
                label="Minimal buyurtma (so'm)"
                rules={[{ required: true, message: 'Summa kiriting' }]}
                extra="Faqat dastavka uchun"
              >
                <InputNumber
                  style={{ width: '100%' }}
                  min={0}
                  max={1000000}
                  step={5000}
                  formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                  parser={(v) => v.replace(/,/g, '')}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item
                name="delivery_base_fee"
                label="Bazaviy narx (so'm)"
                rules={[{ required: true, message: 'Kiriting' }]}
                extra="Har qanday masofaga"
              >
                <InputNumber
                  style={{ width: '100%' }}
                  min={0}
                  max={500000}
                  step={1000}
                  formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                  parser={(v) => v.replace(/,/g, '')}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item
                name="delivery_per_km"
                label="Har km uchun (so'm)"
                rules={[{ required: true, message: 'Kiriting' }]}
                extra="Masofaga qarab qo'shiladi"
              >
                <InputNumber
                  style={{ width: '100%' }}
                  min={0}
                  max={50000}
                  step={500}
                  formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                  parser={(v) => v.replace(/,/g, '')}
                />
              </Form.Item>
            </Col>
          </Row>
        </Card>

        {/* ── Til ── */}
        <Card title="🌐 Bot tili" style={{ marginBottom: 24 }} size="small">
          <Form.Item name="language" style={{ maxWidth: 250, marginBottom: 0 }}>
            <Select
              options={[
                { value: 'uz', label: "🇺🇿 O'zbek tili" },
                { value: 'ru', label: '🇷🇺 Rus tili' },
              ]}
            />
          </Form.Item>
        </Card>

        <Button
          type="primary"
          icon={<SaveOutlined />}
          loading={saving}
          onClick={handleSave}
          size="large"
          block
          style={{
            background: '#fa8c16',
            borderColor: '#fa8c16',
            height: 48,
            fontSize: 16,
            fontWeight: 600,
            marginBottom: 32,
          }}
        >
          Saqlash
        </Button>
      </Form>

      {/* ── Profil ── */}
      <Title level={4} style={{ marginBottom: 24 }}>👤 Profil sozlamalari</Title>
      <Form form={profileForm} layout="vertical" requiredMark="optional">
        <Card
          title={<><UserOutlined /> Admin profili</>}
          style={{ marginBottom: 16 }}
          size="small"
        >
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item
                name="username"
                label="Username (login)"
                rules={[{ required: true, message: 'Username kiriting' }]}
              >
                <Input prefix={<UserOutlined />} placeholder="admin" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item
                name="new_password"
                label="Yangi parol"
                extra="O'zgartirmoqchi bo'lsangiz kiriting"
              >
                <Input.Password prefix={<LockOutlined />} placeholder="Yangi parol" />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item
                name="confirm_password"
                label="Parolni tasdiqlang"
                dependencies={['new_password']}
                rules={[
                  ({ getFieldValue }) => ({
                    validator(_, value) {
                      if (!value && !getFieldValue('new_password')) return Promise.resolve()
                      if (value === getFieldValue('new_password')) return Promise.resolve()
                      return Promise.reject('Parollar mos emas!')
                    },
                  }),
                ]}
              >
                <Input.Password prefix={<LockOutlined />} placeholder="Parolni takrorlang" />
              </Form.Item>
            </Col>
          </Row>
        </Card>

        <Button
          type="primary"
          icon={<SaveOutlined />}
          loading={savingProfile}
          onClick={handleProfileSave}
          size="large"
          block
          style={{ height: 48, fontSize: 16, fontWeight: 600 }}
        >
          Profilni saqlash
        </Button>
      </Form>
    </div>
  )
}
