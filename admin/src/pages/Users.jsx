import { useEffect, useMemo, useState } from 'react'
import {
  Table, Card, Typography, Input, message, Tag, Spin, Modal,
  Space, Avatar, Button, Empty, Divider, Statistic, Row, Col,
} from 'antd'
import {
  SearchOutlined, UserOutlined, PhoneOutlined, ShoppingCartOutlined,
  HistoryOutlined, DollarOutlined, CalendarOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { getUsers, getUserOrders } from '../api'
import { fmtTashkent, fmtDateOnly } from '../utils/datetime'
import { useBranchStore } from '../store/branch'
import { useAuthStore } from '../store/auth'

const { Title, Text } = Typography

const STATUS_TAG = {
  pending:    { color: 'orange',   text: '⏳ Kutilmoqda' },
  confirmed:  { color: 'blue',     text: '✓ Qabul qilingan' },
  preparing:  { color: 'geekblue', text: "👨‍🍳 Tayyorlanmoqda" },
  ready:      { color: 'cyan',     text: '📦 Tayyor' },
  delivering: { color: 'purple',   text: "🚗 Yo'lda" },
  delivered:  { color: 'green',    text: '✅ Yetkazildi' },
  cancelled:  { color: 'red',      text: '❌ Bekor qilindi' },
}

function fmtUZS(v) {
  return new Intl.NumberFormat('uz-UZ').format(Math.round(v || 0))
}

// ── Mijoz buyurtmalari (modal ichida) ───────────────────────────────────

function UserOrdersModal({ user, open, onClose }) {
  const [orders, setOrders] = useState(null)

  useEffect(() => {
    if (!open || !user) { setOrders(null); return }
    getUserOrders(user.id)
      .then((r) => {
        // Yangidan eskiga tartibda
        const sorted = (r.data || []).slice().sort((a, b) =>
          new Date(b.created_at || 0) - new Date(a.created_at || 0))
        setOrders(sorted)
      })
      .catch(() => setOrders([]))
  }, [open, user])

  const stats = useMemo(() => {
    if (!orders) return null
    const delivered = orders.filter((o) => o.status === 'delivered')
    const totalSpent = delivered.reduce((s, o) => s + (o.total_price || 0), 0)
    const avgCheck = delivered.length ? totalSpent / delivered.length : 0
    return {
      total: orders.length,
      delivered: delivered.length,
      cancelled: orders.filter((o) => o.status === 'cancelled').length,
      totalSpent, avgCheck,
    }
  }, [orders])

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={760}
      title={
        <Space>
          <Avatar icon={<UserOutlined />} style={{ background: '#fa8c16' }} />
          <div>
            <div style={{ fontWeight: 600 }}>{user?.full_name}</div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              <PhoneOutlined /> {user?.phone || '—'} ·
              {' '}{user?.language === 'uz' ? '🇺🇿 UZ' : '🇷🇺 RU'} ·
              {user?.created_at ? ` ${fmtDateOnly(user.created_at)}` : ''}
            </Text>
          </div>
        </Space>
      }
    >
      {orders === null ? (
        <Spin size="large" style={{ display: 'block', margin: 40 }} />
      ) : orders.length === 0 ? (
        <Empty description="Bu mijoz hali zakaz bermagan" style={{ margin: 40 }} />
      ) : (
        <>
          <Row gutter={12} style={{ marginBottom: 16 }}>
            <Col xs={12} md={6}>
              <Card size="small">
                <Statistic title="Jami zakaz" value={stats.total}
                  prefix={<ShoppingCartOutlined />} />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card size="small">
                <Statistic title="Yetkazildi" value={stats.delivered}
                  valueStyle={{ color: '#52c41a' }} />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card size="small">
                <Statistic title="Bekor" value={stats.cancelled}
                  valueStyle={{ color: '#ff4d4f' }} />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card size="small">
                <Statistic title="O'rtacha chek" value={fmtUZS(stats.avgCheck)} suffix="so'm"
                  prefix={<DollarOutlined />} valueStyle={{ fontSize: 16 }} />
              </Card>
            </Col>
          </Row>

          <Divider orientation="left" style={{ margin: '8px 0' }}>
            <HistoryOutlined /> Zakazlar tarixi (yangidan eskiga)
          </Divider>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {orders.map((o) => {
              const st = STATUS_TAG[o.status] || { color: 'default', text: o.status }
              const totalSum = (o.total_price || 0) + (o.delivery_fee || 0)
              return (
                <Card key={o.id} size="small" hoverable>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                    <Space>
                      <Text strong style={{ fontSize: 15 }}>#{o.id}</Text>
                      <Tag color={st.color}>{st.text}</Tag>
                      <Tag>{o.delivery_type === 'delivery' ? '🚗 Dastavka' : '🏪 Saboy'}</Tag>
                    </Space>
                    <Space direction="vertical" size={0} align="end">
                      <Text strong style={{ fontSize: 16, color: '#fa8c16' }}>
                        {fmtUZS(totalSum)} so'm
                      </Text>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        <CalendarOutlined /> {fmtTashkent(o.created_at)}
                      </Text>
                    </Space>
                  </div>

                  {(o.items || []).length > 0 && (
                    <div style={{ background: '#fafafa', padding: 8, borderRadius: 4, fontSize: 13 }}>
                      {(o.items || []).map((it, i) => (
                        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
                          <span>
                            <Text>{it.product_name || `#${it.product_id}`}</Text>
                            <Text type="secondary"> × {it.quantity}</Text>
                          </span>
                          <Text>{fmtUZS((it.price || 0) * (it.quantity || 1))} so'm</Text>
                        </div>
                      ))}
                      {o.delivery_fee > 0 && (
                        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0 0', borderTop: '1px dashed #d9d9d9' }}>
                          <Text type="secondary">Yetkazib berish</Text>
                          <Text type="secondary">{fmtUZS(o.delivery_fee)} so'm</Text>
                        </div>
                      )}
                    </div>
                  )}
                  {o.address && (
                    <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 6 }}>
                      📍 {o.address}
                    </Text>
                  )}
                </Card>
              )
            })}
          </div>
        </>
      )}
    </Modal>
  )
}

// ── Mijozlar ro'yxati sahifasi ──────────────────────────────────────────

export default function Users() {
  const [users, setUsers] = useState([])
  const [filtered, setFiltered] = useState([])
  const [loading, setLoading] = useState(true)
  const [pageSize, setPageSize] = useState(20)
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState(null)
  const selectedBranchId = useBranchStore((s) => s.selectedBranchId)
  const restaurantId = useAuthStore((s) => s.currentRestaurantId)

  useEffect(() => {
    setLoading(true)
    const params = {}
    if (restaurantId) params.restaurant_id = restaurantId
    if (selectedBranchId) params.branch_id = selectedBranchId
    getUsers(params)
      .then((r) => {
        const list = r.data || []
        setUsers(list); setFiltered(list)
      })
      .catch(() => message.error('Yuklashda xato'))
      .finally(() => setLoading(false))
  }, [selectedBranchId, restaurantId])

  useEffect(() => {
    const q = search.trim().toLowerCase()
    if (!q) { setFiltered(users); return }
    setFiltered(users.filter((u) =>
      (u.full_name || '').toLowerCase().includes(q) ||
      (u.phone || '').includes(q) ||
      String(u.id).includes(q)
    ))
  }, [search, users])

  const columns = [
    { title: '#', dataIndex: 'id', width: 60 },
    {
      title: 'Mijoz',
      render: (_, u) => (
        <Space>
          <Avatar icon={<UserOutlined />} style={{ background: '#fa8c16' }} />
          <div>
            <div style={{ fontWeight: 600 }}>{u.full_name}</div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              <PhoneOutlined /> {u.phone || '—'}
            </Text>
          </div>
        </Space>
      ),
    },
    {
      title: 'Til', dataIndex: 'language', width: 80,
      render: (v) => v === 'uz' ? '🇺🇿 UZ' : '🇷🇺 RU',
    },
    {
      title: "Ro'yxatdan o'tdi", dataIndex: 'created_at', width: 160,
      render: (v) => fmtDateOnly(v),
      sorter: (a, b) => new Date(a.created_at || 0) - new Date(b.created_at || 0),
    },
    {
      title: 'Amal', width: 140,
      render: (_, u) => (
        <Button size="small" type="primary" ghost icon={<HistoryOutlined />}
          onClick={(e) => { e.stopPropagation(); setSelected(u) }}>
          Zakazlar
        </Button>
      ),
    },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>
        Mijozlar {filtered.length > 0 && <Text type="secondary" style={{ fontSize: 14 }}>({filtered.length})</Text>}
      </Title>
      <Card>
        <Input
          prefix={<SearchOutlined />}
          placeholder="Ism, telefon yoki ID bo'yicha qidirish..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          allowClear
          style={{ maxWidth: 320, marginBottom: 16 }}
        />
        <Table
          dataSource={filtered}
          columns={columns}
          rowKey="id"
          loading={loading}
          scroll={{ x: 600 }}
          onRow={(record) => ({
            onClick: () => setSelected(record),
            style: { cursor: 'pointer' },
          })}
          pagination={{
            pageSize,
            pageSizeOptions: ['10', '20', '50', '100'],
            showSizeChanger: true,
            onShowSizeChange: (_, size) => setPageSize(size),
            showTotal: (total) => `Jami: ${total} ta`,
          }}
        />
      </Card>

      <UserOrdersModal
        user={selected}
        open={!!selected}
        onClose={() => setSelected(null)}
      />
    </div>
  )
}
