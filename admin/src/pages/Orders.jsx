import { useEffect, useState, useRef, useCallback } from 'react'
import { Table, Tag, Card, Typography, Space, Button, DatePicker, message, Popconfirm, Badge, Segmented, Modal, Divider, Tooltip } from 'antd'
import { ReloadOutlined, CheckCircleOutlined, CarOutlined, CloseCircleOutlined, SoundOutlined, EnvironmentOutlined, PhoneOutlined, MessageOutlined, ShopOutlined, ClockCircleOutlined, GiftOutlined, CreditCardOutlined, UserOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { getOrders, updateOrderStatus, refundOrder } from '../api'
import { fmtTashkent } from '../utils/datetime'
import { useBranchStore } from '../store/branch'
import { useAuthStore } from '../store/auth'

const { Title, Text } = Typography
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
  pending:    '⏳ Kutilmoqda',
  confirmed:  '✅ Qabul qilindi',
  preparing:  '👨‍🍳 Tayyorlanmoqda',
  ready:      '📦 Tayyor',
  delivering: "🚗 Yo'lda",
  delivered:  '✅ Yetkazildi',
  cancelled:  '❌ Bekor',
}

const deliverySubtypeText = {
  onsite: '🏠 Joyiga borib yopib berish',
  pickup: '🛍 Olib ketish (saboy)',
  delivery: '🚗 Dastavka',
}
const paymentMethodText = { cash: '💵 Naqd', card: '💳 Karta', click: '💳 Click', payme: '💳 Payme' }
const paymentTimingText = { now: '⚡ Hozir', later: '⏱ Buyurtma olganda' }

function getOrderFlowType(order) {
  if (order?.order_kind === 'catering' && order.delivery_subtype) return order.delivery_subtype
  return order?.delivery_type === 'delivery' ? 'delivery' : 'pickup'
}

function getOrderTypeLabel(order) {
  const type = getOrderFlowType(order)
  return deliverySubtypeText[type] || (type === 'pickup' ? '🏪 Saboy olib ketish' : '🚗 Dastavka')
}

function getOrderTypeColor(order) {
  return { delivery: 'blue', pickup: 'green', onsite: 'purple' }[getOrderFlowType(order)] || 'default'
}

function getStatusLabel(order, status = order?.status) {
  const type = getOrderFlowType(order)
  if (type === 'delivery' && status === 'delivering') return '🚗 Kuryerga berildi'
  if (type === 'pickup' && status === 'ready') return '📦 Zakaz tayyor'
  if (type === 'onsite' && status === 'confirmed') return '✅ Zakaz qabul qilindi'
  return statusText[status] || status
}

function getNextAction(order) {
  const status = order?.status
  const type = getOrderFlowType(order)
  if (status === 'delivered' || status === 'cancelled') return null

  if (type === 'onsite') {
    if (status === 'pending') return { next: 'confirmed', label: 'Zakaz qabul qilindi', confirm: 'Borib yopib berish zakazi qabul qilinsinmi?' }
    return null
  }

  if (type === 'pickup') {
    if (['pending', 'confirmed', 'preparing'].includes(status)) return { next: 'ready', label: 'Zakaz tayyor', confirm: 'Saboy zakaz tayyormi?' }
    if (status === 'ready') return { next: 'delivered', label: 'Mijozga berildi', confirm: 'Zakaz mijozga berildimi?' }
    return null
  }

  if (type === 'delivery') {
    if (status === 'pending') return { next: 'confirmed', label: 'Qabul qilish', confirm: 'Dastavka zakazi qabul qilinsinmi?' }
    if (status === 'confirmed') return { next: 'preparing', label: 'Tayyorlashni boshlash', confirm: 'Tayyorlash boshlansinmi?' }
    if (status === 'preparing') return { next: 'ready', label: 'Zakaz tayyor', confirm: 'Zakaz tayyormi?' }
    if (status === 'ready') return { next: 'delivering', label: 'Kuryerga berildi', confirm: 'Zakaz kuryerga berildimi?' }
    if (status === 'delivering') return { next: 'delivered', label: 'Yetkazildi', confirm: 'Zakaz yetkazildimi?' }
  }

  return null
}

function playNotificationSound() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)()
    const play = (freq, startTime, duration) => {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.connect(gain); gain.connect(ctx.destination)
      osc.type = 'sine'
      osc.frequency.setValueAtTime(freq, ctx.currentTime + startTime)
      gain.gain.setValueAtTime(0.3, ctx.currentTime + startTime)
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + startTime + duration)
      osc.start(ctx.currentTime + startTime)
      osc.stop(ctx.currentTime + startTime + duration)
    }
    play(880, 0, 0.3); play(660, 0.35, 0.3); play(880, 0.7, 0.4)
    play(988, 1.2, 0.3); play(784, 1.55, 0.3); play(988, 1.9, 0.5)
    setTimeout(() => ctx.close(), 3000)
  } catch (e) { console.warn('Audio play failed:', e) }
}

const POLL_INTERVAL = 10000

// ─── Order Detail Modal ─────────────────────────────────
function OrderDetailModal({ order, open, onClose, onStatusChange, onRefund }) {
  if (!order) return null

  const isCatering = order.order_kind === 'catering'
  const total = (order.total_price || 0) + (order.delivery_fee || 0)
  const hasLocation = order.latitude && order.longitude
  const yandexMapUrl = hasLocation
    ? `https://yandex.uz/maps/?pt=${order.longitude},${order.latitude}&z=17&l=map`
    : null

  const renderActions = () => {
    const { status } = order
    const nextAction = getNextAction(order)
    if (status === 'delivered' || status === 'cancelled') return null
    return (
      <Space wrap>
        {nextAction && (
          <Popconfirm title={nextAction.confirm} onConfirm={() => onStatusChange(order.id, nextAction.next)}>
            <Button
              type="primary"
              icon={nextAction.next === 'delivering' || nextAction.next === 'delivered' ? <CarOutlined /> : <CheckCircleOutlined />}
              size="large"
              style={nextAction.next === 'delivered' ? { background: '#52c41a', borderColor: '#52c41a', color: '#fff' } : undefined}
            >
              {nextAction.label}
            </Button>
          </Popconfirm>
        )}
        {order.payment_status === 'paid' ? (
          <Popconfirm
            title="Bekor qilish + pul qaytarish?"
            description={
              <div style={{ maxWidth: 280 }}>
                <div>Mijozga pul qaytariladi va buyurtma bekor qilinadi.</div>
                <div style={{ marginTop: 6 }}>
                  <Tag color="blue">{'≥'}24h</Tag> 100% qaytariladi<br/>
                  <Tag color="orange">6–24h</Tag> 50%<br/>
                  <Tag color="red">{'<'}6h</Tag> 0% (kech)
                </div>
              </div>
            }
            okText="Refund qil" cancelText="Yo'q"
            onConfirm={() => onRefund(order.id)}
          >
            <Button danger icon={<CloseCircleOutlined />} size="large">Bekor qilish + Refund</Button>
          </Popconfirm>
        ) : (
          <Popconfirm title="Bekor qilish?" onConfirm={() => onStatusChange(order.id, 'cancelled')}>
            <Button danger icon={<CloseCircleOutlined />} size="large">Bekor qilish</Button>
          </Popconfirm>
        )}
      </Space>
    )
  }

  return (
    <Modal
      open={open} onCancel={onClose} footer={null} width={760} destroyOnClose
      title={
        <Space>
          <Text strong style={{ fontSize: 18 }}>Buyurtma #{order.id}</Text>
          <Tag color={statusColor[order.status]}>{getStatusLabel(order)}</Tag>
          {isCatering && <Tag color="purple"><GiftOutlined /> Catering</Tag>}
        </Space>
      }
    >
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
        {/* Mijoz */}
        <Card size="small" title={<><UserOutlined /> Mijoz</>}>
          <div style={{ marginBottom: 6 }}><Text strong>{order.user?.full_name || '—'}</Text></div>
          <div><PhoneOutlined /> <a href={`tel:${order.user?.phone}`}>{order.user?.phone || '—'}</a></div>
          {order.user?.telegram_id && (
            <div style={{ marginTop: 4, color: '#666', fontSize: 12 }}>TG: {order.user.telegram_id}</div>
          )}
        </Card>

        {/* Vaqt va tur */}
        <Card size="small" title={<><ClockCircleOutlined /> Vaqt va tur</>}>
          <div style={{ marginBottom: 6 }}>
            <Text type="secondary">Yaratildi:</Text>{' '}
            {fmtTashkent(order.created_at)}
          </div>
          <div>
            <Text type="secondary">Zakaz turi:</Text>{' '}
            <Tag color={getOrderTypeColor(order)}>{getOrderTypeLabel(order)}</Tag>
          </div>
          {order.order_kind === 'catering' && (
            <div style={{ marginTop: 6 }}>
              <Text type="secondary">Tadbir vaqti:</Text>{' '}
              <Text strong>{order.schedule_date || '—'} {order.schedule_time || ''}</Text>
            </div>
          )}
        </Card>
      </div>

      {/* Manzil va xarita */}
      {(order.address || hasLocation) && (
        <Card size="small" title={<><EnvironmentOutlined /> Yetkazish manzili</>} style={{ marginBottom: 16 }}>
          <div style={{ marginBottom: 8 }}>
            <Text strong>{order.address || 'Manzil ko\'rsatilmagan'}</Text>
          </div>
          {hasLocation && (
            <>
              <Space style={{ marginBottom: 8 }} wrap>
                <Tag color="blue">📍 {order.latitude.toFixed(6)}, {order.longitude.toFixed(6)}</Tag>
                <Button type="link" size="small" href={yandexMapUrl} target="_blank">
                  🗺 Yandex Maps'da ochish
                </Button>
                <Button type="link" size="small"
                  href={`https://www.google.com/maps?q=${order.latitude},${order.longitude}`}
                  target="_blank">
                  🌍 Google Maps'da ochish
                </Button>
              </Space>
              <iframe
                title={`Buyurtma #${order.id} xaritasi`}
                src={`https://yandex.com/map-widget/v1/?ll=${order.longitude}%2C${order.latitude}&z=16&pt=${order.longitude}%2C${order.latitude}%2Cpm2rdm&mode=search`}
                style={{
                  width: '100%', height: 280, border: 0, borderRadius: 8,
                  display: 'block', background: '#f0f2f5',
                }}
                loading="lazy"
                allowFullScreen
              />
            </>
          )}
        </Card>
      )}

      {/* Catering ma'lumotlari */}
      {isCatering && (
        <Card size="small" title={<><GiftOutlined /> Catering ma'lumotlari</>} style={{ marginBottom: 16, background: '#fff7e6' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8 }}>
            <div><Text type="secondary">Sana:</Text> <Text strong>{order.schedule_date || '—'}</Text></div>
            <div><Text type="secondary">Vaqt:</Text> <Text strong>{order.schedule_time || '—'}</Text></div>
            <div><Text type="secondary">Tur:</Text> {deliverySubtypeText[order.delivery_subtype] || order.delivery_subtype || '—'}</div>
            <div><Text type="secondary">To'lov:</Text> {paymentTimingText[order.payment_timing] || order.payment_timing || '—'}</div>
          </div>
        </Card>
      )}

      {/* Mahsulotlar */}
      <Card size="small" title={`🛒 Mahsulotlar (${order.items?.length || 0} tur)`} style={{ marginBottom: 16 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #f0f0f0', background: '#fafafa' }}>
              <th style={{ textAlign: 'left', padding: '8px' }}>Nomi</th>
              <th style={{ textAlign: 'center', padding: '8px', width: 70 }}>Soni</th>
              <th style={{ textAlign: 'right', padding: '8px', width: 110 }}>Narxi</th>
              <th style={{ textAlign: 'right', padding: '8px', width: 120 }}>Jami</th>
            </tr>
          </thead>
          <tbody>
            {order.items?.map((item, idx) => (
              <tr key={idx} style={{ borderBottom: '1px solid #f0f0f0' }}>
                <td style={{ padding: '8px' }}>{item.product_name}</td>
                <td style={{ textAlign: 'center', padding: '8px' }}>{item.quantity}</td>
                <td style={{ textAlign: 'right', padding: '8px' }}>{(item.price || 0).toLocaleString()} so'm</td>
                <td style={{ textAlign: 'right', padding: '8px', fontWeight: 600 }}>
                  {((item.price || 0) * item.quantity).toLocaleString()} so'm
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {/* Izoh — sariq fonda alohida */}
      {order.comment && (
        <Card size="small" title={<><MessageOutlined /> Mijoz izohi</>}
          style={{ marginBottom: 16, background: '#fffbe6', borderColor: '#ffe58f' }}>
          <Text style={{ fontSize: 14, fontStyle: 'italic' }}>{order.comment}</Text>
        </Card>
      )}

      {/* Summa */}
      <Card size="small" title={<><CreditCardOutlined /> To'lov</>} style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
          <Text>Mahsulotlar:</Text>
          <Text>{(order.total_price || 0).toLocaleString()} so'm</Text>
        </div>
        {order.delivery_fee > 0 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
            <Text>Dastavka:</Text>
            <Text>{order.delivery_fee.toLocaleString()} so'm</Text>
          </div>
        )}
        <Divider style={{ margin: '8px 0' }} />
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <Text strong style={{ fontSize: 16 }}>Jami:</Text>
          <Text strong style={{ fontSize: 18, color: '#fa8c16' }}>{total.toLocaleString()} so'm</Text>
        </div>
        {order.payment_method && (
          <div style={{ marginTop: 8, color: '#666' }}>
            To'lov turi: {paymentMethodText[order.payment_method] || order.payment_method}
            {order.payment_status && <Tag color={order.payment_status === 'paid' ? 'green' : 'orange'} style={{ marginLeft: 8 }}>{order.payment_status}</Tag>}
          </div>
        )}
      </Card>

      <Divider />
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>{renderActions()}</div>
    </Modal>
  )
}

export default function Orders() {
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [dateRange, setDateRange] = useState([dayjs().subtract(7, 'day'), dayjs()])
  const [pageSize, setPageSize] = useState(15)
  const [soundEnabled, setSoundEnabled] = useState(true)
  const [newOrderFlash, setNewOrderFlash] = useState(false)
  const [orderKind, setOrderKind] = useState('all')
  const [selectedOrder, setSelectedOrder] = useState(null)
  const selectedBranchId = useBranchStore((s) => s.selectedBranchId)
  const restaurantId = useAuthStore((s) => s.currentRestaurantId)
  const prevOrderIdsRef = useRef(new Set())
  const isFirstLoadRef = useRef(true)
  const pollTimerRef = useRef(null)

  const fetchOrders = useCallback(async (range, silent = false) => {
    if (!silent) setLoading(true)
    const [from, to] = range || dateRange
    try {
      const params = {
        date_from: from.format('YYYY-MM-DD'),
        date_to: to.format('YYYY-MM-DD'),
      }
      if (restaurantId) params.restaurant_id = restaurantId
      if (selectedBranchId) params.branch_id = selectedBranchId
      if (orderKind !== 'all') params.order_kind = orderKind
      const res = await getOrders(params)
      const newOrders = res.data || []
      setOrders(newOrders)

      if (!isFirstLoadRef.current) {
        const newIds = newOrders.map(o => o.id)
        const prevIds = prevOrderIdsRef.current
        const freshOrders = newIds.filter(id => !prevIds.has(id))
        if (freshOrders.length > 0) {
          if (soundEnabled) playNotificationSound()
          message.info({ content: `🔔 ${freshOrders.length} ta yangi zakaz tushdi!`, duration: 5 })
          setNewOrderFlash(true)
          setTimeout(() => setNewOrderFlash(false), 3000)
        }
      }
      isFirstLoadRef.current = false
      prevOrderIdsRef.current = new Set(newOrders.map(o => o.id))

      // Modal ochiq bo'lsa, yangi versiyani qo'yish
      if (selectedOrder) {
        const updated = newOrders.find(o => o.id === selectedOrder.id)
        if (updated) setSelectedOrder(updated)
      }
    } catch {
      if (!silent) message.error('Zakazlarni yuklashda xato')
    } finally {
      if (!silent) setLoading(false)
    }
  }, [dateRange, soundEnabled, selectedBranchId, orderKind, restaurantId, selectedOrder])

  useEffect(() => {
    isFirstLoadRef.current = true
    fetchOrders(dateRange)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedBranchId, orderKind])

  useEffect(() => {
    pollTimerRef.current = setInterval(() => fetchOrders(dateRange, true), POLL_INTERVAL)
    return () => clearInterval(pollTimerRef.current)
  }, [dateRange, fetchOrders])

  const handleStatusChange = async (orderId, newStatus) => {
    try {
      await updateOrderStatus(orderId, newStatus)
      message.success(`Zakaz #${orderId}: ${statusText[newStatus]}`)
      fetchOrders(dateRange)
      if (selectedOrder?.id === orderId && (newStatus === 'delivered' || newStatus === 'cancelled')) {
        setSelectedOrder(null)
      }
    } catch { message.error('Holatni o\'zgartirishda xato') }
  }

  const handleRefund = async (orderId) => {
    try {
      const r = await refundOrder(orderId, '')
      message.success(`Refund #${r.refund_id} bajarildi (zakaz #${orderId})`)
      fetchOrders(dateRange)
      if (selectedOrder?.id === orderId) setSelectedOrder(null)
    } catch (e) {
      message.error(e?.response?.data?.detail || 'Refund qilishda xato')
    }
  }

  const handleRangeChange = (dates) => {
    if (dates && dates.length === 2) {
      setDateRange(dates); isFirstLoadRef.current = true; fetchOrders(dates)
    }
  }

  const pendingCount = orders.filter(o => o.status === 'pending').length

  // Compact columns
  const columns = [
    {
      title: '#', dataIndex: 'id', width: 60, fixed: 'left',
      render: (id, r) => (
        <Space size={4}>
          <b>#{id}</b>
          {r.order_kind === 'catering' && <Tooltip title="Catering"><GiftOutlined style={{ color: '#722ed1' }} /></Tooltip>}
        </Space>
      )
    },
    {
      title: 'Mijoz', dataIndex: 'user', ellipsis: true,
      render: (u) => u ? (
        <div>
          <div style={{ fontWeight: 500 }}>{u.full_name || '—'}</div>
          <div style={{ fontSize: 11, color: '#888' }}>{u.phone || ''}</div>
        </div>
      ) : '—'
    },
    {
      title: 'Mahsulotlar', dataIndex: 'items', ellipsis: true,
      render: (items) => (
        <Tooltip title={items?.map((i) => `${i.product_name} ×${i.quantity}`).join(', ')}>
          <Text style={{ fontSize: 12 }}>
            {items?.length || 0} tur · {items?.reduce((s, i) => s + (i.quantity || 0), 0) || 0} ta
          </Text>
        </Tooltip>
      )
    },
    {
      title: 'Summa', dataIndex: 'total_price', width: 120, align: 'right',
      render: (v, r) => (
        <Text strong style={{ color: '#fa8c16' }}>
          {((v || 0) + (r.delivery_fee || 0)).toLocaleString()} so'm
        </Text>
      )
    },
    {
      title: '📍', dataIndex: 'latitude', width: 50, align: 'center',
      render: (_, r) => r.latitude && r.longitude
        ? <Tooltip title={r.address || 'Lokatsiya bor'}><EnvironmentOutlined style={{ color: '#1677ff', fontSize: 16 }} /></Tooltip>
        : <Text type="secondary">—</Text>
    },
    {
      title: 'Tur', dataIndex: 'delivery_type', width: 70, align: 'center',
      render: (_, r) => {
        const type = getOrderFlowType(r)
        const icon = type === 'delivery' ? '🚗' : type === 'onsite' ? '🏠' : '🏪'
        return <Tooltip title={getOrderTypeLabel(r)}><Tag color={getOrderTypeColor(r)} style={{ margin: 0 }}>{icon}</Tag></Tooltip>
      }
    },
    {
      title: 'Holat', dataIndex: 'status', width: 130,
      render: (s, r) => <Tag color={statusColor[s]} style={{ margin: 0 }}>{getStatusLabel(r, s)}</Tag>
    },
    {
      title: 'Vaqt', dataIndex: 'created_at', width: 95,
      render: (v) => v ? (
        <Tooltip title={fmtTashkent(v)}>
          <Text style={{ fontSize: 12 }}>{fmtTashkent(v, 'DD.MM HH:mm')}</Text>
        </Tooltip>
      ) : '—'
    },
    {
      title: 'Amallar', width: 110, fixed: 'right', align: 'center',
      render: (_, record) => {
        const { status } = record
        const nextAction = getNextAction(record)
        if (status === 'delivered') return <Tag color="green" style={{ margin: 0 }}>✅</Tag>
        if (status === 'cancelled') return <Tag color="red" style={{ margin: 0 }}>❌</Tag>
        return (
          <Space size={4} onClick={(e) => e.stopPropagation()}>
            {nextAction && (
              <Popconfirm title={nextAction.confirm} onConfirm={() => handleStatusChange(record.id, nextAction.next)}>
                <Button type="primary" size="small" icon={<CheckCircleOutlined />} />
              </Popconfirm>
            )}
            <Popconfirm title="Bekor qilish?" onConfirm={() => handleStatusChange(record.id, 'cancelled')}>
              <Button danger size="small" icon={<CloseCircleOutlined />} />
            </Popconfirm>
          </Space>
        )
      },
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
        <Space>
          <Title level={4} style={{ margin: 0 }}>Zakazlar</Title>
          {pendingCount > 0 && (
            <Badge count={`${pendingCount} ta yangi`} style={{ backgroundColor: '#fa8c16' }} />
          )}
        </Space>
        <Button size="small" type={soundEnabled ? 'primary' : 'default'} icon={<SoundOutlined />}
          onClick={() => setSoundEnabled(!soundEnabled)}
          style={soundEnabled ? { background: '#fa8c16', borderColor: '#fa8c16' } : {}}>
          {soundEnabled ? 'Ovoz: ON' : 'Ovoz: OFF'}
        </Button>
      </div>

      <Card>
        <Space style={{ marginBottom: 16 }} wrap>
          <Segmented value={orderKind} onChange={setOrderKind}
            options={[
              { label: 'Barchasi', value: 'all' },
              { label: '🍽 Oddiy', value: 'regular' },
              { label: '🎉 Catering', value: 'catering' },
            ]}
          />
          <RangePicker value={dateRange} onChange={handleRangeChange} format="DD.MM.YYYY" allowClear={false} />
          <Button icon={<ReloadOutlined />} onClick={() => fetchOrders(dateRange)}>Yangilash</Button>
        </Space>

        <Table
          dataSource={orders}
          columns={columns}
          rowKey="id"
          loading={loading}
          size="small"
          onRow={(record) => ({
            onClick: () => setSelectedOrder(record),
            style: { cursor: 'pointer' },
          })}
          pagination={{
            pageSize,
            pageSizeOptions: ['15', '30', '50'],
            showSizeChanger: true,
            onShowSizeChange: (_, size) => setPageSize(size),
            showTotal: (total) => `Jami: ${total} ta`,
          }}
          scroll={{ x: 950 }}
          rowClassName={(r) =>
            r.status === 'pending'
              ? `ant-table-row-pending${newOrderFlash ? ' order-flash' : ''}`
              : ''
          }
        />
      </Card>

      <OrderDetailModal
        order={selectedOrder}
        open={!!selectedOrder}
        onClose={() => setSelectedOrder(null)}
        onStatusChange={handleStatusChange}
        onRefund={handleRefund}
      />
    </div>
  )
}
