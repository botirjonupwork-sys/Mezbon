import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Table, Button, Tag, Space, Typography, message, Card, Input, Modal,
  Form, Select, InputNumber, DatePicker, Alert, Dropdown, Switch, Divider,
  Row, Col, Tooltip, Badge, Popconfirm,
} from 'antd'
import {
  PlusOutlined, EditOutlined, SearchOutlined, ReloadOutlined,
  KeyOutlined, IdcardOutlined, StopOutlined, CheckCircleOutlined,
  ShopOutlined, MoreOutlined, DeleteOutlined, EnvironmentOutlined,
  CompassOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  getSuperAdminRestaurants, patchSuperAdminRestaurant, getPlans,
  setRestaurantCredentials, updateRestaurantInfo, createSuperRestaurant,
  softDeleteRestaurant,
  getBranches, createBranch, updateBranch, deleteBranch,
} from '../api'
import { fmtDateOnly } from '../utils/datetime'
import LocationPicker from '../components/LocationPicker'

const { Title, Text } = Typography

const STATUS_TAG = {
  active:  { color: 'green',  text: 'Aktiv' },
  blocked: { color: 'red',    text: 'Bloklangan' },
  trial:   { color: 'orange', text: 'Sinov' },
}

const PLAN_COLOR = { free: 'default', basic: 'blue', pro: 'gold' }

function fmtUZS(v) {
  return new Intl.NumberFormat('uz-UZ').format(Math.round(v || 0))
}

export default function Restaurants() {
  const [data, setData] = useState([])
  const [plans, setPlans] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [search, setSearch] = useState('')
  const [editing, setEditing] = useState(null)
  const [credsEditing, setCredsEditing] = useState(null)
  const [infoEditing, setInfoEditing] = useState(null)
  const [creating, setCreating] = useState(false)

  // ── Filiallar boshqaruvi uchun state'lar ──
  const [branchRestaurant, setBranchRestaurant] = useState(null)
  const [branchesList, setBranchesList] = useState([])
  const [branchesLoading, setBranchesLoading] = useState(false)
  const [branchFormOpen, setBranchFormOpen] = useState(false)
  const [editingBranch, setEditingBranch] = useState(null)
  const [branchSaving, setBranchSaving] = useState(false)

  const [form] = Form.useForm()
  const [credsForm] = Form.useForm()
  const [infoForm] = Form.useForm()
  const [createForm] = Form.useForm()
  const [branchForm] = Form.useForm()
  const navigate = useNavigate()

  // Xarita uchun joriy qiymatlar (useWatch)
  const branchLat = Form.useWatch('latitude', branchForm)
  const branchLon = Form.useWatch('longitude', branchForm)
  const branchAddr = Form.useWatch('address', branchForm)

  const createLat = Form.useWatch('restaurant_lat', createForm) || 41.2995
  const createLon = Form.useWatch('restaurant_lon', createForm) || 69.2401
  const createAddr = Form.useWatch('address', createForm)

  const load = async () => {
    setLoading(true)
    try {
      const [r, p] = await Promise.all([
        getSuperAdminRestaurants(),
        getPlans().catch(() => ({ data: [] })),
      ])
      setData(r.data || [])
      setPlans(p.data || [])
    } catch (e) {
      message.error(e?.response?.data?.detail || 'Yuklashda xato')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const filtered = data.filter((r) => {
    if (!search) return true
    const q = search.toLowerCase()
    return (
      (r.name || '').toLowerCase().includes(q) ||
      (r.slug || '').toLowerCase().includes(q) ||
      (r.phone || '').includes(q)
    )
  })

  // ── Filiallarni yuklash ──
  const loadBranches = async (restaurantId) => {
    setBranchesLoading(true)
    try {
      const res = await getBranches(restaurantId)
      setBranchesList(res.data || [])
    } catch (e) {
      message.error(e?.response?.data?.detail || 'Filiallarni yuklashda xato')
    } finally {
      setBranchesLoading(false)
    }
  }

  const openBranchesModal = (record) => {
    setBranchRestaurant(record)
    loadBranches(record.id)
  }

  const detectLocation = () => {
    if (!navigator.geolocation) {
      message.warning("Brauzeringiz geolokatsiyani qo'llab-quvvatlamaydi")
      return
    }
    const hide = message.loading("Joylashuv aniqlanmoqda...", 0)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        hide()
        const lat = Number(pos.coords.latitude.toFixed(6))
        const lon = Number(pos.coords.longitude.toFixed(6))
        branchForm.setFieldsValue({ latitude: lat, longitude: lon })
        message.success(`Koordinata aniqlandi: ${lat}, ${lon}`)
      },
      (err) => {
        hide()
        message.error("Joylashuvni aniqlab bo'lmadi: " + err.message)
      },
      { enableHighAccuracy: true, timeout: 10000 }
    )
  }

  const openAddBranch = () => {
    setEditingBranch(null)
    branchForm.resetFields()
    branchForm.setFieldsValue({
      name: '',
      phone: '+998',
      address: '',
      landmark: '',
      latitude: 41.299500,
      longitude: 69.240100,
      work_hours_from: '09:00',
      work_hours_until: '22:00',
      min_order: 30000,
      delivery_base_fee: 10000,
      delivery_per_km: 3000,
      max_delivery_radius_km: 15.0,
      is_delivery_enabled: true,
      is_takeaway_enabled: true,
      kitchen_chat_id: '',
      cashier_chat_id: '',
      is_active: true,
    })
    setBranchFormOpen(true)
  }

  const openEditBranch = (branch) => {
    setEditingBranch(branch)
    branchForm.resetFields()
    branchForm.setFieldsValue({
      name: branch.name,
      address: branch.address,
      landmark: branch.landmark,
      phone: branch.phone,
      latitude: branch.latitude,
      longitude: branch.longitude,
      work_hours_from: branch.work_hours_from || '09:00',
      work_hours_until: branch.work_hours_until || '22:00',
      min_order: branch.min_order ?? 30000,
      delivery_base_fee: branch.delivery_base_fee ?? 10000,
      delivery_per_km: branch.delivery_per_km ?? 3000,
      is_delivery_enabled: branch.is_delivery_enabled !== false,
      is_takeaway_enabled: branch.is_takeaway_enabled !== false,
      kitchen_chat_id: branch.kitchen_chat_id,
      cashier_chat_id: branch.cashier_chat_id,
      max_delivery_radius_km: branch.max_delivery_radius_km ?? 15.0,
      is_active: branch.is_active !== false,
    })
    setBranchFormOpen(true)
  }

  const handleSaveBranch = async () => {
    try {
      const values = await branchForm.validateFields()
      setBranchSaving(true)
      if (editingBranch) {
        await updateBranch(editingBranch.id, values)
        message.success("Filial muvaffaqiyatli yangilandi")
      } else {
        await createBranch(branchRestaurant.id, values)
        message.success("Yangi filial muvaffaqiyatli qo'shildi")
      }
      setBranchFormOpen(false)
      await loadBranches(branchRestaurant.id)
    } catch (e) {
      if (!e?.errorFields) message.error(e?.response?.data?.detail || "Saqlashda xato")
    } finally {
      setBranchSaving(false)
    }
  }

  const handleDeleteBranch = async (branchId) => {
    try {
      await deleteBranch(branchId)
      message.success("Filial o'chirildi")
      await loadBranches(branchRestaurant.id)
    } catch (e) {
      message.error(e?.response?.data?.detail || "O'chirishda xato")
    }
  }

  const openEdit = (record) => {
    setEditing(record)
    form.setFieldsValue({
      status: record.status,
      plan_id: record.plan_id,
      plan_expires_at: record.plan_expires_at ? dayjs(record.plan_expires_at) : null,
      commission_percent: record.commission_percent,
      extend_days: undefined,
    })
  }

  const openCredsEdit = (record) => {
    setCredsEditing(record)
    credsForm.setFieldsValue({
      admin_username: record.admin_username || '',
      admin_password: '',
    })
  }

  const openInfoEdit = (record) => {
    setInfoEditing(record)
    infoForm.setFieldsValue({
      name: record.name || '',
      inn: record.inn || '',
      phone: record.phone || '',
      address: record.address || '',
      logo_url: record.logo_url || '',
      catering_payment_card: record.catering_payment_card || '',
      catering_payment_owner: record.catering_payment_owner || '',
      is_verified: !!record.is_verified,
    })
  }

  const onCredsSave = async () => {
    try {
      const v = await credsForm.validateFields()
      setSaving(true)
      await setRestaurantCredentials(credsEditing.id, {
        admin_username: v.admin_username,
        admin_password: v.admin_password || undefined,
      })
      message.success('Kirish ma\'lumotlari yangilandi')
      setCredsEditing(null)
      await load()
    } catch (e) {
      if (!e?.errorFields) message.error(e?.response?.data?.detail || 'Xato')
    } finally {
      setSaving(false)
    }
  }

  const onInfoSave = async () => {
    try {
      const v = await infoForm.validateFields()
      setSaving(true)
      await updateRestaurantInfo(infoEditing.id, v)
      message.success('Ma\'lumotlar yangilandi')
      setInfoEditing(null)
      await load()
    } catch (e) {
      if (!e?.errorFields) message.error(e?.response?.data?.detail || 'Xato')
    } finally {
      setSaving(false)
    }
  }

  const onCreate = async () => {
    try {
      const v = await createForm.validateFields()
      setSaving(true)
      await createSuperRestaurant(v)
      message.success('Restoran muvaffaqiyatli yaratildi')
      setCreating(false)
      createForm.resetFields()
      await load()
    } catch (e) {
      if (!e?.errorFields) message.error(e?.response?.data?.detail || 'Yaratishda xato')
    } finally {
      setSaving(false)
    }
  }

  const onSave = async () => {
    try {
      const v = await form.validateFields()
      setSaving(true)
      const payload = {
        status: v.status,
        plan_id: v.plan_id ?? null,
        commission_percent: v.commission_percent,
      }
      if (v.plan_expires_at) payload.plan_expires_at = v.plan_expires_at.toISOString()
      if (v.extend_days) payload.extend_days = Number(v.extend_days)

      await patchSuperAdminRestaurant(editing.id, payload)
      message.success('Restoran yangilandi (audit log\'ga yozildi)')
      setEditing(null)
      await load()
    } catch (e) {
      if (!e?.errorFields) message.error(e?.response?.data?.detail || 'Saqlashda xato')
    } finally {
      setSaving(false)
    }
  }

  const getActionMenuItems = (record) => {
    const isBlocked = record.status === 'blocked'
    return [
      {
        key: 'branches',
        icon: <ShopOutlined style={{ color: '#1890ff' }} />,
        label: <span style={{ fontWeight: 500 }}>🏢 Filiallar boshqaruvi</span>,
        onClick: () => openBranchesModal(record),
      },
      { type: 'divider' },
      {
        key: 'plan',
        icon: <EditOutlined />,
        label: 'Tarif sozlamalari',
        onClick: () => openEdit(record),
      },
      {
        key: 'info',
        icon: <IdcardOutlined />,
        label: "Ma'lumotlarni tahrirlash",
        onClick: () => openInfoEdit(record),
      },
      {
        key: 'creds',
        icon: <KeyOutlined />,
        label: 'Login / Parol',
        onClick: () => openCredsEdit(record),
      },
      { type: 'divider' },
      !isBlocked
        ? {
            key: 'block',
            icon: <StopOutlined style={{ color: '#ff4d4f' }} />,
            danger: true,
            label: 'Restoranni bloklash',
            onClick: () => {
              Modal.confirm({
                title: 'Restoranni bloklash?',
                content: 'Bloklangach, mijozlar va adminlar ushbu restorandan foydalana olmaydi.',
                okText: 'Bloklash',
                okType: 'danger',
                cancelText: 'Bekor',
                onOk: async () => {
                  try {
                    await softDeleteRestaurant(record.id)
                    message.success('Restoran bloklandi')
                    await load()
                  } catch (e) {
                    message.error(e?.response?.data?.detail || 'Xato')
                  }
                },
              })
            },
          }
        : {
            key: 'unblock',
            icon: <CheckCircleOutlined style={{ color: '#52c41a' }} />,
            label: 'Faollashtirish (Aktiv)',
            onClick: async () => {
              try {
                await patchSuperAdminRestaurant(record.id, { status: 'active' })
                message.success('Restoran faollashtirildi')
                await load()
              } catch (e) {
                message.error(e?.response?.data?.detail || 'Xato')
              }
            },
          },
    ]
  }

  const columns = [
    { title: '#', dataIndex: 'id', width: 60 },
    {
      title: 'Restoran', dataIndex: 'name',
      render: (v, r) => (
        <Space direction="vertical" size={0}>
          <Text strong>{v}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {r.slug || '—'} · {r.phone || '—'}
          </Text>
        </Space>
      ),
    },
    {
      title: 'Holat', dataIndex: 'status', width: 110,
      render: (s) => {
        const v = STATUS_TAG[s] || { color: 'default', text: s }
        return <Tag color={v.color}>{v.text}</Tag>
      },
    },
    {
      title: 'Tarif', dataIndex: 'plan_slug', width: 100,
      render: (slug) => slug
        ? <Tag color={PLAN_COLOR[slug] || 'default'}>{slug.toUpperCase()}</Tag>
        : <Tag>—</Tag>,
    },
    {
      title: 'Muddat', dataIndex: 'plan_expires_at',
      render: (v) => v
        ? fmtDateOnly(v)
        : <Text type="secondary">cheksiz</Text>,
    },
    {
      title: "Tushum (so'm)", dataIndex: 'revenue_uzs',
      render: (v, r) => (
        <Space direction="vertical" size={0}>
          <Text strong>{fmtUZS(v)}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{r.orders_count} ta zakaz</Text>
        </Space>
      ),
    },
    {
      title: 'Komissiya', dataIndex: 'commission_percent', width: 110,
      render: (v) => <Text>{(v || 0).toFixed(1)}%</Text>,
    },
    {
      title: 'Amallar', width: 90, align: 'center', fixed: 'right',
      render: (_, record) => (
        <Dropdown
          menu={{ items: getActionMenuItems(record) }}
          trigger={['click']}
          placement="bottomRight"
        >
          <Button
            size="middle"
            type="text"
            icon={<MoreOutlined style={{ fontSize: 20 }} />}
            style={{ borderRadius: 6 }}
          />
        </Dropdown>
      ),
    },
  ]

  // Filiallar jadvali ustunlari
  const branchTableColumns = [
    {
      title: 'Filial nomi',
      dataIndex: 'name',
      render: (v, r) => (
        <Space direction="vertical" size={0}>
          <Text strong>{v}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            <EnvironmentOutlined /> {r.address || "Manzil ko'rsatilmagan"} {r.landmark ? `(Mo'ljal: ${r.landmark})` : ''}
          </Text>
        </Space>
      ),
    },
    {
      title: 'Telefon',
      dataIndex: 'phone',
      width: 140,
      render: (p) => p || '—',
    },
    {
      title: 'Ish vaqti',
      width: 130,
      render: (_, r) => `${r.work_hours_from || '09:00'} - ${r.work_hours_until || '22:00'}`,
    },
    {
      title: 'Xizmatlar',
      width: 170,
      render: (_, r) => (
        <Space size={4}>
          <Tag color={r.is_delivery_enabled !== false ? 'green' : 'default'}>
            🚗 {r.is_delivery_enabled !== false ? 'Dastavka' : 'Yo\'q'}
          </Tag>
          <Tag color={r.is_takeaway_enabled !== false ? 'blue' : 'default'}>
            🛍️ {r.is_takeaway_enabled !== false ? 'Saboy' : 'Yo\'q'}
          </Tag>
        </Space>
      ),
    },
    {
      title: 'Holat',
      dataIndex: 'is_active',
      width: 90,
      render: (act) => (
        <Badge
          status={act !== false ? 'success' : 'default'}
          text={act !== false ? 'Aktiv' : 'Nofaol'}
        />
      ),
    },
    {
      title: 'Amal',
      width: 110,
      align: 'right',
      render: (_, branch) => (
        <Space size="small">
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => openEditBranch(branch)}
          />
          <Popconfirm
            title="Filialni o'chirish?"
            description="Ushbu filial o'chiriladi."
            okText="O'chirish"
            cancelText="Bekor"
            okType="danger"
            onConfirm={() => handleDeleteBranch(branch.id)}
          >
            <Button size="small" icon={<DeleteOutlined />} danger />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Space style={{ marginBottom: 16, justifyContent: 'space-between', width: '100%' }}>
        <Title level={4} style={{ margin: 0 }}>🏪 Restoranlar</Title>
        <Space>
          <Input
            prefix={<SearchOutlined />}
            placeholder="Qidiruv..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 220 }}
            allowClear
          />
          <Button icon={<ReloadOutlined />} onClick={load}>Yangilash</Button>
          <Button type="primary" icon={<PlusOutlined />}
            onClick={() => {
              createForm.resetFields()
              createForm.setFieldsValue({
                is_verified: true,
                restaurant_lat: 41.2995,
                restaurant_lon: 69.2401,
              })
              setCreating(true)
            }}
            style={{ background: '#722ed1', borderColor: '#722ed1' }}>
            Yangi restoran
          </Button>
        </Space>
      </Space>

      <Card size="small">
        <Table
          rowKey="id"
          dataSource={filtered}
          columns={columns}
          loading={loading}
          pagination={{ pageSize: 20 }}
          scroll={{ x: 900 }}
        />
      </Card>

      {/* ── Filiallar boshqaruvi modali ── */}
      <Modal
        title={
          <Space>
            <ShopOutlined style={{ color: '#722ed1', fontSize: 20 }} />
            <span><b>{branchRestaurant?.name}</b> — Filiallar boshqaruvi</span>
          </Space>
        }
        open={!!branchRestaurant}
        onCancel={() => setBranchRestaurant(null)}
        footer={[
          <Button key="close" onClick={() => setBranchRestaurant(null)}>
            Yopish
          </Button>,
        ]}
        width={950}
        destroyOnClose
      >
        <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text type="secondary">
            Barcha buyurtmalar filial koordinatalari va faol xizmat turlariga qarab taqsimlanadi.
          </Text>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={openAddBranch}
            style={{ background: '#722ed1', borderColor: '#722ed1' }}
          >
            Yangi filial qo'shish
          </Button>
        </div>

        <Table
          rowKey="id"
          dataSource={branchesList}
          columns={branchTableColumns}
          loading={branchesLoading}
          pagination={false}
          size="middle"
          locale={{ emptyText: "Ushbu restoranda hali filiallar qo'shilmagan" }}
        />
      </Modal>

      {/* ── Filial qo'shish / tahrirlash formasi modali ── */}
      <Modal
        title={
          editingBranch
            ? `Filialni tahrirlash: ${editingBranch.name}`
            : `Yangi filial qo'shish — ${branchRestaurant?.name}`
        }
        open={branchFormOpen}
        onCancel={() => setBranchFormOpen(false)}
        onOk={handleSaveBranch}
        confirmLoading={branchSaving}
        okText="Saqlash"
        cancelText="Bekor"
        width={720}
        destroyOnClose
      >
        <Form form={branchForm} layout="vertical">
          <Row gutter={16}>
            <Col span={14}>
              <Form.Item
                name="name"
                label="Filial nomi"
                rules={[
                  { required: true, message: 'Filial nomi kiritilishi shart' },
                  { min: 3, message: 'Kamida 3 ta belgi' },
                  { max: 60, message: 'Ko‘pi bilan 60 ta belgi' },
                  { whitespace: true, message: 'Bo‘sh joylardan iborat bo‘lmasin' },
                ]}
              >
                <Input placeholder="Masalan: Chilonzor filiali" maxLength={60} showCount />
              </Form.Item>
            </Col>
            <Col span={10}>
              <Form.Item
                name="phone"
                label="Telefon raqami"
                rules={[
                  { required: true, message: 'Telefon raqami kiritilishi shart' },
                  { pattern: /^\+998\d{9}$/, message: 'Format: +998901234567 (12 ta belgi: +998 va 9 ta raqam)' },
                ]}
              >
                <Input
                  placeholder="+998901234567"
                  maxLength={13}
                  onChange={(e) => {
                    let val = e.target.value.replace(/[^\d+]/g, '')
                    if (!val.startsWith('+998') && val.startsWith('998')) val = '+' + val
                    else if (!val.startsWith('+') && val.length > 0) val = '+998' + val
                    branchForm.setFieldsValue({ phone: val })
                  }}
                />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={14}>
              <Form.Item
                name="address"
                label="Aniq manzil"
                rules={[
                  { required: true, message: 'Manzil kiritilishi shart' },
                  { min: 5, message: 'Kamida 5 ta belgi' },
                  { max: 200, message: 'Ko‘pi bilan 200 ta belgi' },
                ]}
              >
                <Input placeholder="Toshkent sh., Chilonzor tumani, 7-mavze" maxLength={200} />
              </Form.Item>
            </Col>
            <Col span={10}>
              <Form.Item
                name="landmark"
                label="Mo'ljal (Landmark)"
                rules={[{ max: 100, message: 'Ko‘pi bilan 100 ta belgi' }]}
              >
                <Input placeholder="Masalan: Rayhon milliy taomlari ro'parasi" maxLength={100} />
              </Form.Item>
            </Col>
          </Row>

          <Divider orientation="left" style={{ margin: '8px 0 16px' }}>
            📍 Filial joylashuvi (Yandex Maps orqali tanlash)
          </Divider>

          <LocationPicker
            lat={branchLat || 41.2995}
            lon={branchLon || 69.2401}
            address={branchAddr || ''}
            onChange={({ lat, lon, address }) => {
              branchForm.setFieldsValue({
                latitude: lat,
                longitude: lon,
                address: address || branchForm.getFieldValue('address'),
              })
            }}
            height={260}
          />

          <Row gutter={16} style={{ marginTop: 12 }}>
            <Col span={12}>
              <Form.Item
                name="latitude"
                label="Kenglik (Latitude)"
                rules={[
                  { required: true, message: 'Kenglik (Latitude) kiritilishi shart' },
                  {
                    type: 'number',
                    min: 35.0,
                    max: 46.0,
                    message: "O'zbekiston hududi uchun 35.0 dan 46.0 gacha bo'lishi kerak",
                  },
                ]}
              >
                <InputNumber
                  style={{ width: '100%' }}
                  placeholder="Masalan: 41.299500"
                  step={0.000001}
                  precision={6}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="longitude"
                label="Uzunlik (Longitude)"
                rules={[
                  { required: true, message: 'Uzunlik (Longitude) kiritilishi shart' },
                  {
                    type: 'number',
                    min: 55.0,
                    max: 74.0,
                    message: "O'zbekiston hududi uchun 55.0 dan 74.0 gacha bo'lishi kerak",
                  },
                ]}
              >
                <InputNumber
                  style={{ width: '100%' }}
                  placeholder="Masalan: 69.240100"
                  step={0.000001}
                  precision={6}
                />
              </Form.Item>
            </Col>
          </Row>

          <Divider orientation="left" style={{ margin: '8px 0 16px' }}>⏰ Ish vaqti va xizmat turlari</Divider>

          <Row gutter={16}>
            <Col span={6}>
              <Form.Item
                name="work_hours_from"
                label="Ochilish vaqti"
                rules={[
                  { required: true, message: 'Ochilish vaqti majburiy' },
                  { pattern: /^([01]\d|2[0-3]):[0-5]\d$/, message: 'Format: HH:mm (09:00)' },
                ]}
              >
                <Input placeholder="09:00" maxLength={5} />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item
                name="work_hours_until"
                label="Yopilish vaqti"
                rules={[
                  { required: true, message: 'Yopilish vaqti majburiy' },
                  { pattern: /^([01]\d|2[0-3]):[0-5]\d$/, message: 'Format: HH:mm (22:00)' },
                ]}
              >
                <Input placeholder="22:00" maxLength={5} />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="is_delivery_enabled" label="Dastavka" valuePropName="checked">
                <Switch checkedChildren="Bor" unCheckedChildren="Yo'q" />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="is_takeaway_enabled" label="Saboy (Olib ketish)" valuePropName="checked">
                <Switch checkedChildren="Bor" unCheckedChildren="Yo'q" />
              </Form.Item>
            </Col>
          </Row>

          <Divider orientation="left" style={{ margin: '8px 0 16px' }}>💰 Tarif va logistika parametrlari</Divider>

          <Row gutter={16}>
            <Col span={8}>
              <Form.Item
                name="min_order"
                label="Min. buyurtma (so'm)"
                rules={[{ required: true, message: 'Min. buyurtma summasi kiritilishi shart' }]}
              >
                <InputNumber
                  min={0}
                  max={50000000}
                  step={5000}
                  style={{ width: '100%' }}
                  formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ' ')}
                  parser={(v) => v.replace(/\s?|(,*)/g, '')}
                  placeholder="30 000"
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="delivery_base_fee"
                label="Boshlang'ich narx (so'm)"
                rules={[{ required: true, message: 'Boshlang‘ich to‘lov majburiy' }]}
              >
                <InputNumber
                  min={0}
                  max={1000000}
                  step={1000}
                  style={{ width: '100%' }}
                  formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ' ')}
                  parser={(v) => v.replace(/\s?|(,*)/g, '')}
                  placeholder="10 000"
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="delivery_per_km"
                label="Har 1 km narxi (so'm)"
                rules={[{ required: true, message: 'Km narxi majburiy' }]}
              >
                <InputNumber
                  min={0}
                  max={100000}
                  step={500}
                  style={{ width: '100%' }}
                  formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ' ')}
                  parser={(v) => v.replace(/\s?|(,*)/g, '')}
                  placeholder="3 000"
                />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={8}>
              <Form.Item
                name="max_delivery_radius_km"
                label="Max radius (km)"
                rules={[{ required: true, message: 'Maksimal radius majburiy' }]}
              >
                <InputNumber min={0.5} max={50.0} step={0.5} style={{ width: '100%' }} placeholder="15.0" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="kitchen_chat_id"
                label="Oshxona Telegram Chat ID"
                rules={[
                  { pattern: /^-?\d{5,20}$/, message: 'Telegram ID raqam bo‘lishi kerak (masalan: -100123456789)' },
                ]}
              >
                <Input placeholder="Masalan: -100123456789" maxLength={20} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="cashier_chat_id"
                label="Kassa Telegram Chat ID"
                rules={[
                  { pattern: /^-?\d{5,20}$/, message: 'Telegram ID raqam bo‘lishi kerak (masalan: -100123456789)' },
                ]}
              >
                <Input placeholder="Masalan: -100123456789" maxLength={20} />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item name="is_active" label="Filial holati" valuePropName="checked">
            <Switch checkedChildren="Aktiv" unCheckedChildren="Nofaol" />
          </Form.Item>
        </Form>
      </Modal>

      {/* ── Tarif sozlamalari modali ── */}
      <Modal
        title={`${editing?.name || ''} — sozlash`}
        open={!!editing}
        onCancel={() => setEditing(null)}
        onOk={onSave}
        confirmLoading={saving}
        okText="Saqlash"
        cancelText="Bekor"
        width={520}
      >
        <Alert
          type="warning" showIcon style={{ marginBottom: 16 }}
          message="Diqqat — har bir o'zgartirish audit log'ga yoziladi"
        />
        <Form form={form} layout="vertical">
          <Form.Item name="status" label="Holat">
            <Select options={[
              { value: 'active',  label: '✅ Aktiv' },
              { value: 'trial',   label: '🟠 Sinov' },
              { value: 'blocked', label: '🚫 Bloklangan' },
            ]} />
          </Form.Item>
          <Form.Item name="plan_id" label="Tarif">
            <Select
              allowClear
              placeholder="Tarif tanlang"
              options={(plans || []).map((p) => ({ value: p.id, label: p.name }))}
            />
          </Form.Item>
          <Form.Item name="plan_expires_at" label="Amal qilish muddati"
            extra="Bo'sh qoldirilsa cheksiz">
            <DatePicker format="DD.MM.YYYY" style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="extend_days" label="Yoki — kun qo'shish (extend)"
            extra="extend_days yuborilsa, plan_expires_at avtomatik hisoblanadi">
            <InputNumber min={1} max={365} style={{ width: '100%' }} placeholder="masalan 30" />
          </Form.Item>
          <Form.Item name="commission_percent" label="Komissiya %">
            <InputNumber min={0} max={100} step={0.5} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* ── Yangi restoran yaratish ── */}
      <Modal
        title={<><PlusOutlined /> Yangi restoran qo'shish</>}
        open={creating}
        onCancel={() => setCreating(false)}
        onOk={onCreate}
        okText="Yaratish"
        cancelText="Bekor"
        width={680}
        destroyOnClose
      >
        <Alert type="info" showIcon style={{ marginBottom: 16 }}
          message="Super-admin manual qo'shadi"
          description="Restoran avtomatik tasdiqlangan (is_verified=True) va Free tarifda boshlanadi. Bot tokenini keyin Settings'da ham qo'shsa bo'ladi." />
        <Form form={createForm} layout="vertical" initialValues={{ is_verified: true }}>
          <Form.Item name="name" label="Kompaniya nomi"
            rules={[{ required: true, message: 'Nom majburiy' }]}>
            <Input placeholder="Masalan: Muhsina Dollar" />
          </Form.Item>
          <Space style={{ width: '100%' }} size="large">
            <Form.Item name="inn" label="INN (9 raqam)" style={{ flex: 1, minWidth: 200 }}
              rules={[{ required: true, message: 'INN majburiy' }, { len: 9, message: '9 raqam bo\'lishi shart' }]}>
              <Input placeholder="305405559" maxLength={9} />
            </Form.Item>
            <Form.Item name="phone" label="Telefon" style={{ flex: 1, minWidth: 200 }}>
              <Input placeholder="+998901234567" />
            </Form.Item>
          </Space>
          <Form.Item name="address" label="Bosh manzil">
            <Input placeholder="Xaritadan tanlang yoki kiriting" />
          </Form.Item>
          <div style={{ marginBottom: 16 }}>
            <LocationPicker
              lat={createLat}
              lon={createLon}
              address={createAddr}
              onChange={({ lat, lon, address }) => {
                createForm.setFieldsValue({
                  restaurant_lat: lat,
                  restaurant_lon: lon,
                  address: address || createForm.getFieldValue('address'),
                })
              }}
              height={220}
            />
          </div>
          <div style={{ display: 'none' }}>
            <Form.Item name="restaurant_lat"><Input /></Form.Item>
            <Form.Item name="restaurant_lon"><Input /></Form.Item>
          </div>
          <Alert type="warning" showIcon style={{ marginBottom: 12 }}
            message="Restoran admin login (panelga kirish uchun)" />
          <Space style={{ width: '100%' }} size="large">
            <Form.Item name="admin_username" label="Login (username)" style={{ flex: 1, minWidth: 200 }}
              rules={[{ required: true, message: 'Login majburiy' }, { min: 3, max: 30 }]}>
              <Input prefix={<IdcardOutlined />} placeholder="muhsina_admin" autoComplete="off" />
            </Form.Item>
            <Form.Item name="admin_password" label="Parol" style={{ flex: 1, minWidth: 200 }}
              rules={[{ required: true, message: 'Parol majburiy' }, { min: 6 }]}>
              <Input.Password prefix={<KeyOutlined />} placeholder="Kuchli parol" autoComplete="new-password" />
            </Form.Item>
          </Space>
          <Alert type="warning" showIcon style={{ marginBottom: 12 }}
            message="Bot tokenlari (ixtiyoriy — keyin Sozlamalardan ham qo'shsa bo'ladi)" />
          <Form.Item name="bot_token" label="Customer bot tokeni (BotFather)">
            <Input.Password placeholder="123456:ABC..." autoComplete="off" />
          </Form.Item>
          <Form.Item name="courier_bot_token" label="Courier bot tokeni (BotFather)">
            <Input.Password placeholder="123456:DEF..." autoComplete="off" />
          </Form.Item>
        </Form>
      </Modal>

      {/* ── Restoran admin login/parol ── */}
      <Modal
        title={<><KeyOutlined /> Login va parol — {credsEditing?.name}</>}
        open={!!credsEditing}
        onCancel={() => setCredsEditing(null)}
        onOk={onCredsSave}
        okText="Saqlash"
        cancelText="Bekor"
        destroyOnClose
      >
        <Alert type="warning" showIcon style={{ marginBottom: 16 }}
          message="Diqqat: Eski parol so'ralmaydi"
          description="Super-admin sifatida siz eski parolni bilmasdan to'g'ridan-to'g'ri yangi parol qo'yishingiz mumkin. Bu amal audit log'ga yoziladi." />
        <Form form={credsForm} layout="vertical">
          <Form.Item name="admin_username" label="Login (username)">
            <Input prefix={<IdcardOutlined />} placeholder="masalan: muhsina_admin" autoComplete="off" />
          </Form.Item>
          <Form.Item name="admin_password" label="Yangi parol"
            extra="Bo'sh qoldirsangiz parol o'zgarmaydi">
            <Input.Password prefix={<KeyOutlined />} placeholder="Yangi parol" autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Modal>

      {/* ── Restoran ma'lumotlari ── */}
      <Modal
        title={<><IdcardOutlined /> Restoran ma'lumotlari — {infoEditing?.name}</>}
        open={!!infoEditing}
        onCancel={() => setInfoEditing(null)}
        onOk={onInfoSave}
        okText="Saqlash"
        cancelText="Bekor"
        width={680}
        destroyOnClose
      >
        <Alert type="info" showIcon style={{ marginBottom: 16 }}
          message="Asosiy ma'lumotlar (mahsulotlar tahriri bu yerda yo'q)"
          description="Mahsulot, kategoriya yoki narx o'zgartirish uchun restoran admin paneliga kirish kerak." />
        <Form form={infoForm} layout="vertical">
          <Form.Item name="name" label="Kompaniya nomi"
            rules={[{ required: true, message: "Nom majburiy" }]}>
            <Input />
          </Form.Item>
          <Space style={{ width: '100%' }} size="large">
            <Form.Item name="inn" label="INN (9 raqam)" style={{ flex: 1, minWidth: 200 }}>
              <Input placeholder="305405559" maxLength={9} />
            </Form.Item>
            <Form.Item name="phone" label="Telefon" style={{ flex: 1, minWidth: 200 }}>
              <Input placeholder="+998901234567" />
            </Form.Item>
          </Space>
          <Form.Item name="address" label="Manzil">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="logo_url" label="Logo URL">
            <Input placeholder="https://..." />
          </Form.Item>
          <Space style={{ width: '100%' }} size="large">
            <Form.Item name="catering_payment_card" label="Catering karta raqami" style={{ flex: 1, minWidth: 200 }}>
              <Input placeholder="8600 ..." />
            </Form.Item>
            <Form.Item name="catering_payment_owner" label="Karta egasi" style={{ flex: 1, minWidth: 200 }}>
              <Input placeholder="ISMI FAMILIYASI" />
            </Form.Item>
          </Space>
          <Form.Item name="is_verified" label="INN tasdiqlangan">
            <Select options={[{ value: true, label: '✅ Tasdiqlangan' }, { value: false, label: '❌ Tasdiqlanmagan' }]} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
