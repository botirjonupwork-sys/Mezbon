import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Table, Button, Tag, Space, Typography, message, Card, Input, Modal,
  Form, Select, InputNumber, DatePicker, Alert,
} from 'antd'
import {
  PlusOutlined, EditOutlined, SearchOutlined, ReloadOutlined,
  KeyOutlined, IdcardOutlined, StopOutlined,
} from '@ant-design/icons'
import { Popconfirm } from 'antd'
import dayjs from 'dayjs'
import {
  getSuperAdminRestaurants, patchSuperAdminRestaurant, getPlans,
  setRestaurantCredentials, updateRestaurantInfo, createSuperRestaurant,
  softDeleteRestaurant,
} from '../api'
import { fmtDateOnly } from '../utils/datetime'

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
  const [form] = Form.useForm()
  const [credsForm] = Form.useForm()
  const [infoForm] = Form.useForm()
  const [createForm] = Form.useForm()
  const navigate = useNavigate()

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
      is_verified: record.is_verified,
    })
  }

  const onCredsSave = async () => {
    try {
      const v = await credsForm.validateFields()
      const payload = {}
      if (v.admin_username) payload.admin_username = v.admin_username
      if (v.admin_password) payload.admin_password = v.admin_password
      if (!Object.keys(payload).length) {
        message.warning('Kamida bittasi kiritilishi kerak')
        return
      }
      await setRestaurantCredentials(credsEditing.id, payload)
      message.success('Login/parol yangilandi')
      setCredsEditing(null)
      await load()
    } catch (e) {
      if (!e?.errorFields) message.error(e?.response?.data?.detail || 'Xato')
    }
  }

  const onInfoSave = async () => {
    try {
      const v = await infoForm.validateFields()
      await updateRestaurantInfo(infoEditing.id, v)
      message.success('Restoran ma\'lumotlari yangilandi')
      setInfoEditing(null)
      await load()
    } catch (e) {
      if (!e?.errorFields) message.error(e?.response?.data?.detail || 'Xato')
    }
  }

  const onCreate = async () => {
    try {
      const v = await createForm.validateFields()
      const r = await createSuperRestaurant(v)
      message.success(`✅ Restoran #${r.restaurant.id} (${r.restaurant.name}) yaratildi`)
      Modal.info({
        title: 'Keyingi qadamlar',
        width: 500,
        content: (
          <ul>
            {(r.next_steps || []).map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        ),
      })
      setCreating(false)
      await load()
    } catch (e) {
      if (!e?.errorFields) message.error(e?.response?.data?.detail || 'Yaratishda xato')
    }
  }

  const onSave = async () => {
    setSaving(true)
    try {
      const v = await form.validateFields()
      const payload = {
        status: v.status,
        plan_id: v.plan_id,
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
      title: 'Amal', width: 320,
      render: (_, record) => (
        <Space size="small" wrap>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>
            Tarif
          </Button>
          <Button size="small" icon={<IdcardOutlined />} onClick={() => openInfoEdit(record)}>
            Ma'lumotlar
          </Button>
          <Button size="small" icon={<KeyOutlined />} onClick={() => openCredsEdit(record)}>
            Login/Parol
          </Button>
          {record.status !== 'blocked' ? (
            <Popconfirm
              title="Restoranni bloklash?"
              description="Tiklash mumkin (Tarif → status='active')."
              okText="Bloklash"
              cancelText="Bekor"
              onConfirm={async () => {
                try {
                  await softDeleteRestaurant(record.id)
                  message.success('Restoran bloklandi')
                  await load()
                } catch (e) {
                  message.error(e?.response?.data?.detail || 'Xato')
                }
              }}
            >
              <Button size="small" icon={<StopOutlined />} danger>Bloklash</Button>
            </Popconfirm>
          ) : (
            <Tag color="default">bloklangan</Tag>
          )}
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
            onClick={() => { createForm.resetFields(); setCreating(true) }}
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

      {/* Yangi restoran yaratish */}
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
          <Form.Item name="address" label="Manzil">
            <Input.TextArea rows={2} placeholder="Toshkent, Chilonzor 7" />
          </Form.Item>
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

      {/* Restoran admin login/parol */}
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

      {/* Restoran ma'lumotlari */}
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
