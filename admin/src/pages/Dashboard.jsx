import { useEffect, useState, useMemo, useCallback } from 'react'
import {
  Row, Col, Card, Statistic, Tag, Typography, Space, Button,
  Empty, Tooltip, message, Popconfirm, Badge, Segmented,
} from 'antd'
import {
  ShoppingCartOutlined, ClockCircleOutlined, ReloadOutlined,
  FireOutlined, CheckCircleOutlined, CloseCircleOutlined,
  PhoneOutlined, EnvironmentOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { getStats, getOrders, updateOrderStatus } from '../api'
import { fmtTashkent } from '../utils/datetime'
import { useBranchStore } from '../store/branch'
import { useAuthStore } from '../store/auth'

const { Title, Text } = Typography

const STATUS_COLOR = {
  pending:    'orange',
  confirmed:  'blue',
  preparing:  'geekblue',
  ready:      'cyan',
  delivering: 'purple',
  delivered:  'green',
  cancelled:  'red',
}
const STATUS_TEXT = {
  pending:    'Yangi',
  confirmed:  'Qabul qilingan',
  preparing:  'Tayyorlanmoqda',
  ready:      'Tayyor',
  delivering: "Yo'lda",
  delivered:  'Yetkazildi',
  cancelled:  'Bekor',
}

// Keyingi status — har bir bosqichdan keyin nima
const NEXT_STATUS = {
  pending:    { next: 'confirmed',  label: 'Qabul qilish' },
  confirmed:  { next: 'preparing',  label: 'Tayyorlashni boshlash' },
  preparing:  { next: 'ready',      label: 'Tayyor' },
  ready:      { next: 'delivering', label: "Yo'lga jo'natish" },  // delivery
  delivering: { next: 'delivered',  label: 'Yetkazildi' },
}

const ACTIVE_STATUSES = ['pending', 'confirmed', 'preparing', 'ready', 'delivering']

// Vaqt asosida shoshilinch darajasi (daqiqa)
const URGENCY_GREEN  = 10
const URGENCY_YELLOW = 25

function getUrgencyColor(createdAt) {
  // created_at UTC (Z yoki naive) — local deb o'qimaslik
  const m = dayjs().diff(dayjs.utc(createdAt), 'minute')
  if (m <= URGENCY_GREEN)  return '#52c41a'  // yashil — yangi
  if (m <= URGENCY_YELLOW) return '#faad14'  // sariq — diqqat
  return '#f5222d'                            // qizil — shoshilinch
}

function formatElapsed(createdAt) {
  const m = dayjs().diff(dayjs.utc(createdAt), 'minute')
  if (m < 1)  return 'hozir'
  if (m < 60) return `${m} daq`
  const h = Math.floor(m / 60)
  const rem = m % 60
  return rem ? `${h} soat ${rem} daq` : `${h} soat`
}

function getOrderFlowType(order) {
  if (order?.order_kind === 'catering' && order.delivery_subtype) return order.delivery_subtype
  return order?.delivery_type === 'delivery' ? 'delivery' : 'pickup'
}

function getOrderTypeLabel(order) {
  const type = getOrderFlowType(order)
  if (type === 'onsite') return '🏠 Borib yopib berish'
  if (type === 'delivery') return '🚗 Dastavka'
  return '🏪 Saboy'
}

function getStatusLabel(order) {
  const type = getOrderFlowType(order)
  if (type === 'delivery' && order.status === 'delivering') return 'Kuryerga berildi'
  if (type === 'pickup' && order.status === 'ready') return 'Zakaz tayyor'
  if (type === 'onsite' && order.status === 'confirmed') return 'Zakaz qabul qilindi'
  return STATUS_TEXT[order.status] || order.status
}

function isOperationallyActive(order) {
  if (!ACTIVE_STATUSES.includes(order.status)) return false
  if (getOrderFlowType(order) === 'onsite' && order.status !== 'pending') return false
  return true
}

function operationalSortValue(order) {
  if (order?.order_kind === 'catering' && order.schedule_date) {
    return dayjs(`${order.schedule_date} ${order.schedule_time || '00:00'}`, 'YYYY-MM-DD HH:mm').valueOf()
  }
  return dayjs.utc(order.created_at).valueOf()
}

export default function Dashboard() {
  const [orders, setOrders] = useState([])
  const [stats, setStats] = useState({})
  const [loading, setLoading] = useState(true)
  const [advancingId, setAdvancingId] = useState(null)
  const [queueTab, setQueueTab] = useState('outgoing')
  const [tick, setTick] = useState(0)  // elapsed timer'ni real vaqtda yangilash
  const selectedBranchId = useBranchStore((s) => s.selectedBranchId)
  const restaurantId = useAuthStore((s) => s.currentRestaurantId)

  const fetchAll = useCallback(async () => {
    setLoading(true)
    const today = dayjs().format('YYYY-MM-DD')
    const params = { date_from: today, date_to: today, operational_date: true }
    if (restaurantId) params.restaurant_id = restaurantId
    if (selectedBranchId) params.branch_id = selectedBranchId
    try {
      const [statsRes, ordersRes] = await Promise.all([
        getStats(params),
        getOrders(params),
      ])
      setStats(statsRes.data || {})
      setOrders(ordersRes.data || [])
    } catch {
      // silent — auto-refresh shovqin qilmasin
    } finally {
      setLoading(false)
    }
  }, [restaurantId, selectedBranchId])

  // Boshlanish va branch o'zgarganda yuklash
  useEffect(() => { fetchAll() }, [fetchAll])

  // Auto-refresh — har 30 sek
  useEffect(() => {
    const t = setInterval(fetchAll, 30_000)
    return () => clearInterval(t)
  }, [fetchAll])

  // Vaqt hisoblagichi — har 30 sek yangilash (renderni majburlash)
  useEffect(() => {
    const t = setInterval(() => setTick((x) => x + 1), 30_000)
    return () => clearInterval(t)
  }, [])

  // FIFO navbat — birinchi kelgan birinchi xizmat ko'rsatiladi
  const activeQueue = useMemo(() => {
    return (orders || [])
      .filter(isOperationallyActive)
      .filter((o) => {
        const type = getOrderFlowType(o)
        return queueTab === 'onsite' ? type === 'onsite' : type !== 'onsite'
      })
      .sort((a, b) => operationalSortValue(a) - operationalSortValue(b))
  }, [orders, tick, queueTab])

  const onsiteCount = useMemo(
    () => (orders || []).filter((o) => isOperationallyActive(o) && getOrderFlowType(o) === 'onsite').length,
    [orders],
  )
  const outgoingCount = useMemo(
    () => (orders || []).filter((o) => isOperationallyActive(o) && getOrderFlowType(o) !== 'onsite').length,
    [orders],
  )

  const doneToday      = orders.filter((o) => o.status === 'delivered').length
  const cancelledToday = orders.filter((o) => o.status === 'cancelled').length

  // Shoshilinch (25+ daqiqa) zakazlar soni
  const urgentCount = useMemo(() => {
    return activeQueue.filter(
      (o) => dayjs().diff(dayjs.utc(o.created_at), 'minute') > URGENCY_YELLOW
    ).length
  }, [activeQueue, tick])

  // Zakaz turiga qarab status oqimi.
  const computeNextStatus = (order) => {
    const type = getOrderFlowType(order)

    if (type === 'onsite') {
      if (order.status === 'pending') return { next: 'confirmed', label: 'Zakaz qabul qilindi' }
      return null
    }

    if (type === 'pickup') {
      if (['pending', 'confirmed', 'preparing'].includes(order.status)) {
        return { next: 'ready', label: 'Zakaz tayyor' }
      }
      if (order.status === 'ready') return { next: 'delivered', label: 'Mijozga berildi' }
      return null
    }

    if (type === 'delivery') {
      if (order.status === 'pending') return { next: 'confirmed', label: 'Qabul qilish' }
      if (order.status === 'confirmed') return { next: 'preparing', label: 'Tayyorlashni boshlash' }
      if (order.status === 'preparing') return { next: 'ready', label: 'Zakaz tayyor' }
      if (order.status === 'ready') return { next: 'delivering', label: 'Kuryerga berildi' }
      if (order.status === 'delivering') return { next: 'delivered', label: 'Yetkazildi' }
    }

    return NEXT_STATUS[order.status] || null
  }

  const advanceStatus = async (order) => {
    const cfg = computeNextStatus(order)
    if (!cfg) return
    setAdvancingId(order.id)
    try {
      await updateOrderStatus(order.id, cfg.next)
      message.success(`#${order.id} → ${cfg.label}`)
      await fetchAll()
    } catch (e) {
      message.error(e?.response?.data?.detail || "Holatni o'zgartirib bo'lmadi")
    } finally {
      setAdvancingId(null)
    }
  }

  const cancelOrder = async (order) => {
    setAdvancingId(order.id)
    try {
      await updateOrderStatus(order.id, 'cancelled')
      message.success(`#${order.id} bekor qilindi`)
      await fetchAll()
    } catch (e) {
      message.error(e?.response?.data?.detail || "Bekor qilib bo'lmadi")
    } finally {
      setAdvancingId(null)
    }
  }

  return (
    <div>
      {/* Sarlavha */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: 16, flexWrap: 'wrap', gap: 12,
      }}>
        <Title level={4} style={{ margin: 0 }}>
          📋 Bugungi kun · {dayjs().format('DD.MM.YYYY')}
        </Title>
        <Space>
          <Text type="secondary" style={{ fontSize: 12 }}>
            Avtomatik yangilash · har 30 sek
          </Text>
          <Button icon={<ReloadOutlined />} onClick={fetchAll} loading={loading}>
            Yangilash
          </Button>
        </Space>
      </div>

      {/* Yuqori statistika — operatsion */}
      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={8} lg={6}>
          <Card size="small">
            <Statistic
              title="🔥 Faol navbat"
              value={activeQueue.length}
              valueStyle={{ color: activeQueue.length > 0 ? '#fa541c' : '#999', fontSize: 28 }}
              prefix={<FireOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} lg={6}>
          <Card size="small">
            <Statistic
              title="⚠️ Shoshilinch (25+ daq)"
              value={urgentCount}
              valueStyle={{ color: urgentCount > 0 ? '#f5222d' : '#52c41a', fontSize: 28 }}
              prefix={<ClockCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} lg={6}>
          <Card size="small">
            <Statistic
              title="✅ Yetkazildi (bugun)"
              value={doneToday}
              valueStyle={{ color: '#52c41a', fontSize: 28 }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} lg={6}>
          <Card size="small">
            <Statistic
              title="💰 Daromad (bugun)"
              value={stats.today_revenue ?? 0}
              suffix="so'm"
              valueStyle={{ color: '#1677ff', fontSize: 22 }}
              formatter={(v) => Number(v).toLocaleString()}
            />
          </Card>
        </Col>
      </Row>

      {/* Asosiy ish navbati */}
      <Card
        title={
          <Space>
            <FireOutlined style={{ color: '#fa541c' }} />
            <span>Bugungi navbat</span>
            <Badge count={activeQueue.length} style={{ backgroundColor: '#fa541c' }} showZero />
          </Space>
        }
        extra={
          <Segmented
            size="small"
            value={queueTab}
            onChange={setQueueTab}
            options={[
              { label: `Kafedan chiqadi (${outgoingCount})`, value: 'outgoing' },
              { label: `Borib yopib berish (${onsiteCount})`, value: 'onsite' },
            ]}
          />
        }
        loading={loading && activeQueue.length === 0}
        bodyStyle={{ padding: activeQueue.length === 0 ? 24 : 0 }}
      >
        {activeQueue.length === 0 ? (
          <Empty description="Faol zakaz yo'q. Hammasi yetkazib bo'lingan 🎉" />
        ) : (
          <div>
            {activeQueue.map((order, idx) => {
              const urgency = getUrgencyColor(order.created_at)
              const elapsed = formatElapsed(order.created_at)
              const nextCfg = computeNextStatus(order)
              const userName  = order.user?.full_name || '—'
              const userPhone = order.user?.phone
              const itemsText = (order.items || [])
                .map((i) => `${i.product_name} ×${i.quantity}`)
                .join(', ')
              const flowType = getOrderFlowType(order)
              const isDelivery = flowType === 'delivery'
              const isCatering = order.order_kind === 'catering'
              const mainTime = isCatering
                ? (order.schedule_time || '—')
                : formatElapsed(order.created_at)
              const subTime = isCatering
                ? (order.schedule_date || '—')
                : fmtTashkent(order.created_at, 'HH:mm')

              return (
                <div
                  key={order.id}
                  style={{
                    borderLeft: `6px solid ${urgency}`,
                    padding: '12px 16px',
                    borderBottom: '1px solid #f0f0f0',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 16,
                    flexWrap: 'wrap',
                    background: idx === 0 ? '#fffbe6' : '#fff',
                  }}
                >
                  {/* Navbat raqami */}
                  <div style={{ minWidth: 56, textAlign: 'center' }}>
                    <div style={{
                      fontSize: 26, fontWeight: 700,
                      color: idx === 0 ? '#fa541c' : '#1677ff',
                      lineHeight: 1,
                    }}>
                      #{idx + 1}
                    </div>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {idx === 0 ? "birinchi" : "navbat"}
                    </Text>
                  </div>

                  {/* Vaqt */}
                  <div style={{ minWidth: 90, textAlign: 'center' }}>
                    <div style={{ fontSize: 15, fontWeight: 700, color: urgency }}>
                      ⏱ {mainTime}
                    </div>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {subTime}
                    </Text>
                  </div>

                  {/* Asosiy ma'lumot */}
                  <div style={{ flex: '1 1 260px', minWidth: 240 }}>
                    <Space size={6} wrap>
                      <Text strong style={{ fontSize: 15 }}>#{order.id}</Text>
                      <Tag color={STATUS_COLOR[order.status]} style={{ margin: 0 }}>
                        {getStatusLabel(order)}
                      </Tag>
                      <Tag color={flowType === 'delivery' ? 'purple' : flowType === 'onsite' ? 'magenta' : 'cyan'} style={{ margin: 0 }}>
                        {getOrderTypeLabel(order)}
                      </Tag>
                    </Space>
                    <div style={{ marginTop: 4 }}>
                      <Text strong>{userName}</Text>
                      {userPhone && (
                        <Text type="secondary" style={{ marginLeft: 8 }}>
                          <PhoneOutlined /> <a href={`tel:${userPhone}`}>{userPhone}</a>
                        </Text>
                      )}
                    </div>
                    {isDelivery && order.address && (
                      <Tooltip title={order.address}>
                        <Text type="secondary" style={{ fontSize: 12, display: 'block' }}>
                          <EnvironmentOutlined />{' '}
                          {order.address.length > 60
                            ? order.address.slice(0, 60) + '…'
                            : order.address}
                        </Text>
                      </Tooltip>
                    )}
                    <Tooltip title={itemsText}>
                      <Text style={{ fontSize: 13, display: 'block', marginTop: 2 }} ellipsis>
                        {itemsText || '—'}
                      </Text>
                    </Tooltip>
                    {order.comment && (
                      <Text type="warning" style={{ fontSize: 12, display: 'block', marginTop: 2 }}>
                        💬 {order.comment}
                      </Text>
                    )}
                  </div>

                  {/* Summa */}
                  <div style={{ minWidth: 120, textAlign: 'right' }}>
                    <div style={{ fontSize: 16, fontWeight: 700, color: '#52c41a' }}>
                      {(order.total_price || 0).toLocaleString()} so'm
                    </div>
                    {order.delivery_fee ? (
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        +{(order.delivery_fee).toLocaleString()} dast.
                      </Text>
                    ) : null}
                  </div>

                  {/* Amallar */}
                  <Space wrap>
                    {nextCfg && (
                      <Button
                        type="primary"
                        icon={<CheckCircleOutlined />}
                        loading={advancingId === order.id}
                        onClick={() => advanceStatus(order)}
                      >
                        {nextCfg.label}
                      </Button>
                    )}
                    <Popconfirm
                      title={`#${order.id} ni bekor qilasizmi?`}
                      okText="Ha"
                      cancelText="Yo'q"
                      onConfirm={() => cancelOrder(order)}
                    >
                      <Button
                        danger
                        icon={<CloseCircleOutlined />}
                        disabled={advancingId === order.id}
                      >
                        Bekor
                      </Button>
                    </Popconfirm>
                  </Space>
                </div>
              )
            })}
          </div>
        )}
      </Card>

      {/* Pastki qisqa statistika */}
      <Row gutter={[12, 12]} style={{ marginTop: 16 }}>
        <Col xs={24} sm={12} md={8}>
          <Card size="small">
            <Statistic
              title="Bugun jami zakaz"
              value={stats.today_orders ?? 0}
              prefix={<ShoppingCartOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={8}>
          <Card size="small">
            <Statistic
              title="Bekor qilingan"
              value={cancelledToday}
              suffix={
                stats.today_orders
                  ? ` · ${Math.round((cancelledToday / stats.today_orders) * 100)}%`
                  : ''
              }
              valueStyle={{ color: cancelledToday > 0 ? '#f5222d' : '#999' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={24} md={8}>
          <Card size="small">
            <Statistic
              title="O'rtacha reyting"
              value={stats.average_rating || 0}
              suffix={` / 5 (${stats.total_reviews || 0} ta)`}
              valueStyle={{ color: '#fadb14' }}
            />
          </Card>
        </Col>
      </Row>
    </div>
  )
}
