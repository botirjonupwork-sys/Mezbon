import { useEffect, useState } from 'react'
import {
  Table, Tag, Button, Space, Typography, message, Popconfirm,
  Dropdown, Modal, Form, Input, Select
} from 'antd'
import {
  UserOutlined, MoreOutlined, EditOutlined,
  DeleteOutlined, StopOutlined, CheckOutlined
} from '@ant-design/icons'
import { getCouriers, updateCourierStatus, updateCourier, deleteCourier } from '../api'
import { useBranchStore } from '../store/branch'
import { useAuthStore } from '../store/auth'

const { Title } = Typography

const TRANSPORT = {
  car: '🚗 Avtomobil',
  motorcycle: '🏍 Motosikl',
  bicycle: '🚲 Velosiped',
  walk: '🚶 Piyoda',
}

const STATUS_TAG = {
  pending: <Tag color="orange">Kutilmoqda</Tag>,
  active: <Tag color="green">Faol</Tag>,
  blocked: <Tag color="red">Bloklangan</Tag>,
}

export default function Couriers() {
  const [couriers, setCouriers] = useState([])
  const [loading, setLoading] = useState(true)
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [editingCourier, setEditingCourier] = useState(null)
  const [form] = Form.useForm()
  const selectedBranchId = useBranchStore((s) => s.selectedBranchId)
  const restaurantId = useAuthStore((s) => s.restaurantId)

  const load = () => {
    setLoading(true)
    const params = {}
    if (restaurantId) params.restaurant_id = restaurantId
    if (selectedBranchId) params.branch_id = selectedBranchId
    getCouriers(params)
      .then((r) => setCouriers(r.data))
      .catch(() => message.error('Kuryer ma\'lumotlarini yuklashda xato'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [selectedBranchId])

  const handleStatus = async (id, status) => {
    try {
      await updateCourierStatus(id, status)
      message.success(
        status === 'active' ? 'Kuryer tasdiqlandi!'
        : status === 'blocked' ? 'Kuryer bloklandi!'
        : 'Holat yangilandi'
      )
      load()
    } catch {
      message.error('Xato!')
    }
  }

  const openEdit = (courier) => {
    setEditingCourier(courier)
    form.setFieldsValue({
      full_name: courier.full_name,
      phone: courier.phone,
      transport_type: courier.transport_type,
    })
    setEditModalOpen(true)
  }

  const handleSaveEdit = async () => {
    try {
      const values = await form.validateFields()
      await updateCourier(editingCourier.id, values)
      message.success('Yangilandi')
      setEditModalOpen(false)
      load()
    } catch (err) {
      if (err?.errorFields) return
      message.error('Saqlashda xato')
    }
  }

  const handleDelete = async (id) => {
    try {
      await deleteCourier(id)
      message.success("Kuryer o'chirildi")
      load()
    } catch {
      message.error("O'chirishda xato")
    }
  }

  const getActionItems = (record) => {
    const items = [
      {
        key: 'edit',
        icon: <EditOutlined />,
        label: 'Tahrirlash',
        onClick: () => openEdit(record),
      },
    ]

    if (record.status !== 'active') {
      items.push({
        key: 'approve',
        icon: <CheckOutlined />,
        label: 'Tasdiqlash',
        onClick: () => handleStatus(record.id, 'active'),
      })
    }
    if (record.status !== 'blocked') {
      items.push({
        key: 'block',
        icon: <StopOutlined />,
        label: 'Bloklash',
        danger: true,
        onClick: () => handleStatus(record.id, 'blocked'),
      })
    }
    if (record.status === 'blocked') {
      items.push({
        key: 'unblock',
        icon: <CheckOutlined />,
        label: 'Blokdan chiqarish',
        onClick: () => handleStatus(record.id, 'pending'),
      })
    }

    items.push({ type: 'divider' })
    items.push({
      key: 'delete',
      icon: <DeleteOutlined />,
      label: (
        <Popconfirm
          title="Kuryer o'chirilsinmi?"
          description="Bu amalni orqaga qaytarib bo'lmaydi."
          onConfirm={() => handleDelete(record.id)}
          okText="Ha, o'chirish"
          cancelText="Bekor"
          okButtonProps={{ danger: true }}
        >
          <span style={{ color: '#ff4d4f' }}>O'chirish</span>
        </Popconfirm>
      ),
      danger: true,
    })

    return items
  }

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    {
      title: 'Ism',
      dataIndex: 'full_name',
      render: (name) => <><UserOutlined /> {name}</>,
    },
    { title: 'Telefon', dataIndex: 'phone' },
    {
      title: 'Transport',
      dataIndex: 'transport_type',
      render: (t) => TRANSPORT[t] || t,
    },
    {
      title: 'Holat',
      dataIndex: 'status',
      render: (s) => STATUS_TAG[s] || s,
    },
    {
      title: 'Sana',
      dataIndex: 'created_at',
      render: (d) => d ? new Date(d).toLocaleDateString('uz') : '—',
    },
    {
      title: 'Amallar',
      width: 80,
      align: 'center',
      render: (_, record) => (
        <Dropdown
          menu={{ items: getActionItems(record) }}
          trigger={['click']}
          placement="bottomRight"
        >
          <Button type="text" icon={<MoreOutlined />} />
        </Dropdown>
      ),
    },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>🚗 Kuryerlar</Title>
      <Table
        columns={columns}
        dataSource={couriers}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 20 }}
        size="small"
        scroll={{ x: 700 }}
      />

      <Modal
        title="Kuryerni tahrirlash"
        open={editModalOpen}
        onOk={handleSaveEdit}
        onCancel={() => setEditModalOpen(false)}
        okText="Saqlash"
        cancelText="Bekor"
        okButtonProps={{ style: { background: '#fa8c16', borderColor: '#fa8c16' } }}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="full_name"
            label="To'liq ism"
            rules={[{ required: true, message: 'Ism kiriting' }]}
          >
            <Input placeholder="Ali Valiyev" />
          </Form.Item>
          <Form.Item
            name="phone"
            label="Telefon"
            rules={[{ required: true, message: 'Telefon kiriting' }]}
          >
            <Input placeholder="+998901234567" />
          </Form.Item>
          <Form.Item name="transport_type" label="Transport turi">
            <Select
              options={[
                { value: 'car', label: '🚗 Avtomobil' },
                { value: 'motorcycle', label: '🏍 Motosikl' },
                { value: 'bicycle', label: '🚲 Velosiped' },
                { value: 'walk', label: '🚶 Piyoda' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
