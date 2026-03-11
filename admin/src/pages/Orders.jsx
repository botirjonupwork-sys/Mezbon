import { useEffect, useState, useRef, useCallback } from 'react'
import { Table, Tag, Card, Typography, Space, Button, DatePicker, Descriptions, message, Popconfirm, Badge } from 'antd'
import { ReloadOutlined, CheckCircleOutlined, CarOutlined, CloseCircleOutlined, SoundOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { getOrders, updateOrderStatus } from '../api'
import { useBranchStore } from '../store/branch'

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

// Ovozli signal — Web Audio API orqali jarangli bell
function playNotificationSound() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)()

    // 1-chi bell — yuqori ton
    const play = (freq, startTime, duration) => {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.connect(gain)
      gain.connect(ctx.destination)
      osc.type = 'sine'
      osc.frequency.setValueAtTime(freq, ctx.currentTime + startTime)
      gain.gain.setValueAtTime(0.3, ctx.currentTime + startTime)
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + startTime + duration)
      osc.start(ctx.currentTime + startTime)
      osc.stop(ctx.currentTime + startTime + duration)
    }

    // Ding-dong-ding pattern (3 marta)
    play(880, 0, 0.3)       // ding
    play(660, 0.35, 0.3)    // dong
    play(880, 0.7, 0.4)     // ding (uzunroq)

    // Ikkinchi set — kuchliroq
    play(988, 1.2, 0.3)
    play(784, 1.55, 0.3)
    play(988, 1.9, 0.5)

    setTimeout(() => ctx.close(), 3000)
  } catch (e) {
    console.warn('Audio play failed:', e)
  }
}

const POLL_INTERVAL = 10000 // 10 sekund

export default function Orders() {
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [dateRange, setDateRange] = useState([dayjs().subtract(7, 'day'), dayjs()])
  const [pageSize, setPageSize] = useState(10)
  const [soundEnabled, setSoundEnabled] = useState(true)
  const [newOrderFlash, setNewOrderFlash] = useState(false)
  const selectedBranchId = useBranchStore((s) => s.selectedBranchId)
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
      if (selectedBranchId) params.branch_id = selectedBranchId
      const res = await getOrders(params)
      const newOrders = res.data || []
      setOrders(newOrders)

      // Yangi zakaz kelganini tekshirish
      if (!isFirstLoadRef.current) {
        const newIds = newOrders.map(o => o.id)
        const prevIds = prevOrderIdsRef.current
        const freshOrders = newIds.filter(id => !prevIds.has(id))

        if (freshOrders.length > 0) {
          // Yangi zakaz keldi!
          if (soundEnabled) playNotificationSound()
          message.info({
            content: `🔔 ${freshOrders.length} ta yangi zakaz tushdi!`,
            duration: 5,
            style: { marginTop: '20px' },
          })
          setNewOrderFlash(true)
          setTimeout(() => setNewOrderFlash(false), 3000)
        }
      }
      isFirstLoadRef.current = false
      prevOrderIdsRef.current = new Set(newOrders.map(o => o.id))
    } catch {
      if (!silent) message.error('Zakazlarni yuklashda xato')
    } finally {
      if (!silent) setLoading(false)
    }
  }, [dateRange, soundEnabled, selectedBranchId])

  // Birinchi yuklash + branch o'zgarganda
  useEffect(() => {
    isFirstLoadRef.current = true
    fetchOrders(dateRange)
  }, [selectedBranchId])

  // Polling — har 10 sekundda yangi zakazlarni tekshirish
  useEffect(() => {
    pollTimerRef.current = setInterval(() => {
      fetchOrders(dateRange, true)
    }, POLL_INTERVAL)
    return () => clearInterval(pollTimerRef.current)
  }, [dateRange, fetchOrders])

  const handleStatusChange = async (orderId, newStatus) => {
    try {
      await updateOrderStatus(orderId, newStatus)
      message.success(`Zakaz #${orderId}: ${statusText[newStatus]}`)
      fetchOrders(dateRange)
    } catch {
      message.error('Holatni o\'zgartirishda xato')
    }
  }

  const handleRangeChange = (dates) => {
    if (dates && dates.length === 2) {
      setDateRange(dates)
      isFirstLoadRef.current = true
      fetchOrders(dates)
    }
  }

  // Expandable row — to'liq zakaz ma'lumotlari
  const expandedRowRender = (record) => {
    return (
      <div style={{ padding: '8px 0' }}>
        <Descriptions column={{ xs: 1, sm: 2, md: 3 }} size="small" bordered>
          <Descriptions.Item label="Zakaz raqami">
            <Text strong>#{record.id}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="Holat">
            <Tag color={statusColor[record.status]}>{statusText[record.status]}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Vaqt">
            {record.created_at ? new Date(record.created_at).toLocaleString('uz') : '—'}
          </Descriptions.Item>

          <Descriptions.Item label="Mijoz ismi">
            {record.user?.full_name || '—'}
          </Descriptions.Item>
          <Descriptions.Item label="Telefon">
            <a href={`tel:${record.user?.phone}`}>{record.user?.phone || '—'}</a>
          </Descriptions.Item>
          <Descriptions.Item label="Yetkazish turi">
            {record.delivery_type === 'delivery' ? '🚗 Dastavka' : '🏪 Saboy olib ketish'}
          </Descriptions.Item>

          <Descriptions.Item label="Manzil" span={2}>
            {record.address || '—'}
          </Descriptions.Item>
          <Descriptions.Item label="Izoh">
            {record.comment || '—'}
          </Descriptions.Item>

          <Descriptions.Item label="Mahsulotlar" span={3}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #f0f0f0' }}>
                  <th style={{ textAlign: 'left', padding: '4px 8px' }}>Nomi</th>
                  <th style={{ textAlign: 'center', padding: '4px 8px' }}>Soni</th>
                  <th style={{ textAlign: 'right', padding: '4px 8px' }}>Narxi</th>
                  <th style={{ textAlign: 'right', padding: '4px 8px' }}>Jami</th>
                </tr>
              </thead>
              <tbody>
                {record.items?.map((item, idx) => (
                  <tr key={idx} style={{ borderBottom: '1px solid #f0f0f0' }}>
                    <td style={{ padding: '4px 8px' }}>{item.product_name}</td>
                    <td style={{ textAlign: 'center', padding: '4px 8px' }}>{item.quantity}</td>
                    <td style={{ textAlign: 'right', padding: '4px 8px' }}>{(item.price || 0).toLocaleString()} so'm</td>
                    <td style={{ textAlign: 'right', padding: '4px 8px', fontWeight: 600 }}>
                      {((item.price || 0) * item.quantity).toLocaleString()} so'm
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Descriptions.Item>

          <Descriptions.Item label="Mahsulotlar summasi">
            <Text strong>{(record.total_price || 0).toLocaleString()} so'm</Text>
          </Descriptions.Item>
          <Descriptions.Item label="Dastavka narxi">
            {record.delivery_fee ? `${record.delivery_fee.toLocaleString()} so'm` : '—'}
          </Descriptions.Item>
          <Descriptions.Item label="Umumiy summa">
            <Text strong style={{ fontSize: 16, color: '#fa8c16' }}>
              {((record.total_price || 0) + (record.delivery_fee || 0)).toLocaleString()} so'm
            </Text>
          </Descriptions.Item>
        </Descriptions>
      </div>
    )
  }

  const pendingCount = orders.filter(o => o.status === 'pending').length

  const columns = [
    { title: '#', dataIndex: 'id', width: 60, render: (id) => <b>#{id}</b> },
    {
      title: 'Mijoz', dataIndex: 'user',
      render: (u) => u ? `${u.full_name} (${u.phone})` : '—'
    },
    {
      title: 'Mahsulotlar',
      dataIndex: 'items',
      ellipsis: true,
      render: (items) =>
        items?.map((i) => `${i.product_name} x${i.quantity}`).join(', ') || '—'
    },
    {
      title: 'Summa', dataIndex: 'total_price',
      render: (v) => `${(v || 0).toLocaleString()} so'm`
    },
    {
      title: 'Tur', dataIndex: 'delivery_type', width: 100,
      render: (v) => v === 'delivery'
        ? <Tag color="blue">🚗</Tag>
        : <Tag color="green">🏪</Tag>
    },
    {
      title: 'Holat', dataIndex: 'status', width: 130,
      render: (s) => <Tag color={statusColor[s]}>{statusText[s]}</Tag>
    },
    {
      title: 'Vaqt', dataIndex: 'created_at',
      width: 140,
      render: (v) => v ? new Date(v).toLocaleString('uz') : '—'
    },
    {
      title: 'Amallar', width: 130, fixed: 'right',
      render: (_, record) => {
        const { status } = record
        if (status === 'delivered') return <Tag color="green">✅</Tag>
        if (status === 'cancelled') return <Tag color="red">❌</Tag>

        return (
          <Space size={4} wrap>
            {status === 'pending' && (
              <Popconfirm
                title="Qabul qilish?"
                onConfirm={() => handleStatusChange(record.id, 'confirmed')}
              >
                <Button type="primary" size="small" icon={<CheckCircleOutlined />}>
                  Qabul
                </Button>
              </Popconfirm>
            )}

            {['confirmed', 'preparing', 'ready', 'delivering'].includes(status) && (
              <Popconfirm
                title="Yetkazildimi?"
                onConfirm={() => handleStatusChange(record.id, 'delivered')}
              >
                <Button size="small" icon={<CarOutlined />}
                  style={{ background: '#52c41a', borderColor: '#52c41a', color: '#fff' }}
                >
                  Tayyor
                </Button>
              </Popconfirm>
            )}

            <Popconfirm
              title="Bekor qilish?"
              onConfirm={() => handleStatusChange(record.id, 'cancelled')}
            >
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
            <Badge
              count={`${pendingCount} ta yangi`}
              style={{ backgroundColor: '#fa8c16' }}
            />
          )}
        </Space>
        <Button
          size="small"
          type={soundEnabled ? 'primary' : 'default'}
          icon={<SoundOutlined />}
          onClick={() => setSoundEnabled(!soundEnabled)}
          style={soundEnabled ? { background: '#fa8c16', borderColor: '#fa8c16' } : {}}
        >
          {soundEnabled ? 'Ovoz: ON' : 'Ovoz: OFF'}
        </Button>
      </div>

      <Card>
        <Space style={{ marginBottom: 16 }} wrap>
          <RangePicker
            value={dateRange}
            onChange={handleRangeChange}
            format="DD.MM.YYYY"
            allowClear={false}
          />
          <Button icon={<ReloadOutlined />} onClick={() => fetchOrders(dateRange)}>
            Yangilash
          </Button>
        </Space>

        <Table
          dataSource={orders}
          columns={columns}
          rowKey="id"
          loading={loading}
          expandable={{
            expandedRowRender,
            expandRowByClick: true,
          }}
          pagination={{
            pageSize,
            pageSizeOptions: ['10', '30', '50'],
            showSizeChanger: true,
            onShowSizeChange: (_, size) => setPageSize(size),
            showTotal: (total) => `Jami: ${total} ta`,
          }}
          scroll={{ x: 900 }}
          rowClassName={(r) =>
            r.status === 'pending'
              ? `ant-table-row-pending${newOrderFlash ? ' order-flash' : ''}`
              : ''
          }
        />
      </Card>
    </div>
  )
}
