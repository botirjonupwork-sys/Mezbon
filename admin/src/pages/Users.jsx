import { useEffect, useState } from 'react'
import { Table, Card, Typography, Input, message, Tag, Spin } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import { getUsers, getUserOrders } from '../api'
import { useBranchStore } from '../store/branch'
import { useAuthStore } from '../store/auth'

const { Title } = Typography

const statusColor = {
  pending: 'orange', confirmed: 'blue', preparing: 'geekblue',
  ready: 'cyan', delivering: 'purple', delivered: 'green', cancelled: 'red',
}
const statusText = {
  pending: 'Kutilmoqda', confirmed: 'Qabul', preparing: 'Tayyorlanmoqda',
  ready: 'Tayyor', delivering: "Yo'lda", delivered: 'Yetkazildi', cancelled: 'Bekor',
}

// Sub-jadval: buyurtma tarkibi
function OrderItemsTable({ items }) {
  const cols = [
    { title: 'Mahsulot', dataIndex: 'product_name' },
    { title: 'Miqdor', dataIndex: 'quantity', width: 80 },
    { title: 'Narx', dataIndex: 'price', render: (v) => `${(v || 0).toLocaleString()} so'm`, width: 140 },
    {
      title: 'Jami', width: 140,
      render: (_, r) => `${((r.price || 0) * (r.quantity || 1)).toLocaleString()} so'm`
    },
  ]
  return (
    <Table
      dataSource={items}
      columns={cols}
      rowKey={(r, i) => i}
      pagination={false}
      size="small"
      style={{ margin: '8px 0' }}
    />
  )
}

// Sub-jadval: foydalanuvchi zakazlari
function UserOrdersTable({ userId }) {
  const [orders, setOrders] = useState(null)

  useEffect(() => {
    getUserOrders(userId)
      .then((res) => setOrders(res.data || []))
      .catch(() => setOrders([]))
  }, [userId])

  if (orders === null) return <Spin style={{ padding: 24 }} />
  if (!orders.length) return <div style={{ padding: 16, color: '#999' }}>Zakazlar yo'q</div>

  const cols = [
    { title: '#', dataIndex: 'id', width: 70, render: (id) => `#${id}` },
    {
      title: 'Holat', dataIndex: 'status',
      render: (s) => <Tag color={statusColor[s]}>{statusText[s]}</Tag>
    },
    {
      title: 'Tur', dataIndex: 'delivery_type',
      render: (v) => v === 'delivery' ? '🚗 Dastavka' : '🏪 Saboy'
    },
    {
      title: 'Summa', dataIndex: 'total_price',
      render: (v) => `${(v || 0).toLocaleString()} so'm`
    },
    {
      title: 'Vaqt', dataIndex: 'created_at',
      render: (v) => v ? new Date(v).toLocaleString('uz') : '—'
    },
  ]

  return (
    <div style={{ padding: '0 16px 16px' }}>
      <Table
        dataSource={orders}
        columns={cols}
        rowKey="id"
        pagination={false}
        size="small"
        expandable={{
          expandedRowRender: (order) => <OrderItemsTable items={order.items || []} />,
          rowExpandable: (order) => (order.items?.length || 0) > 0,
        }}
      />
    </div>
  )
}

export default function Users() {
  const [users, setUsers] = useState([])
  const [filtered, setFiltered] = useState([])
  const [loading, setLoading] = useState(true)
  const [pageSize, setPageSize] = useState(10)
  const selectedBranchId = useBranchStore((s) => s.selectedBranchId)
  const restaurantId = useAuthStore((s) => s.restaurantId)

  useEffect(() => {
    setLoading(true)
    const params = {}
    if (restaurantId) params.restaurant_id = restaurantId
    if (selectedBranchId) params.branch_id = selectedBranchId
    getUsers(params)
      .then((res) => { setUsers(res.data || []); setFiltered(res.data || []) })
      .catch(() => message.error('Yuklashda xato'))
      .finally(() => setLoading(false))
  }, [selectedBranchId])

  const onSearch = (val) => {
    const q = val.toLowerCase()
    setFiltered(users.filter((u) =>
      u.full_name?.toLowerCase().includes(q) || u.phone?.includes(q)
    ))
  }

  const columns = [
    { title: '#', dataIndex: 'id', width: 60 },
    { title: 'Ism', dataIndex: 'full_name' },
    { title: 'Telefon', dataIndex: 'phone' },
    {
      title: 'Til', dataIndex: 'language', width: 80,
      render: (v) => v === 'uz' ? '🇺🇿 UZ' : '🇷🇺 RU'
    },
    {
      title: "Ro'yxat sanasi", dataIndex: 'created_at',
      render: (v) => v ? new Date(v).toLocaleDateString('uz') : '—'
    },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>Mijozlar</Title>
      <Card>
        <Input
          prefix={<SearchOutlined />}
          placeholder="Ism yoki telefon bo'yicha qidirish"
          onChange={(e) => onSearch(e.target.value)}
          style={{ maxWidth: 300, width: '100%', marginBottom: 16 }}
        />
        <Table
          dataSource={filtered}
          columns={columns}
          rowKey="id"
          loading={loading}
          scroll={{ x: 600 }}
          pagination={{
            pageSize,
            pageSizeOptions: ['10', '30', '50'],
            showSizeChanger: true,
            onShowSizeChange: (_, size) => setPageSize(size),
            showTotal: (total) => `Jami: ${total} ta`,
          }}
          expandable={{
            expandedRowRender: (user) => <UserOrdersTable userId={user.id} />,
            expandRowByClick: true,
          }}
        />
      </Card>
    </div>
  )
}
