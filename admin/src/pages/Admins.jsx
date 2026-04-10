import { useEffect, useState } from 'react'
import {
  Table, Card, Typography, Button, Modal, Form,
  Input, Popconfirm, message, Tag, Space, Alert
} from 'antd'
import { PlusOutlined, DeleteOutlined, LockOutlined, UserOutlined } from '@ant-design/icons'
import { getAdmins, createAdmin, deleteAdmin } from '../api'
import { useAuthStore } from '../store/auth'

const { Title } = Typography

export default function Admins() {
  const [admins, setAdmins] = useState([])
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()
  const restaurantId = useAuthStore((s) => s.restaurantId)

  const fetchAdmins = () => {
    setLoading(true)
    const params = {}
    if (restaurantId) params.restaurant_id = restaurantId
    getAdmins(params)
      .then((res) => setAdmins(res.data || []))
      .catch(() => message.error('Yuklashda xato'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchAdmins() }, [])

  // Admin qo'shilgan kundan buyon necha kun o'tganini hisoblaymiz
  const getDaysSince = (dateStr) => {
    if (!dateStr) return 0
    const diff = Date.now() - new Date(dateStr).getTime()
    return Math.floor(diff / (1000 * 60 * 60 * 24))
  }

  const handleAdd = async () => {
    setSaving(true)
    try {
      const values = await form.validateFields()
      const qParams = restaurantId ? { restaurant_id: restaurantId } : {}
      await createAdmin(values, qParams)
      message.success("Admin qo'shildi")
      form.resetFields()
      setModalOpen(false)
      fetchAdmins()
    } catch (err) {
      if (!err?.errorFields) message.error("Qo'shishda xato: foydalanuvchi allaqachon mavjud bo'lishi mumkin")
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id) => {
    try {
      await deleteAdmin(id)
      message.success("Admin o'chirildi")
      fetchAdmins()
    } catch {
      message.error("O'chirishda xato")
    }
  }

  const columns = [
    { title: '#', dataIndex: 'id', width: 60 },
    {
      title: 'Username', dataIndex: 'username',
      render: (v) => <Space><UserOutlined /><b>{v}</b></Space>
    },
    {
      title: "Qo'shilgan sana", dataIndex: 'created_at',
      render: (v) => v ? new Date(v).toLocaleDateString('uz') : '—'
    },
    {
      title: 'Huquqlar', dataIndex: 'created_at',
      render: (v) => {
        const days = getDaysSince(v)
        return days >= 10
          ? <Tag color="green">✅ To'liq huquq (CRUD)</Tag>
          : <Tag color="orange">⏳ {10 - days} kun qoldi (faqat ko'rish)</Tag>
      }
    },
    {
      title: 'Amallar', width: 100,
      render: (_, record) => (
        <Popconfirm
          title="Bu adminni o'chirishni xohlaysizmi?"
          onConfirm={() => handleDelete(record.id)}
          okText="Ha" cancelText="Yo'q"
          okButtonProps={{ danger: true }}
        >
          <Button size="small" danger icon={<DeleteOutlined />}>
            O'chirish
          </Button>
        </Popconfirm>
      )
    },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>Adminlar</Title>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="Huquqlar haqida"
        description="Yangi adminlar qo'shilgan kundan boshlab 10 kun davomida faqat ma'lumotlarni ko'rish huquqiga ega. 10 kundan so'ng to'liq CRUD huquqlari beriladi. Yangi adminlar eski foydalanuvchilarni o'chira olmaydi."
      />

      <Card
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => { form.resetFields(); setModalOpen(true) }}
            style={{ background: '#fa8c16', borderColor: '#fa8c16' }}
          >
            Admin qo'shish
          </Button>
        }
      >
        <Table
          dataSource={admins}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 20 }}
          scroll={{ x: 600 }}
        />
      </Card>

      <Modal
        title="Yangi admin qo'shish"
        open={modalOpen}
        onOk={handleAdd}
        onCancel={() => setModalOpen(false)}
        okText="Qo'shish"
        cancelText="Bekor"
        confirmLoading={saving}
        okButtonProps={{ style: { background: '#fa8c16', borderColor: '#fa8c16' } }}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="username"
            label="Username"
            rules={[
              { required: true, message: 'Username kiriting' },
              { min: 4, message: "Kamida 4 ta belgi bo'lishi kerak" },
              { pattern: /^[a-z0-9_]+$/, message: 'Faqat lotin harflari, raqamlar va _' }
            ]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder="admin_user"
              autoComplete="off"
            />
          </Form.Item>

          <Form.Item
            name="password"
            label="Parol"
            rules={[
              { required: true, message: 'Parol kiriting' },
              { min: 6, message: "Kamida 6 ta belgi" }
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="••••••"
              autoComplete="new-password"
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
