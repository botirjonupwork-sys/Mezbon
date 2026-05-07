import { useEffect, useState, useMemo, useCallback } from 'react'
import {
  Calendar, Card, Tag, Typography, Row, Col, Table, Badge, Space,
  Button, Empty, message, DatePicker, Statistic,
} from 'antd'
import {
  GiftOutlined, ReloadOutlined, CalendarOutlined,
  ShopOutlined, PhoneOutlined, EnvironmentOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { getCateringOrders } from '../api'
import { fmtTashkent, fmtTimeOnly } from '../utils/datetime'
import { useBranchStore } from '../store/branch'

const { Title, Text } = Typography

const STATUS_TAG = {
  pending:    { color: 'orange',  label: '⏳ Kutilmoqda' },
  confirmed:  { color: 'blue',    label: '✅ Qabul qilingan' },
  preparing:  { color: 'cyan',    label: '👨‍🍳 Tayyorlanmoqda' },
  ready:      { color: 'green',   label: '📦 Tayyor' },
  delivering: { color: 'geekblue',label: '🚗 Yo\'lda' },
  delivered:  { color: 'success', label: '✅ Yetkazildi' },
  cancelled:  { color: 'default', label: '❌ Bekor' },
}

const SUBTYPE_LABEL = {
  onsite:   '🏠 Joyiga borib yopish',
  pickup:   '🛍 Olib ketish',
  delivery: '🚗 Dastavka',
}

function fmtUZS(v) { return new Intl.NumberFormat('uz-UZ').format(Math.round(v || 0)) }

export default function Catering() {
  const selectedBranchId = useBranchStore(s => s.selectedBranchId)
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(false)
  const [selectedDate, setSelectedDate] = useState(dayjs())

  const fetchOrders = useCallback(async () => {
    setLoading(true)
    try {
      // Oxirgi 60 kun + kelajak 60 kun
      const params = {
        date_from: dayjs().subtract(60, 'day').format('YYYY-MM-DD'),
        date_to: dayjs().add(60, 'day').format('YYYY-MM-DD'),
      }
      if (selectedBranchId) params.branch_id = selectedBranchId
      const res = await getCateringOrders(params)
      setOrders(Array.isArray(res) ? res : (res?.items || []))
    } catch (e) {
      message.error('Catering buyurtmalarini yuklashda xato')
    } finally {
      setLoading(false)
    }
  }, [selectedBranchId])

  useEffect(() => { fetchOrders() }, [fetchOrders])

  // Sana bo'yicha gruppalash
  const ordersByDate = useMemo(() => {
    const map = {}
    for (const o of orders) {
      const d = o.event_date || o.schedule_date || o.created_at
      if (!d) continue
      const key = dayjs.utc(d).tz('Asia/Tashkent').format('YYYY-MM-DD')
      if (!map[key]) map[key] = []
      map[key].push(o)
    }
    return map
  }, [orders])

  // Kelajakdagi buyurtmalar
  const upcoming = useMemo(() => {
    const today = dayjs().startOf('day')
    return orders.filter(o => {
      const d = o.event_date || o.schedule_date
      if (!d) return false
      return dayjs.utc(d).tz('Asia/Tashkent').isAfter(today.subtract(1, 'second'))
    }).sort((a, b) => {
      const da = dayjs.utc(a.event_date || a.schedule_date)
      const db = dayjs.utc(b.event_date || b.schedule_date)
      return da.diff(db)
    })
  }, [orders])

  const stats = useMemo(() => {
    const today = dayjs().format('YYYY-MM-DD')
    const tomorrow = dayjs().add(1, 'day').format('YYYY-MM-DD')
    return {
      todayCount: (ordersByDate[today] || []).length,
      tomorrowCount: (ordersByDate[tomorrow] || []).length,
      upcomingCount: upcoming.length,
      totalRevenue: orders.reduce((s, o) => s + (o.total_price || 0), 0),
    }
  }, [orders, ordersByDate, upcoming])

  const dateCellRender = (value) => {
    const key = value.format('YYYY-MM-DD')
    const list = ordersByDate[key] || []
    if (list.length === 0) return null
    const total = list.length
    const cancelled = list.filter(o => o.status === 'cancelled').length
    const active = total - cancelled
    return (
      <div style={{ textAlign: 'center' }}>
        {active > 0 && <Badge count={active} style={{ backgroundColor: '#52c41a' }} />}
        {cancelled > 0 && <Badge count={cancelled} style={{ backgroundColor: '#bfbfbf', marginLeft: 4 }} />}
      </div>
    )
  }

  const monthCellRender = (value) => {
    const monthStart = value.format('YYYY-MM')
    const list = orders.filter(o => {
      const d = o.event_date || o.schedule_date
      if (!d) return false
      return dayjs.utc(d).tz('Asia/Tashkent').format('YYYY-MM') === monthStart
    })
    if (list.length === 0) return null
    return <div style={{ textAlign: 'center' }}><Badge count={list.length} style={{ backgroundColor: '#1890ff' }} /></div>
  }

  const selectedKey = selectedDate.format('YYYY-MM-DD')
  const dayList = ordersByDate[selectedKey] || []

  const dayColumns = [
    { title: '#', dataIndex: 'id', width: 60, render: id => <b>#{id}</b> },
    {
      title: 'Vaqt', dataIndex: 'schedule_time', width: 80,
      render: (v, r) => v || (r.event_date ? fmtTimeOnly(r.event_date) : '—'),
    },
    {
      title: 'Mijoz', dataIndex: 'user', width: 200,
      render: (u, r) => (
        <div>
          <div><b>{u?.full_name || '—'}</b></div>
          <div style={{ fontSize: 12, color: '#666' }}>
            <PhoneOutlined /> <a href={`tel:${u?.phone}`}>{u?.phone || '—'}</a>
          </div>
        </div>
      ),
    },
    {
      title: 'Turi', dataIndex: 'delivery_subtype', width: 180,
      render: v => SUBTYPE_LABEL[v] || v || '—',
    },
    {
      title: 'Manzil', dataIndex: 'address',
      render: (v, r) => v ? (
        <Space>
          <EnvironmentOutlined />
          <Text style={{ fontSize: 12 }}>{v}</Text>
        </Space>
      ) : '—',
    },
    {
      title: 'Summa', dataIndex: 'total_price', width: 120, align: 'right',
      render: v => <b>{fmtUZS(v)} so'm</b>,
    },
    {
      title: 'Holat', dataIndex: 'status', width: 130,
      render: s => {
        const t = STATUS_TAG[s] || { color: 'default', label: s }
        return <Tag color={t.color}>{t.label}</Tag>
      },
    },
    {
      title: 'To\'lov', dataIndex: 'payment_status', width: 110,
      render: ps => {
        const map = { paid: 'green', partial: 'gold', refunded: 'red', cancelled: 'default', pending: 'orange' }
        return <Tag color={map[ps] || 'default'}>{ps || '—'}</Tag>
      },
    },
  ]

  return (
    <div>
      <Space style={{ marginBottom: 16, justifyContent: 'space-between', width: '100%' }}>
        <Title level={3} style={{ margin: 0 }}>
          <GiftOutlined /> Catering buyurtmalari
        </Title>
        <Button icon={<ReloadOutlined />} onClick={fetchOrders}>Yangilash</Button>
      </Space>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}>
          <Card><Statistic title="📅 Bugun" value={stats.todayCount} prefix={<CalendarOutlined />} /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card><Statistic title="📅 Ertaga" value={stats.tomorrowCount} valueStyle={{ color: '#fa8c16' }} /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card><Statistic title="🗓 Kelajakdagi" value={stats.upcomingCount} valueStyle={{ color: '#1890ff' }} /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="💰 Jami summa" value={stats.totalRevenue} formatter={fmtUZS} suffix="so'm" />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <Card title="📅 Kalendar" loading={loading}>
            <Calendar
              fullscreen={false}
              value={selectedDate}
              onSelect={setSelectedDate}
              cellRender={(current, info) => {
                if (info.type === 'date') return dateCellRender(current)
                if (info.type === 'month') return monthCellRender(current)
                return info.originNode
              }}
            />
            <div style={{ marginTop: 8, fontSize: 12, color: '#666' }}>
              <Badge count={1} style={{ backgroundColor: '#52c41a' }} /> faol &nbsp;
              <Badge count={1} style={{ backgroundColor: '#bfbfbf', marginLeft: 8 }} /> bekor
            </div>
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          <Card title={
            <Space>
              <CalendarOutlined />
              <span>{selectedDate.format('DD.MM.YYYY (dddd)')}</span>
              <Tag color="blue">{dayList.length} ta buyurtma</Tag>
            </Space>
          }>
            {dayList.length === 0 ? (
              <Empty description="Bu sanada catering yo'q" />
            ) : (
              <Space direction="vertical" style={{ width: '100%' }}>
                {dayList.map(o => (
                  <Card key={o.id} size="small" style={{ background: o.status === 'cancelled' ? '#fafafa' : '#fff' }}>
                    <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                      <div>
                        <b>#{o.id}</b> — {o.schedule_time || '—'}<br/>
                        <Text style={{ fontSize: 12 }}>{o.user?.full_name || '—'} · {o.user?.phone || ''}</Text><br/>
                        <Tag>{SUBTYPE_LABEL[o.delivery_subtype] || '—'}</Tag>
                        <Tag color={STATUS_TAG[o.status]?.color}>{STATUS_TAG[o.status]?.label}</Tag>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <b>{fmtUZS(o.total_price)} so'm</b>
                      </div>
                    </Space>
                  </Card>
                ))}
              </Space>
            )}
          </Card>
        </Col>
      </Row>

      <Card title={`🗓 Kelgusi catering (${upcoming.length})`} style={{ marginTop: 16 }}>
        <Table
          rowKey="id" size="small"
          loading={loading}
          dataSource={upcoming.slice(0, 50)}
          columns={[
            {
              title: 'Sana', dataIndex: 'event_date', width: 110,
              render: (v, r) => fmtTashkent(v || r.schedule_date, 'DD.MM.YYYY'),
            },
            ...dayColumns,
          ]}
          pagination={{ pageSize: 20 }}
          locale={{ emptyText: 'Kelgusi catering yo\'q' }}
        />
      </Card>
    </div>
  )
}
