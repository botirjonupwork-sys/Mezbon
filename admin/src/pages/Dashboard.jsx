import { useEffect, useState } from 'react'
import {
  Row, Col, Card, Statistic, Table, Tag, Typography, DatePicker, Space, Button
} from 'antd'
import {
  ShoppingCartOutlined, DollarOutlined, StarOutlined, UserOutlined, ReloadOutlined
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { getStats, getOrders, getReviewStats } from '../api'
import { useBranchStore } from '../store/branch'

const { Title } = Typography
const { RangePicker } = DatePicker

const statusColor = {
  pending:    'orange',
  confirmed:  'blue',
  preparing:  'geekblue',
  ready:      'cyan',
  delivering: 'purple',
  delivered:  'green',
  cancelled:  'red',
}
const statusText = {
  pending:    'Kutilmoqda',
  confirmed:  'Qabul qilindi',
  preparing:  'Tayyorlanmoqda',
  ready:      'Tayyor',
  delivering: "Yo'lda",
  delivered:  'Yetkazildi',
  cancelled:  'Bekor',
}

export default function Dashboard() {
  const [orders, setOrders] = useState([])
  const [stats, setStats] = useState({})
  const [reviewStats, setReviewStats] = useState({})
  const [loading, setLoading] = useState(true)
  const [dateRange, setDateRange] = useState([dayjs(), dayjs()])
  const selectedBranchId = useBranchStore((s) => s.selectedBranchId)

  const fetchAll = async (range) => {
    setLoading(true)
    const [from, to] = range || dateRange
    const params = {
      date_from: from.format('YYYY-MM-DD'),
      date_to: to.format('YYYY-MM-DD'),
    }
    if (selectedBranchId) params.branch_id = selectedBranchId
    try {
      const [statsRes, ordersRes, reviewRes] = await Promise.all([
        getStats(params),
        getOrders(params),
        getReviewStats(),
      ])
      setStats(statsRes.data || {})
      setOrders(ordersRes.data || [])
      setReviewStats(reviewRes.data || {})
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchAll(dateRange) }, [selectedBranchId])

  const handleRangeChange = (dates) => {
    if (dates && dates.length === 2) {
      setDateRange(dates)
      fetchAll(dates)
    }
  }

  const columns = [
    { title: '#', dataIndex: 'id', width: 60, render: (id) => `#${id}` },
    { title: 'Mijoz', dataIndex: ['user', 'full_name'], render: (v) => v || '—' },
    {
      title: 'Mahsulotlar',
      dataIndex: 'items',
      ellipsis: true,
      render: (items) =>
        items?.map((i) => `${i.product_name} x${i.quantity}`).join(', ') || '—',
    },
    { title: 'Summa', dataIndex: 'total_price', render: (v) => `${(v || 0).toLocaleString()} so'm` },
    {
      title: 'Tur', dataIndex: 'delivery_type',
      render: (v) => v === 'delivery' ? '🚗 Dastavka' : '🏪 Saboy'
    },
    {
      title: 'Holat', dataIndex: 'status',
      render: (s) => <Tag color={statusColor[s]}>{statusText[s]}</Tag>
    },
    {
      title: 'Vaqt', dataIndex: 'created_at',
      render: (v) => v ? new Date(v).toLocaleString('uz') : '—'
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24, flexWrap: 'wrap', gap: 12 }}>
        <Title level={4} style={{ margin: 0 }}>Dashboard</Title>
        <Space wrap>
          <RangePicker
            value={dateRange}
            onChange={handleRangeChange}
            format="DD.MM.YYYY"
            allowClear={false}
          />
          <Button icon={<ReloadOutlined />} onClick={() => fetchAll(dateRange)}>
            Yangilash
          </Button>
        </Space>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="Zakazlar soni"
              value={stats.today_orders ?? 0}
              prefix={<ShoppingCartOutlined style={{ color: '#fa8c16' }} />}
              valueStyle={{ color: '#fa8c16' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="Daromad"
              value={stats.today_revenue ?? 0}
              suffix="so'm"
              prefix={<DollarOutlined style={{ color: '#52c41a' }} />}
              valueStyle={{ color: '#52c41a' }}
              formatter={(v) => Number(v).toLocaleString()}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="Jami mijozlar"
              value={stats.total_users ?? 0}
              prefix={<UserOutlined style={{ color: '#1677ff' }} />}
              valueStyle={{ color: '#1677ff' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="O'rtacha reyting"
              value={reviewStats.average_rating || 0}
              prefix={<StarOutlined style={{ color: '#fadb14' }} />}
              suffix={`/ 5 (${reviewStats.total_reviews || 0} ta)`}
              valueStyle={{ color: '#fadb14' }}
            />
          </Card>
        </Col>
      </Row>

      <Card title="So'nggi zakazlar">
        <Table
          dataSource={orders}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{
            defaultPageSize: 10,
            showSizeChanger: true,
            pageSizeOptions: ['10', '20', '50'],
            showTotal: (total, range) => `${range[0]}-${range[1]} / ${total} ta`,
          }}
          size="small"
          scroll={{ x: 900 }}
        />
      </Card>
    </div>
  )
}
