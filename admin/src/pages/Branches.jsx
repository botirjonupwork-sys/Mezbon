import { useEffect, useState, useCallback } from 'react'
import {
  Card, Table, Button, Space, Typography, message, Modal, Form,
  Input, InputNumber, Tag, Alert, Popconfirm, Tooltip,
} from 'antd'
import {
  PlusOutlined, EditOutlined, EnvironmentOutlined, ReloadOutlined,
  ShopOutlined, ClockCircleOutlined, PhoneOutlined, DeleteOutlined,
} from '@ant-design/icons'
import {
  getAdminBranches, createAdminBranch, getBranchSettings, updateBranchSettings,
} from '../api'

const { Title, Text } = Typography

export default function Branches() {
  const [branches, setBranches] = useState([])
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState(null)
  const [createForm] = Form.useForm()
  const [editForm] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await getAdminBranches()
      setBranches(r.data || r || [])
    } catch (e) {
      message.error(e?.response?.data?.detail || 'Filiallarni yuklashda xato')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const onCreate = async () => {
    try {
      const v = await createForm.validateFields()
      const r = await createAdminBranch(v)
      message.success(`✅ Filial #${r.id} (${r.name}) yaratildi`)
      setCreating(false)
      createForm.resetFields()
      await load()
    } catch (e) {
      if (e?.errorFields) return
      const detail = e?.response?.data?.detail
      if (typeof detail === 'object' && detail?.code === 'branch_limit_reached') {
        Modal.warning({
          title: '⛔ Tarif chegarasi',
          content: detail.message,
        })
      } else {
        message.error(detail || 'Yaratishda xato')
      }
    }
  }

  const openEdit = async (record) => {
    setEditing(record)
    try {
      const r = await getBranchSettings(record.id)
      editForm.setFieldsValue(r.data || r || {})
    } catch (e) {
      editForm.setFieldsValue(record)
    }
  }

  const onEdit = async () => {
    try {
      const v = await editForm.validateFields()
      await updateBranchSettings(editing.id, v)
      message.success('✅ Filial yangilandi')
      setEditing(null)
      await load()
    } catch (e) {
      if (e?.errorFields) return
      message.error(e?.response?.data?.detail || 'Saqlashda xato')
    }
  }

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 60, render: id => <b>#{id}</b> },
    {
      title: 'Nom', dataIndex: 'name',
      render: (v, r) => (
        <Space>
          <ShopOutlined style={{ color: '#1890ff' }} />
          <b>{v}</b>
          {r.is_active === false && <Tag color="default">o'chirilgan</Tag>}
        </Space>
      ),
    },
    {
      title: 'Manzil', dataIndex: 'address',
      render: v => v ? (
        <Tooltip title={v}>
          <Text style={{ fontSize: 12 }}>
            <EnvironmentOutlined /> {v.length > 40 ? v.slice(0, 40) + '…' : v}
          </Text>
        </Tooltip>
      ) : '—',
    },
    {
      title: 'Telefon', dataIndex: 'phone', width: 150,
      render: v => v ? <a href={`tel:${v}`}><PhoneOutlined /> {v}</a> : '—',
    },
    {
      title: 'Ish vaqti', width: 120,
      render: (_, r) => (
        <Text style={{ fontSize: 12 }}>
          <ClockCircleOutlined /> {r.work_hours_from || '09:00'}–{r.work_hours_until || '22:00'}
        </Text>
      ),
    },
    {
      title: 'Min zakaz', dataIndex: 'min_order', width: 120, align: 'right',
      render: v => `${(v || 0).toLocaleString('uz')} so'm`,
    },
    {
      title: 'Holat', width: 80,
      render: (_, r) => r.is_open
        ? <Tag color="green">ochiq</Tag>
        : <Tag color="default">yopiq</Tag>,
    },
    {
      title: 'Amal', width: 100,
      render: (_, r) => (
        <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)}>
          Tahrir
        </Button>
      ),
    },
  ]

  return (
    <div>
      <Space style={{ marginBottom: 16, justifyContent: 'space-between', width: '100%' }}>
        <Title level={3} style={{ margin: 0 }}>
          <ShopOutlined /> Filiallar ({branches.length})
        </Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={load}>Yangilash</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreating(true)}>
            Yangi filial
          </Button>
        </Space>
      </Space>

      <Alert type="info" showIcon style={{ marginBottom: 16 }}
        message="Tarif chegarasi"
        description="Free tarif: 1 filial · Basic: 3 · Pro: 10. Ko'paytirish uchun tarifni ko'taring." />

      <Card>
        <Table
          rowKey="id" size="middle"
          loading={loading}
          dataSource={branches}
          columns={columns}
          pagination={false}
          locale={{ emptyText: 'Filial yo\'q. "Yangi filial" tugmasini bosing.' }}
        />
      </Card>

      {/* Yangi filial */}
      <Modal
        title={<><PlusOutlined /> Yangi filial</>}
        open={creating}
        onCancel={() => setCreating(false)}
        onOk={onCreate}
        okText="Yaratish"
        cancelText="Bekor"
        width={600}
        destroyOnClose
      >
        <Form form={createForm} layout="vertical"
          initialValues={{
            work_hours_from: '09:00', work_hours_until: '22:00',
            min_order: 30000, delivery_base_fee: 10000, delivery_per_km: 3000,
          }}>
          <Form.Item name="name" label="Filial nomi" rules={[{ required: true }]}>
            <Input placeholder="Chilonzor filiali" />
          </Form.Item>
          <Form.Item name="address" label="Manzil">
            <Input.TextArea rows={2} placeholder="Toshkent, Chilonzor 7-mavze, ..." />
          </Form.Item>
          <Form.Item name="phone" label="Telefon">
            <Input placeholder="+998901234567" />
          </Form.Item>
          <Space style={{ width: '100%' }} size="large">
            <Form.Item name="latitude" label="Kenglik (lat)" style={{ flex: 1, minWidth: 180 }}>
              <InputNumber style={{ width: '100%' }} placeholder="41.299" step={0.0001} />
            </Form.Item>
            <Form.Item name="longitude" label="Uzunlik (lon)" style={{ flex: 1, minWidth: 180 }}>
              <InputNumber style={{ width: '100%' }} placeholder="69.240" step={0.0001} />
            </Form.Item>
          </Space>
          <Space style={{ width: '100%' }} size="large">
            <Form.Item name="work_hours_from" label="Ish vaqti (boshlanish)" style={{ flex: 1, minWidth: 180 }}>
              <Input placeholder="09:00" />
            </Form.Item>
            <Form.Item name="work_hours_until" label="Ish vaqti (tugash)" style={{ flex: 1, minWidth: 180 }}>
              <Input placeholder="22:00" />
            </Form.Item>
          </Space>
          <Space style={{ width: '100%' }} size="large">
            <Form.Item name="min_order" label="Min zakaz (so'm)" style={{ flex: 1, minWidth: 150 }}>
              <InputNumber style={{ width: '100%' }} min={0} step={5000} />
            </Form.Item>
            <Form.Item name="delivery_base_fee" label="Dastavka boshlang'ich (so'm)" style={{ flex: 1, minWidth: 180 }}>
              <InputNumber style={{ width: '100%' }} min={0} step={1000} />
            </Form.Item>
            <Form.Item name="delivery_per_km" label="km uchun (so'm)" style={{ flex: 1, minWidth: 150 }}>
              <InputNumber style={{ width: '100%' }} min={0} step={500} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>

      {/* Tahrir */}
      <Modal
        title={<><EditOutlined /> Filial tahrir — {editing?.name}</>}
        open={!!editing}
        onCancel={() => setEditing(null)}
        onOk={onEdit}
        okText="Saqlash"
        cancelText="Bekor"
        width={600}
        destroyOnClose
      >
        <Form form={editForm} layout="vertical">
          <Form.Item name="name" label="Filial nomi" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="address" label="Manzil">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="phone" label="Telefon">
            <Input />
          </Form.Item>
          <Space style={{ width: '100%' }} size="large">
            <Form.Item name="work_hours_from" label="Ish (boshlanish)" style={{ flex: 1, minWidth: 180 }}>
              <Input />
            </Form.Item>
            <Form.Item name="work_hours_until" label="Ish (tugash)" style={{ flex: 1, minWidth: 180 }}>
              <Input />
            </Form.Item>
          </Space>
          <Space style={{ width: '100%' }} size="large">
            <Form.Item name="min_order" label="Min zakaz" style={{ flex: 1, minWidth: 150 }}>
              <InputNumber style={{ width: '100%' }} min={0} step={5000} />
            </Form.Item>
            <Form.Item name="delivery_base_fee" label="Dastavka base" style={{ flex: 1, minWidth: 180 }}>
              <InputNumber style={{ width: '100%' }} min={0} step={1000} />
            </Form.Item>
            <Form.Item name="delivery_per_km" label="km" style={{ flex: 1, minWidth: 150 }}>
              <InputNumber style={{ width: '100%' }} min={0} step={500} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  )
}
