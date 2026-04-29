import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Table, Button, Tag, Space, Typography, message, Card, Input, Modal,
  Form, Select, InputNumber, DatePicker, Alert,
} from 'antd'
import {
  PlusOutlined, EditOutlined, SearchOutlined, ReloadOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  getSuperAdminRestaurants, patchSuperAdminRestaurant, getPlans,
} from '../api'

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
  const [form] = Form.useForm()
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
        ? dayjs(v).format('DD.MM.YYYY')
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
      title: 'Amal', width: 100,
      render: (_, record) => (
        <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>
          Tahrir
        </Button>
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
            onClick={() => navigate('/restaurants/new')}
            style={{ background: '#722ed1', borderColor: '#722ed1' }}>
            Yangi
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
    </div>
  )
}
