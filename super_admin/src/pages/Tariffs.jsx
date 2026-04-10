import { useEffect, useState } from 'react'
import {
  Table, Button, Tag, Space, Typography, Popconfirm, message, Card,
  Modal, Form, Input, InputNumber, Switch, Select
} from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, CrownOutlined } from '@ant-design/icons'
import { getPlans, createPlan, updatePlan, deletePlan } from '../api'

const { Title, Text } = Typography
const { TextArea } = Input

const PLAN_COLORS = { free: 'default', basic: 'blue', pro: 'gold' }

function FeaturesEditor({ value = [], onChange }) {
  const [input, setInput] = useState('')
  const add = () => {
    const trimmed = input.trim()
    if (!trimmed) return
    onChange([...value, trimmed])
    setInput('')
  }
  const remove = (i) => onChange(value.filter((_, idx) => idx !== i))
  return (
    <div>
      <Space style={{ marginBottom: 8 }}>
        <Input
          placeholder="Imkoniyat qo'shish..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onPressEnter={add}
          style={{ width: 260 }}
        />
        <Button onClick={add} type="dashed" size="small">Qo'shish</Button>
      </Space>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {value.map((f, i) => (
          <Tag key={i} closable onClose={() => remove(i)} color="blue">{f}</Tag>
        ))}
      </div>
    </div>
  )
}

export default function Tariffs() {
  const [plans, setPlans] = useState([])
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()

  const load = () => {
    setLoading(true)
    getPlans()
      .then((r) => setPlans(r.data))
      .catch(() => message.error('Yuklashda xato'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ is_active: true, commission_percent: 0, monthly_price: 0, features: [] })
    setModalOpen(true)
  }

  const openEdit = (record) => {
    setEditing(record)
    form.setFieldsValue({
      name: record.name,
      slug: record.slug,
      description: record.description,
      monthly_price: record.monthly_price,
      commission_percent: record.commission_percent,
      features: record.features || [],
      is_active: record.is_active,
    })
    setModalOpen(true)
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      setSaving(true)
      if (editing) {
        await updatePlan(editing.id, values)
        message.success('Tarif yangilandi!')
      } else {
        await createPlan(values)
        message.success('Tarif qo\'shildi!')
      }
      setModalOpen(false)
      load()
    } catch (e) {
      if (e.response) message.error(e.response?.data?.detail || 'Xato')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id) => {
    try {
      await deletePlan(id)
      message.success('O\'chirildi')
      load()
    } catch (e) {
      message.error(e.response?.data?.detail || 'O\'chirishda xato')
    }
  }

  const columns = [
    {
      title: 'Tarif', dataIndex: 'name',
      render: (name, r) => (
        <Space>
          <CrownOutlined style={{ color: PLAN_COLORS[r.slug] === 'gold' ? '#faad14' : PLAN_COLORS[r.slug] === 'blue' ? '#1677ff' : '#999' }} />
          <b>{name}</b>
          <Text type="secondary" style={{ fontSize: 12 }}>{r.slug}</Text>
        </Space>
      )
    },
    {
      title: 'Oylik narx', dataIndex: 'monthly_price',
      render: (v) => v > 0 ? <b>{Number(v).toLocaleString()} so\'m</b> : <Tag color="green">Bepul</Tag>
    },
    {
      title: 'Komissiya', dataIndex: 'commission_percent',
      render: (v) => v > 0
        ? <Tag color="purple">{v}%</Tag>
        : <Tag color="green">Yo'q</Tag>
    },
    {
      title: 'Imkoniyatlar', dataIndex: 'features',
      render: (features) => (
        <Space wrap>
          {(features || []).slice(0, 3).map((f, i) => <Tag key={i}>{f}</Tag>)}
          {(features || []).length > 3 && <Text type="secondary">+{features.length - 3} ta</Text>}
        </Space>
      )
    },
    {
      title: 'Holat', dataIndex: 'is_active',
      render: (v) => <Tag color={v ? 'green' : 'red'}>{v ? 'Faol' : 'Nofaol'}</Tag>
    },
    {
      title: 'Amallar', width: 120, render: (_, r) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)} />
          <Popconfirm
            title="Tarifni o'chirish"
            description="Bu tarifni ishlatayotgan restoranlar bo'lsa o'chirib bo'lmaydi."
            onConfirm={() => handleDelete(r.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      )
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>Tariflar ({plans.length})</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}
          style={{ background: '#722ed1', borderColor: '#722ed1' }}>
          Yangi tarif
        </Button>
      </div>

      <Card>
        <Table
          dataSource={plans}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={false}
          scroll={{ x: 700 }}
        />
      </Card>

      <Modal
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleSave}
        confirmLoading={saving}
        title={editing ? 'Tarifni tahrirlash' : 'Yangi tarif'}
        okText="Saqlash"
        cancelText="Bekor"
        width={540}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="name" label="Tarif nomi"
            rules={[{ required: true, message: 'Nomini kiriting' }]}
          >
            <Input placeholder="Basic, Pro, Enterprise..." />
          </Form.Item>
          <Form.Item
            name="slug" label="Slug (unikal kalit)"
            rules={[
              { required: !editing, message: 'Slug kiriting' },
              { pattern: /^[a-z0-9\-]+$/, message: 'Faqat kichik harf va -' }
            ]}
            tooltip="Bir marta belgilanadi, o'zgartirilmaydi"
          >
            <Input placeholder="basic" disabled={!!editing} />
          </Form.Item>
          <Form.Item name="description" label="Tavsif">
            <TextArea rows={2} placeholder="Tarif haqida qisqacha..." />
          </Form.Item>
          <Space style={{ width: '100%' }} size={16}>
            <Form.Item
              name="monthly_price" label="Oylik narx (so'm)"
              rules={[{ type: 'number', min: 0 }]}
              style={{ flex: 1 }}
            >
              <InputNumber
                style={{ width: '100%' }} min={0} step={10000}
                formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ' ')}
                parser={(v) => parseInt(v.replace(/\s/g, '')) || 0}
              />
            </Form.Item>
            <Form.Item
              name="commission_percent" label="Komissiya (%)"
              rules={[{ type: 'number', min: 0, max: 100 }]}
              tooltip="Bu foiz shu tarifga biriktirilgan barcha restoranlar uchun avtomatik yangilanadi"
              style={{ flex: 1 }}
            >
              <InputNumber
                style={{ width: '100%' }} min={0} max={100} step={0.5}
                formatter={(v) => `${v}%`}
                parser={(v) => parseFloat(v.replace('%', '')) || 0}
              />
            </Form.Item>
          </Space>
          <Form.Item name="features" label="Imkoniyatlar">
            <FeaturesEditor />
          </Form.Item>
          <Form.Item name="is_active" label="Holat" valuePropName="checked">
            <Switch checkedChildren="Faol" unCheckedChildren="Nofaol" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
