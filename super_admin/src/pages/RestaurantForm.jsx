import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Form, Input, InputNumber, Button, Card, Typography, Select,
  message, Divider, Row, Col, Spin, Modal, Table, Tag, Popconfirm, Switch, Space
} from 'antd'
import { ArrowLeftOutlined, EnvironmentOutlined, PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import { createRestaurant, updateRestaurant, getRestaurant, getPlans, getBranches, createBranch, updateBranch, deleteBranch } from '../api'

const { Title } = Typography

// Phone validation: +998XXXXXXXXX yoki 998XXXXXXXXX yoki 0XXXXXXXXX
const phoneRegex = /^(\+998|998|0)[0-9]{9}$/
const phoneValidator = (_, value) => {
  if (!value) return Promise.resolve()
  const clean = value.replace(/[\s\-\(\)]/g, '')
  if (!phoneRegex.test(clean)) {
    return Promise.reject('Format: +998901234567')
  }
  return Promise.resolve()
}

// Normalize phone → +998XXXXXXXXX
const normalizePhone = (val) => {
  if (!val) return val
  const clean = val.replace(/[\s\-\(\)]/g, '')
  if (clean.startsWith('0')) return '+998' + clean.slice(1)
  if (clean.startsWith('998') && !clean.startsWith('+')) return '+' + clean
  return clean
}

// Yandex Maps picker modal
function YandexMapPicker({ open, onClose, onSelect, lat, lon }) {
  const mapRef = useRef(null)
  const ymapRef = useRef(null)
  const placmarkRef = useRef(null)
  const [coords, setCoords] = useState([lat || 41.2995, lon || 69.2401])

  useEffect(() => {
    if (!open) return
    const initMap = () => {
      if (!window.ymaps || mapRef.current?._mapCreated) return
      window.ymaps.ready(() => {
        if (!mapRef.current) return
        const map = new window.ymaps.Map(mapRef.current, {
          center: [coords[0], coords[1]],
          zoom: 13,
          controls: ['zoomControl', 'searchControl'],
        })
        const placemark = new window.ymaps.Placemark(
          [coords[0], coords[1]],
          { hintContent: 'Restoran joylashuvi' },
          { preset: 'islands#redIcon', draggable: true }
        )
        placemark.events.add('dragend', (e) => {
          const c = e.get('target').geometry.getCoordinates()
          setCoords([c[0], c[1]])
        })
        map.events.add('click', (e) => {
          const c = e.get('coords')
          placemark.geometry.setCoordinates(c)
          setCoords([c[0], c[1]])
        })
        map.geoObjects.add(placemark)
        ymapRef.current = map
        placmarkRef.current = placemark
        mapRef.current._mapCreated = true
      })
    }

    if (window.ymaps) {
      initMap()
    } else {
      const script = document.createElement('script')
      script.src = 'https://api-maps.yandex.ru/2.1/?apikey=ваш-api-ключ&lang=ru_RU'
      script.async = true
      script.onload = initMap
      document.head.appendChild(script)
    }

    return () => {
      if (ymapRef.current) {
        ymapRef.current.destroy()
        ymapRef.current = null
        if (mapRef.current) mapRef.current._mapCreated = false
      }
    }
  }, [open])

  const handleSave = () => {
    onSelect(coords[0], coords[1])
    onClose()
  }

  return (
    <Modal
      open={open}
      onCancel={onClose}
      onOk={handleSave}
      okText="Saqlash"
      cancelText="Bekor"
      title="Restoran joylashuvini tanlang"
      width={680}
    >
      <div style={{ marginBottom: 8, color: '#666', fontSize: 13 }}>
        Xaritada bosing yoki markerini tortib joylashuvni belgilang
      </div>
      <div
        ref={mapRef}
        style={{ width: '100%', height: 380, background: '#eee', borderRadius: 8 }}
      />
      <div style={{ marginTop: 8, fontSize: 13, color: '#888' }}>
        Koordinatalar: {coords[0].toFixed(6)}, {coords[1].toFixed(6)}
      </div>
    </Modal>
  )
}

export default function RestaurantForm() {
  const { id } = useParams()
  const isEdit = !!id
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [fetching, setFetching] = useState(isEdit)
  const [mapOpen, setMapOpen] = useState(false)
  const [mapCoords, setMapCoords] = useState([41.2995, 69.2401])
  const [selectedPlan, setSelectedPlan] = useState('free')
  const [plans, setPlans] = useState([])

  // Branches state
  const [branches, setBranches] = useState([])
  const [branchLoading, setBranchLoading] = useState(false)
  const [branchModalOpen, setBranchModalOpen] = useState(false)
  const [editingBranch, setEditingBranch] = useState(null)
  const [branchForm] = Form.useForm()
  const [branchMapOpen, setBranchMapOpen] = useState(false)
  const [branchMapCoords, setBranchMapCoords] = useState([41.2995, 69.2401])

  useEffect(() => {
    getPlans().then((r) => setPlans(r.data || [])).catch(() => {})
  }, [])

  useEffect(() => {
    if (!isEdit) {
      // Yangi restoran: oldingi sessiyadan qolgan ma'lumotlarni tozalash
      form.resetFields()
      return
    }
    getRestaurant(id)
      .then((r) => {
        const d = r.data
        form.setFieldsValue({ ...d, admin_password: '' })
        if (d.restaurant_lat && d.restaurant_lon) {
          setMapCoords([d.restaurant_lat, d.restaurant_lon])
        }
        if (d.plan) setSelectedPlan(d.plan)
      })
      .catch(() => message.error('Yuklab bo\'lmadi'))
      .finally(() => setFetching(false))
  }, [id, isEdit])

  // Load branches when editing
  const loadBranches = async () => {
    if (!isEdit) return
    setBranchLoading(true)
    try {
      const r = await getBranches(id)
      setBranches(r.data || [])
    } catch { }
    setBranchLoading(false)
  }

  useEffect(() => { loadBranches() }, [id])

  const openBranchModal = (branch = null) => {
    setEditingBranch(branch)
    if (branch) {
      branchForm.setFieldsValue(branch)
      setBranchMapCoords([branch.latitude || 41.2995, branch.longitude || 69.2401])
    } else {
      branchForm.resetFields()
      setBranchMapCoords([41.2995, 69.2401])
    }
    setBranchModalOpen(true)
  }

  const handleBranchSave = async () => {
    try {
      const values = await branchForm.validateFields()
      if (editingBranch) {
        await updateBranch(editingBranch.id, values)
        message.success('Filial yangilandi')
      } else {
        await createBranch(id, values)
        message.success('Filial qo\'shildi')
      }
      setBranchModalOpen(false)
      loadBranches()
    } catch (e) {
      if (e.response) message.error(e.response?.data?.detail || 'Xato')
    }
  }

  const handleBranchDelete = async (branchId) => {
    try {
      await deleteBranch(branchId)
      message.success('Filial o\'chirildi')
      loadBranches()
    } catch {
      message.error('O\'chirib bo\'lmadi')
    }
  }

  const handleBranchMapSelect = (lat, lon) => {
    setBranchMapCoords([lat, lon])
    branchForm.setFieldsValue({ latitude: parseFloat(lat.toFixed(6)), longitude: parseFloat(lon.toFixed(6)) })
  }

  const handleMapSelect = (lat, lon) => {
    setMapCoords([lat, lon])
    form.setFieldsValue({ restaurant_lat: parseFloat(lat.toFixed(6)), restaurant_lon: parseFloat(lon.toFixed(6)) })
  }

  const onFinish = async (values) => {
    // Telefon normalize
    if (values.phone) values.phone = normalizePhone(values.phone)
    setLoading(true)
    try {
      if (isEdit) {
        if (!values.admin_password) delete values.admin_password
        await updateRestaurant(id, values)
        message.success('Yangilandi')
      } else {
        await createRestaurant(values)
        message.success('Restoran qo\'shildi')
      }
      navigate('/restaurants')
    } catch (e) {
      message.error(e.response?.data?.detail || 'Xato yuz berdi')
    } finally {
      setLoading(false)
    }
  }

  if (fetching) return <Spin size="large" style={{ display: 'block', margin: '80px auto' }} />

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/restaurants')} />
        <Title level={4} style={{ margin: 0 }}>
          {isEdit ? 'Restoranni tahrirlash' : 'Yangi restoran qo\'shish'}
        </Title>
      </div>

      <Card style={{ maxWidth: 780 }}>
        <Form
          form={form}
          layout="vertical"
          onFinish={onFinish}
          initialValues={{
            plan: 'free',
            work_hours_from: '09:00',
            work_hours_until: '22:00',
            min_order: 30000,
            delivery_base_fee: 10000,
            delivery_per_km: 3000,
            commission_percent: 0,
            restaurant_lat: 41.2995,
            restaurant_lon: 69.2401,
          }}
        >
          {/* ── Asosiy ma'lumotlar ── */}
          <Divider orientation="left">Asosiy ma'lumotlar</Divider>
          <Row gutter={16}>
            <Col xs={24} sm={12}>
              <Form.Item
                name="name"
                label="Restoran nomi"
                rules={[{ required: true, message: 'Nomini kiriting' }, { min: 2, max: 80 }]}
              >
                <Input placeholder="Muhsina Dollar Somsa" maxLength={80} showCount />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item
                name="phone"
                label="Telefon raqam"
                rules={[
                  { required: true, message: 'Telefon kiriting' },
                  { validator: phoneValidator },
                ]}
                tooltip="+998901234567 formatida"
              >
                <Input placeholder="+998901234567" maxLength={13} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item
                name="address"
                label="Manzil"
                rules={[{ max: 200, message: 'Maksimal 200 belgi' }]}
              >
                <Input placeholder="Toshkent sh., Chilonzor t., 1-uy" maxLength={200} />
              </Form.Item>
            </Col>
          </Row>

          {/* ── Joylashuv (xarita) ── */}
          <Divider orientation="left">Joylashuv</Divider>
          <Row gutter={16} align="bottom">
            <Col xs={12} sm={8}>
              <Form.Item
                name="restaurant_lat"
                label="Kenglik (Lat)"
                rules={[{ type: 'number', min: 37, max: 45, message: '37–45 oraliq' }]}
              >
                <InputNumber style={{ width: '100%' }} precision={6} step={0.001} />
              </Form.Item>
            </Col>
            <Col xs={12} sm={8}>
              <Form.Item
                name="restaurant_lon"
                label="Uzunlik (Lon)"
                rules={[{ type: 'number', min: 56, max: 74, message: '56–74 oraliq' }]}
              >
                <InputNumber style={{ width: '100%' }} precision={6} step={0.001} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item label=" ">
                <Button
                  icon={<EnvironmentOutlined />}
                  onClick={() => {
                    const lat = form.getFieldValue('restaurant_lat') || 41.2995
                    const lon = form.getFieldValue('restaurant_lon') || 69.2401
                    setMapCoords([lat, lon])
                    setMapOpen(true)
                  }}
                  block
                >
                  Xaritadan tanlash
                </Button>
              </Form.Item>
            </Col>
          </Row>

          {/* ── Bot tokenlar ── */}
          <Divider orientation="left">Bot tokenlar</Divider>
          <Row gutter={16}>
            <Col xs={24} sm={12}>
              <Form.Item
                name="bot_token"
                label="Asosiy bot token"
                tooltip="@BotFather dan olingan token"
                rules={[{
                  pattern: /^\d+:[A-Za-z0-9_\-]+$/,
                  message: '123456789:ABC... formatida bo\'lishi kerak',
                  warningOnly: true,
                }]}
              >
                <Input.Password placeholder="123456789:ABC-DEF..." />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item
                name="courier_bot_token"
                label="Kuryer bot token"
                tooltip="Kuryerlar uchun alohida bot"
                rules={[{
                  pattern: /^\d+:[A-Za-z0-9_\-]+$/,
                  message: '123456789:ABC... formatida bo\'lishi kerak',
                  warningOnly: true,
                }]}
              >
                <Input.Password placeholder="123456789:ABC-DEF..." />
              </Form.Item>
            </Col>
          </Row>

          {/* ── Admin kirish ── */}
          <Divider orientation="left">Admin kirish</Divider>
          <Row gutter={16}>
            <Col xs={24} sm={12}>
              <Form.Item
                name="admin_username"
                label="Admin login"
                rules={[
                  { required: !isEdit, message: 'Login kiriting' },
                  { min: 3, max: 30, message: '3–30 belgi' },
                  { pattern: /^[a-zA-Z0-9_]+$/, message: 'Faqat harf, raqam va _' },
                ]}
              >
                <Input placeholder="admin" maxLength={30} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item
                name="admin_password"
                label={isEdit ? 'Yangi parol (ixtiyoriy)' : 'Parol'}
                rules={[
                  { required: !isEdit, message: 'Parol kiriting' },
                  { min: 6, message: 'Kamida 6 belgi' },
                  { max: 50, message: 'Maksimal 50 belgi' },
                ]}
              >
                <Input.Password placeholder={isEdit ? 'O\'zgartirmasangiz bo\'sh qoldiring' : 'Kamida 6 belgi'} />
              </Form.Item>
            </Col>
          </Row>

          {/* ── Biznes sozlamalar ── */}
          <Divider orientation="left">Biznes sozlamalar</Divider>
          <Row gutter={16}>
            <Col xs={12} sm={6}>
              <Form.Item
                name="work_hours_from"
                label="Ochilish vaqti"
                rules={[{ pattern: /^\d{2}:\d{2}$/, message: 'HH:MM' }]}
              >
                <Input placeholder="09:00" maxLength={5} />
              </Form.Item>
            </Col>
            <Col xs={12} sm={6}>
              <Form.Item
                name="work_hours_until"
                label="Yopilish vaqti"
                rules={[{ pattern: /^\d{2}:\d{2}$/, message: 'HH:MM' }]}
              >
                <Input placeholder="22:00" maxLength={5} />
              </Form.Item>
            </Col>
            <Col xs={12} sm={6}>
              <Form.Item
                name="min_order"
                label="Min. buyurtma (so'm)"
                rules={[{ type: 'number', min: 0, message: 'Musbat son' }]}
              >
                <InputNumber style={{ width: '100%' }} min={0} step={1000} formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ' ')} />
              </Form.Item>
            </Col>
            <Col xs={12} sm={6}>
              <Form.Item
                name="delivery_base_fee"
                label="Bazaviy dastavka (so'm)"
                rules={[{ type: 'number', min: 0 }]}
              >
                <InputNumber style={{ width: '100%' }} min={0} step={500} formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ' ')} />
              </Form.Item>
            </Col>
            <Col xs={12} sm={6}>
              <Form.Item
                name="delivery_per_km"
                label="Har km narxi (so'm)"
                rules={[{ type: 'number', min: 0 }]}
              >
                <InputNumber style={{ width: '100%' }} min={0} step={500} formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ' ')} />
              </Form.Item>
            </Col>
          </Row>

          {/* ── Platforma ── */}
          <Divider orientation="left">Platforma</Divider>
          <Row gutter={16}>
            <Col xs={12} sm={8}>
              <Form.Item name="plan" label="Tarif rejasi">
                <Select
                  options={plans.map((p) => ({
                    value: p.slug,
                    label: `${p.name} — ${p.commission_percent}% komissiya${p.monthly_price > 0 ? ` (${Number(p.monthly_price).toLocaleString()} so'm/oy)` : ' (bepul)'}`,
                  }))}
                  onChange={(val) => {
                    setSelectedPlan(val)
                    const plan = plans.find((p) => p.slug === val)
                    if (plan) {
                      form.setFieldValue('commission_percent', plan.commission_percent)
                    }
                  }}
                />
              </Form.Item>
            </Col>
            {isEdit && (
              <Col xs={12} sm={4}>
                <Form.Item name="status" label="Status">
                  <Select options={[
                    { value: 'active', label: '✅ Faol' },
                    { value: 'blocked', label: '🚫 Bloklangan' },
                  ]} />
                </Form.Item>
              </Col>
            )}
            <Col xs={12} sm={4}>
              <Form.Item
                name="commission_percent"
                label="Komissiya (%)"
                tooltip="Tarifdan avtomatik to'ldiriladi — bu yerda faqat ko'rish mumkin"
              >
                <InputNumber
                  style={{ width: '100%' }}
                  min={0} max={100} step={0.5}
                  disabled
                  formatter={(v) => `${v}%`}
                  parser={(v) => parseFloat(v.replace('%', '')) || 0}
                />
              </Form.Item>
            </Col>
          </Row>

          {/* ── To'lov kartasi ── */}
          <Divider orientation="left">To'lov kartasi (restoran to'lov qilish uchun)</Divider>
          <Row gutter={16}>
            <Col xs={24} sm={8}>
              <Form.Item
                name="payment_card_number"
                label="Karta raqami"
                rules={[{
                  pattern: /^[\d\s]{16,19}$/,
                  message: '16 ta raqam kiriting',
                  warningOnly: true,
                }]}
              >
                <Input
                  placeholder="8600 1234 5678 9012"
                  maxLength={19}
                  onChange={(e) => {
                    const v = e.target.value.replace(/\D/g, '').slice(0, 16)
                    const fmt = v.match(/.{1,4}/g)?.join(' ') || v
                    form.setFieldValue('payment_card_number', fmt)
                  }}
                />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item
                name="payment_card_name"
                label="Karta egasi"
                rules={[{ max: 50 }]}
              >
                <Input placeholder="NAZIR XOLMATOV" maxLength={50} style={{ textTransform: 'uppercase' }} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item name="payment_card_bank" label="Bank">
                <Select
                  showSearch
                  placeholder="Bankni tanlang"
                  options={[
                    { value: 'Uzcard', label: 'Uzcard' },
                    { value: 'Humo', label: 'Humo' },
                    { value: 'Visa', label: 'Visa' },
                    { value: 'Mastercard', label: 'Mastercard' },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item style={{ marginTop: 16 }}>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              style={{ background: '#722ed1', borderColor: '#722ed1', marginRight: 8, minWidth: 120 }}
            >
              {isEdit ? 'Saqlash' : 'Qo\'shish'}
            </Button>
            <Button onClick={() => navigate('/restaurants')}>Bekor qilish</Button>
          </Form.Item>
        </Form>
      </Card>

      <YandexMapPicker
        open={mapOpen}
        onClose={() => setMapOpen(false)}
        onSelect={handleMapSelect}
        lat={mapCoords[0]}
        lon={mapCoords[1]}
      />

      {/* ── Filiallar bo'limi ── */}
      {isEdit && (
        <Card style={{ maxWidth: 780, marginTop: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <Title level={5} style={{ margin: 0 }}>Filiallar</Title>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => openBranchModal()}
              style={{ background: '#722ed1', borderColor: '#722ed1' }}>
              Filial qo'shish
            </Button>
          </div>

          <Table
            dataSource={branches}
            rowKey="id"
            loading={branchLoading}
            size="small"
            pagination={false}
            columns={[
              { title: 'Nomi', dataIndex: 'name', key: 'name' },
              { title: 'Manzil', dataIndex: 'address', key: 'address', ellipsis: true },
              { title: 'Telefon', dataIndex: 'phone', key: 'phone' },
              {
                title: 'Ish vaqti', key: 'hours',
                render: (_, r) => `${r.work_hours_from} – ${r.work_hours_until}`,
              },
              {
                title: 'Holat', key: 'is_active',
                render: (_, r) => (
                  <Tag color={r.is_active ? 'green' : 'red'}>
                    {r.is_active ? 'Faol' : 'Nofaol'}
                  </Tag>
                ),
              },
              {
                title: '', key: 'actions', width: 100,
                render: (_, r) => (
                  <Space>
                    <Button size="small" icon={<EditOutlined />} onClick={() => openBranchModal(r)} />
                    <Popconfirm title="O'chirilsinmi?" onConfirm={() => handleBranchDelete(r.id)}>
                      <Button size="small" danger icon={<DeleteOutlined />} />
                    </Popconfirm>
                  </Space>
                ),
              },
            ]}
          />
        </Card>
      )}

      {/* ── Filial modal ── */}
      <Modal
        open={branchModalOpen}
        onCancel={() => setBranchModalOpen(false)}
        onOk={handleBranchSave}
        okText={editingBranch ? 'Saqlash' : 'Qo\'shish'}
        cancelText="Bekor"
        title={editingBranch ? 'Filialni tahrirlash' : 'Yangi filial'}
        width={600}
        okButtonProps={{ style: { background: '#722ed1', borderColor: '#722ed1' } }}
      >
        <Form form={branchForm} layout="vertical"
          initialValues={{
            work_hours_from: '09:00', work_hours_until: '22:00',
            min_order: 30000, delivery_base_fee: 10000, delivery_per_km: 3000,
            latitude: 41.2995, longitude: 69.2401,
          }}
        >
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="name" label="Filial nomi" rules={[{ required: true, message: 'Nom kiriting' }]}>
                <Input placeholder="Markaziy filial" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="phone" label="Telefon">
                <Input placeholder="+998901234567" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="address" label="Manzil">
            <Input placeholder="Toshkent sh., Chilonzor t." />
          </Form.Item>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="latitude" label="Lat">
                <InputNumber style={{ width: '100%' }} precision={6} step={0.001} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="longitude" label="Lon">
                <InputNumber style={{ width: '100%' }} precision={6} step={0.001} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label=" ">
                <Button icon={<EnvironmentOutlined />} block onClick={() => {
                  const lat = branchForm.getFieldValue('latitude') || 41.2995
                  const lon = branchForm.getFieldValue('longitude') || 69.2401
                  setBranchMapCoords([lat, lon])
                  setBranchMapOpen(true)
                }}>
                  Xarita
                </Button>
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="work_hours_from" label="Ochilish">
                <Input placeholder="09:00" maxLength={5} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="work_hours_until" label="Yopilish">
                <Input placeholder="22:00" maxLength={5} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="min_order" label="Min. buyurtma">
                <InputNumber style={{ width: '100%' }} min={0} step={1000} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="delivery_base_fee" label="Baza dastavka">
                <InputNumber style={{ width: '100%' }} min={0} step={500} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="delivery_per_km" label="Har km">
                <InputNumber style={{ width: '100%' }} min={0} step={500} />
              </Form.Item>
            </Col>
          </Row>
          {editingBranch && (
            <Form.Item name="is_active" label="Holat" valuePropName="checked">
              <Switch checkedChildren="Faol" unCheckedChildren="Nofaol" />
            </Form.Item>
          )}
        </Form>
      </Modal>

      <YandexMapPicker
        open={branchMapOpen}
        onClose={() => setBranchMapOpen(false)}
        onSelect={handleBranchMapSelect}
        lat={branchMapCoords[0]}
        lon={branchMapCoords[1]}
      />
    </div>
  )
}
