import { useEffect, useState, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Form, Input, InputNumber, Button, Typography, Row, Col,
  message, Spin, TimePicker, Space, Divider
} from 'antd'
import {
  ArrowLeftOutlined, SaveOutlined, ShopOutlined,
  PhoneOutlined, EnvironmentOutlined, ClockCircleOutlined,
} from '@ant-design/icons'
import { getSettings, updateSettings, getBranchSettings, updateBranchSettings } from '../../api'
import { useAuthStore } from '../../store/auth'
import { useBranchStore } from '../../store/branch'
import { moneyFormatter, moneyParser } from '../../utils/format'
import dayjs from 'dayjs'

const { Title, Text } = Typography

const cardStyle = { marginBottom: 12, borderRadius: 14, border: '1px solid #ececec', boxShadow: 'none' }
const cardBody = { padding: 24 }
const sectionLabel = { fontSize: 12, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: 18, display: 'block' }

// Yandex Map Component
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
    <div
      ref={mapRef}
      style={{
        width: '100%',
        height: 300,
        borderRadius: 12,
        overflow: 'hidden',
        border: '1px solid #e8e8e8',
      }}
    />
  )
}

export default function RestaurantSettings() {
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [mapLat, setMapLat] = useState(41.2995)
  const [mapLon, setMapLon] = useState(69.2401)

  const { currentRestaurantId: restaurantId } = useAuthStore()
  const selectedBranchId = useBranchStore((s) => s.selectedBranchId)
  const restParams = restaurantId ? { restaurant_id: restaurantId } : {}

  useEffect(() => {
    if (!restaurantId && !selectedBranchId) {
      setLoading(false)
      return
    }

    setLoading(true)
    const settingsPromise = selectedBranchId
      ? getBranchSettings(selectedBranchId)
      : getSettings(restParams)

    settingsPromise
      .then((res) => {
        const d = { ...(res.data || {}) }
        if (selectedBranchId) {
          d.restaurant_name = d.name || ''
          d.restaurant_lat = d.latitude
          d.restaurant_lon = d.longitude
        }
        if (d.work_hours_from) d.work_hours_from = dayjs(d.work_hours_from, 'HH:mm')
        if (d.work_hours_until) d.work_hours_until = dayjs(d.work_hours_until, 'HH:mm')
        form.setFieldsValue(d)
        if (d.restaurant_lat) setMapLat(d.restaurant_lat)
        if (d.restaurant_lon) setMapLon(d.restaurant_lon)
      })
      .catch(() => message.error("Ma'lumotlarni yuklashda xato"))
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
        const b = {
          ...values,
          name: values.restaurant_name,
          latitude: values.restaurant_lat,
          longitude: values.restaurant_lon,
        }
        delete b.restaurant_name
        delete b.restaurant_lat
        delete b.restaurant_lon
        await updateBranchSettings(selectedBranchId, b)
      } else {
        await updateSettings(values, restParams)
      }
      message.success('Sozlamalar saqlandi')
    } catch (err) {
      if (!err?.errorFields) message.error('Saqlashda xato')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <Spin size="large" />
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <Button
          type="text"
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/settings')}
          style={{ marginBottom: 8, padding: 0, color: '#6b7280' }}
        >
          Sozlamalar
        </Button>
        <Title level={3} style={{ marginBottom: 4, marginTop: 0, fontWeight: 600 }}>
          Restoran ma'lumotlari
        </Title>
        <Text type="secondary" style={{ fontSize: 14 }}>
          Nomi, manzili, joylashuvi va ish vaqti
        </Text>
      </div>

      <Form form={form} layout="vertical" requiredMark="optional">
        {/* Basic Info */}
        <Card style={cardStyle} styles={{ body: cardBody }}>
          <span style={sectionLabel}>Asosiy</span>

          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item
                name="restaurant_name"
                label="Restoran nomi"
                rules={[{ required: true, message: 'Nom kiriting' }]}
              >
                <Input
                  prefix={<ShopOutlined style={{ color: '#bfbfbf' }} />}
                  placeholder="Muhsina Dollar Somsa"
                  size="large"
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item
                name="phone"
                label="Telefon raqam"
                rules={[
                  { required: true, message: 'Telefon kiriting' },
                  { pattern: /^\+998\d{9}$/, message: '+998XXXXXXXXX formatida' }
                ]}
              >
                <Input
                  prefix={<PhoneOutlined style={{ color: '#bfbfbf' }} />}
                  placeholder="+998901234567"
                  maxLength={13}
                  size="large"
                />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item
            name="address"
            label="Manzil"
            rules={[{ required: true, message: 'Manzil kiriting' }]}
          >
            <Input
              prefix={<EnvironmentOutlined style={{ color: '#bfbfbf' }} />}
              placeholder="Toshkent sh., Chilonzor tumani, 7-mavze"
              size="large"
            />
          </Form.Item>
        </Card>

        {/* Map */}
        <Card style={cardStyle} styles={{ body: cardBody }}>
          <span style={sectionLabel}>Joylashuv</span>
          <Text type="secondary" style={{ display: 'block', marginBottom: 16, marginTop: -8, fontSize: 13 }}>
            Markerni surib aniq joyni belgilang
          </Text>

          <YandexMap lat={mapLat} lon={mapLon} onChange={handleMapChange} />

          <Row gutter={16} style={{ marginTop: 16 }}>
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
        </Card>

        {/* Work Hours */}
        <Card style={{ ...cardStyle, marginBottom: 24 }} styles={{ body: cardBody }}>
          <span style={sectionLabel}>Ish vaqti va minimal buyurtma</span>

          <Row gutter={16} align="middle">
            <Col xs={24} sm={8}>
              <Form.Item
                name="work_hours_from"
                label="Ochilish"
                rules={[{ required: true, message: 'Vaqt tanlang' }]}
              >
                <TimePicker
                  format="HH:mm"
                  minuteStep={15}
                  style={{ width: '100%' }}
                  size="large"
                  needConfirm={false}
                  placeholder="08:00"
                />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item
                name="work_hours_until"
                label="Yopilish"
                rules={[{ required: true, message: 'Vaqt tanlang' }]}
              >
                <TimePicker
                  format="HH:mm"
                  minuteStep={15}
                  style={{ width: '100%' }}
                  size="large"
                  needConfirm={false}
                  placeholder="22:00"
                />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item
                name="min_order"
                label="Minimal buyurtma"
                rules={[{ required: true, message: "Summa kiriting" }]}
              >
                <InputNumber
                  style={{ width: '100%' }}
                  min={0}
                  max={1000000}
                  step={5000}
                  size="large"
                  formatter={moneyFormatter}
                  parser={moneyParser}
                  addonAfter="so'm"
                  placeholder="15 000"
                />
              </Form.Item>
            </Col>
          </Row>
        </Card>

        {/* Save Button */}
        <Button
          type="primary"
          icon={<SaveOutlined />}
          loading={saving}
          onClick={handleSave}
          size="large"
          block
          style={{ height: 46, fontWeight: 500, borderRadius: 10, background: '#111827', borderColor: '#111827' }}
        >
          Saqlash
        </Button>
      </Form>
    </div>
  )
}
