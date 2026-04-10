import { useEffect, useState } from 'react'
import {
  Row, Col, Card, Statistic, Typography, Spin, Table, Button,
  Modal, InputNumber, Tag, Space, Tooltip, Descriptions, message, Form, Input, Drawer, Badge, Alert
} from 'antd'
import {
  ShopOutlined, CheckCircleOutlined, ShoppingCartOutlined, CarOutlined,
  CreditCardOutlined, DollarOutlined, EditOutlined, CheckOutlined, HistoryOutlined,
  CopyOutlined, ClockCircleOutlined, CloseOutlined, ExclamationCircleOutlined
} from '@ant-design/icons'
import {
  getStats, getCommissionSummary,
  updateCommissionPercent, markCommissionPaid, getCommissionHistory,
  getPendingPayments, confirmPayment, rejectPayment
} from '../api'
import dayjs from 'dayjs'

const { Title, Text } = Typography

function fmt(n) {
  return Number(n || 0).toLocaleString('uz-UZ') + ' so\'m'
}

// Super admin to'lov modali (bevosita tasdiqlash)
function PaymentModal({ open, onClose, record, onPaid }) {
  const [paying, setPaying] = useState(false)
  const [noteForm] = Form.useForm()

  const handlePay = async () => {
    const note = noteForm.getFieldValue('note')
    setPaying(true)
    try {
      await onPaid(record.restaurant_id, note)
      message.success('To\'lov belgilandi')
      onClose()
    } catch (e) {
      message.error(e.response?.data?.detail || 'Xato')
    } finally {
      setPaying(false)
    }
  }

  const copyCard = () => {
    navigator.clipboard.writeText(record?.payment_card_number?.replace(/\s/g, '') || '')
    message.success('Karta raqami nusxalandi')
  }

  if (!record) return null
  const hasCard = !!record.payment_card_number

  return (
    <Modal
      open={open}
      onCancel={onClose}
      title={`To'lov — ${record.name}`}
      footer={null}
      width={480}
    >
      <Card size="small" style={{ background: '#f6ffed', border: '1px solid #b7eb8f', marginBottom: 16 }}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="Savdo summasi"><b>{fmt(record.revenue)}</b></Descriptions.Item>
          <Descriptions.Item label="Komissiya foizi"><b>{record.commission_percent}%</b></Descriptions.Item>
          <Descriptions.Item label="To'lash kerak" span={2}>
            <Text style={{ fontSize: 22, fontWeight: 700, color: '#722ed1' }}>
              {fmt(record.commission_amount)}
            </Text>
          </Descriptions.Item>
          {record.period_from && (
            <Descriptions.Item label="Davr boshidan" span={2}>
              {dayjs(record.period_from).format('DD.MM.YYYY')}
            </Descriptions.Item>
          )}
        </Descriptions>
      </Card>

      {hasCard ? (
        <Card size="small" style={{ background: 'linear-gradient(135deg, #722ed1, #b37feb)', borderRadius: 12, marginBottom: 16 }}>
          <div style={{ color: '#fff' }}>
            <div style={{ fontSize: 11, opacity: 0.8, marginBottom: 4 }}>{record.payment_card_bank || 'KARTA'}</div>
            <div style={{ fontSize: 20, fontWeight: 700, letterSpacing: 2, fontFamily: 'monospace' }}>
              {record.payment_card_number}
              <Tooltip title="Nusxalash">
                <Button size="small" type="text" icon={<CopyOutlined />} onClick={copyCard}
                  style={{ color: '#fff', marginLeft: 8 }} />
              </Tooltip>
            </div>
            <div style={{ fontSize: 13, marginTop: 6, opacity: 0.9 }}>{record.payment_card_name}</div>
          </div>
        </Card>
      ) : (
        <Card size="small" style={{ background: '#fff7e6', border: '1px solid #ffd591', marginBottom: 16 }}>
          <Text type="warning">Karta ma'lumoti kiritilmagan.</Text>
        </Card>
      )}

      <Form form={noteForm}>
        <Form.Item name="note" label="Izoh (ixtiyoriy)">
          <Input placeholder="To'lov raqami yoki izoh..." />
        </Form.Item>
      </Form>

      <Button type="primary" block size="large" loading={paying}
        disabled={record.commission_amount <= 0} onClick={handlePay}
        style={{ background: '#722ed1', borderColor: '#722ed1' }} icon={<CheckOutlined />}>
        To'landi deb belgilash
      </Button>
    </Modal>
  )
}

// Pending to'lovni tasdiqlash modali
function ConfirmPaymentModal({ open, onClose, payment, onConfirm, onReject }) {
  const [confirming, setConfirming] = useState(false)
  const [rejecting, setRejecting] = useState(false)

  if (!payment) return null

  const handleConfirm = async () => {
    setConfirming(true)
    try {
      await onConfirm(payment.id)
      message.success('To\'lov tasdiqlandi')
      onClose()
    } catch (e) {
      message.error(e.response?.data?.detail || 'Xato')
    } finally {
      setConfirming(false)
    }
  }

  const handleReject = async () => {
    setRejecting(true)
    try {
      await onReject(payment.id)
      message.warning('To\'lov rad etildi')
      onClose()
    } catch (e) {
      message.error(e.response?.data?.detail || 'Xato')
    } finally {
      setRejecting(false)
    }
  }

  return (
    <Modal
      open={open}
      onCancel={onClose}
      title={
        <Space>
          <ExclamationCircleOutlined style={{ color: '#fa8c16' }} />
          To'lovni tasdiqlash — {payment.restaurant_name}
        </Space>
      }
      footer={null}
      width={440}
    >
      <Alert
        message="Admin to'lov qilganini bildirdi"
        description="Pul kartangizga tushganini tekshirib, tasdiqlang yoki rad eting."
        type="warning"
        showIcon
        style={{ marginBottom: 16 }}
      />
      <Card size="small" style={{ background: '#f9f0ff', border: '1px solid #d3adf7', marginBottom: 16 }}>
        <Descriptions column={1} size="small">
          <Descriptions.Item label="Restoran"><b>{payment.restaurant_name}</b></Descriptions.Item>
          <Descriptions.Item label="Summa">
            <b style={{ fontSize: 18, color: '#722ed1' }}>{fmt(payment.amount)}</b>
          </Descriptions.Item>
          <Descriptions.Item label="Foiz">{payment.commission_percent}%</Descriptions.Item>
          <Descriptions.Item label="Savdo">{fmt(payment.orders_revenue)}</Descriptions.Item>
          <Descriptions.Item label="Yuborilgan">
            {dayjs(payment.paid_at).format('DD.MM.YYYY HH:mm')}
          </Descriptions.Item>
          {payment.note && (
            <Descriptions.Item label="Izoh">{payment.note}</Descriptions.Item>
          )}
        </Descriptions>
      </Card>
      <Row gutter={12}>
        <Col span={12}>
          <Button block size="large" type="primary" icon={<CheckOutlined />}
            loading={confirming} onClick={handleConfirm}
            style={{ background: '#52c41a', borderColor: '#52c41a' }}>
            Tasdiqlash
          </Button>
        </Col>
        <Col span={12}>
          <Button block size="large" danger icon={<CloseOutlined />}
            loading={rejecting} onClick={handleReject}>
            Rad etish
          </Button>
        </Col>
      </Row>
    </Modal>
  )
}

// Tarix drawer
function HistoryDrawer({ open, onClose, history, name }) {
  const statusTag = (s) => {
    if (s === 'confirmed') return <Tag color="green">Tasdiqlangan</Tag>
    if (s === 'rejected') return <Tag color="red">Rad etilgan</Tag>
    return <Tag color="orange">Kutilmoqda</Tag>
  }
  const cols = [
    { title: 'Sana', dataIndex: 'paid_at', render: (v) => dayjs(v).format('DD.MM.YYYY HH:mm') },
    { title: 'Savdo', dataIndex: 'orders_revenue', render: (v) => fmt(v) },
    { title: 'Foiz', dataIndex: 'commission_percent', render: (v) => `${v}%` },
    { title: 'Summa', dataIndex: 'amount', render: (v) => <b style={{ color: '#52c41a' }}>{fmt(v)}</b> },
    { title: 'Holat', dataIndex: 'status', render: statusTag },
    { title: 'Izoh', dataIndex: 'note', render: (v) => v || '—' },
  ]
  return (
    <Drawer open={open} onClose={onClose} title={`To'lov tarixi — ${name}`} width={720}>
      <Table dataSource={history} columns={cols} rowKey="id" size="small" scroll={{ x: 600 }} />
    </Drawer>
  )
}

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [commissions, setCommissions] = useState([])
  const [pendingPayments, setPendingPayments] = useState([])
  const [loading, setLoading] = useState(true)
  const [payModal, setPayModal] = useState({ open: false, record: null })
  const [confirmModal, setConfirmModal] = useState({ open: false, payment: null })
  const [histDrawer, setHistDrawer] = useState({ open: false, id: null, name: '', history: [] })
  const [editPercent, setEditPercent] = useState({ id: null, value: 0 })

  const loadAll = () => {
    setLoading(true)
    Promise.all([getStats(), getCommissionSummary(), getPendingPayments()])
      .then(([s, c, p]) => {
        setStats(s.data)
        setCommissions(c.data)
        setPendingPayments(p.data)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadAll() }, [])

  const handlePaid = async (id, note) => {
    await markCommissionPaid(id, note)
    loadAll()
  }

  const handleConfirm = async (paymentId) => {
    await confirmPayment(paymentId)
    loadAll()
  }

  const handleReject = async (paymentId) => {
    await rejectPayment(paymentId)
    loadAll()
  }

  const handlePercentSave = async (id, val) => {
    await updateCommissionPercent(id, val)
    message.success('Foiz yangilandi')
    setEditPercent({ id: null, value: 0 })
    loadAll()
  }

  const openHistory = async (id, name) => {
    const res = await getCommissionHistory(id)
    setHistDrawer({ open: true, id, name, history: res.data })
  }

  const totalCommission = commissions.reduce((s, r) => s + (r.commission_amount || 0), 0)

  const pendingColumns = [
    {
      title: 'Restoran',
      dataIndex: 'restaurant_name',
      render: (v, r) => (
        <Space direction="vertical" size={0}>
          <b>{v}</b>
          <Text type="secondary" style={{ fontSize: 11 }}>{r.restaurant_slug}</Text>
        </Space>
      ),
    },
    { title: 'Summa', dataIndex: 'amount', render: (v) => <b style={{ color: '#722ed1', fontSize: 16 }}>{fmt(v)}</b> },
    { title: 'Savdo', dataIndex: 'orders_revenue', render: (v) => fmt(v) },
    { title: 'Yuborilgan', dataIndex: 'paid_at', render: (v) => dayjs(v).format('DD.MM.YYYY HH:mm') },
    { title: 'Izoh', dataIndex: 'note', render: (v) => v || '—' },
    {
      title: 'Amal',
      width: 200,
      render: (_, r) => (
        <Space>
          <Button size="small" type="primary" icon={<CheckOutlined />}
            onClick={() => setConfirmModal({ open: true, payment: r })}
            style={{ background: '#52c41a', borderColor: '#52c41a' }}>
            Tasdiqlash
          </Button>
          <Button size="small" danger icon={<CloseOutlined />}
            onClick={async () => {
              await rejectPayment(r.id)
              message.warning('Rad etildi')
              loadAll()
            }}>
            Rad
          </Button>
        </Space>
      ),
    },
  ]

  const commissionColumns = [
    {
      title: 'Restoran',
      dataIndex: 'name',
      render: (v, r) => (
        <Space direction="vertical" size={0}>
          <Space>
            <b>{v}</b>
            {r.pending_count > 0 && (
              <Badge count={r.pending_count} size="small" style={{ backgroundColor: '#fa8c16' }}
                title={`${r.pending_count} ta tasdiqlanmagan to'lov`} />
            )}
          </Space>
          <Text type="secondary" style={{ fontSize: 11 }}>{r.slug}</Text>
        </Space>
      ),
    },
    {
      title: 'Savdo (davr)',
      dataIndex: 'revenue',
      render: (v) => fmt(v),
      sorter: (a, b) => a.revenue - b.revenue,
    },
    {
      title: 'Foiz %',
      dataIndex: 'commission_percent',
      width: 140,
      render: (v, r) => editPercent.id === r.restaurant_id ? (
        <Space>
          <InputNumber size="small" min={0} max={100} step={0.5} value={editPercent.value}
            style={{ width: 70 }} onChange={(val) => setEditPercent({ ...editPercent, value: val })} />
          <Button size="small" type="primary" onClick={() => handlePercentSave(r.restaurant_id, editPercent.value)}>✓</Button>
          <Button size="small" onClick={() => setEditPercent({ id: null, value: 0 })}>✗</Button>
        </Space>
      ) : (
        <Space>
          <Tag color="purple">{v}%</Tag>
          <Button size="small" icon={<EditOutlined />}
            onClick={() => setEditPercent({ id: r.restaurant_id, value: v })} />
        </Space>
      ),
    },
    {
      title: 'Komissiya',
      dataIndex: 'commission_amount',
      render: (v) => <b style={{ color: v > 0 ? '#722ed1' : '#999' }}>{fmt(v)}</b>,
      sorter: (a, b) => a.commission_amount - b.commission_amount,
    },
    {
      title: 'Amallar',
      width: 160,
      render: (_, r) => (
        <Space>
          <Tooltip title="To'lov belgilash (bevosita)">
            <Button size="small" type="primary" icon={<CreditCardOutlined />}
              disabled={r.commission_amount <= 0}
              onClick={() => setPayModal({ open: true, record: r })}
              style={{ background: '#722ed1', borderColor: '#722ed1' }}>
              To'lov
            </Button>
          </Tooltip>
          <Tooltip title="Tarix">
            <Button size="small" icon={<HistoryOutlined />}
              onClick={() => openHistory(r.restaurant_id, r.name)} />
          </Tooltip>
        </Space>
      ),
    },
  ]

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '80px auto' }} />

  return (
    <div>
      <Title level={4} style={{ marginBottom: 24 }}>Platforma statistikasi</Title>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={6}>
          <Card><Statistic title="Jami restoranlar" value={stats?.total_restaurants ?? 0}
            prefix={<ShopOutlined style={{ color: '#722ed1' }} />} valueStyle={{ color: '#722ed1' }} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="Faol restoranlar" value={stats?.active_restaurants ?? 0}
            prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />} valueStyle={{ color: '#52c41a' }} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="Jami zakazlar" value={stats?.total_orders ?? 0}
            prefix={<ShoppingCartOutlined style={{ color: '#1677ff' }} />} valueStyle={{ color: '#1677ff' }} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="Yetkazilgan" value={stats?.delivered_orders ?? 0}
            prefix={<CarOutlined style={{ color: '#fa8c16' }} />} valueStyle={{ color: '#fa8c16' }} /></Card>
        </Col>
      </Row>

      {/* Kutilayotgan to'lovlar */}
      {pendingPayments.length > 0 && (
        <Card
          style={{ marginBottom: 24, border: '2px solid #fa8c16' }}
          title={
            <Space>
              <ClockCircleOutlined style={{ color: '#fa8c16' }} />
              <span style={{ color: '#fa8c16', fontWeight: 700 }}>Tasdiqlanmagan to'lovlar</span>
              <Badge count={pendingPayments.length} style={{ backgroundColor: '#fa8c16' }} />
            </Space>
          }
        >
          <Alert
            message="Adminlar to'lov qilganligini bildirdi. Pul tushganini tekshirib tasdiqlang."
            type="warning"
            showIcon
            style={{ marginBottom: 12 }}
          />
          <Table
            dataSource={pendingPayments}
            columns={pendingColumns}
            rowKey="id"
            size="small"
            scroll={{ x: 600 }}
            pagination={false}
          />
        </Card>
      )}

      {/* Komissiya jadvali */}
      <Card
        title={
          <Space>
            <DollarOutlined style={{ color: '#722ed1' }} />
            <span>Komissiya nazorati</span>
            <Tag color="purple" style={{ marginLeft: 8 }}>
              Jami: {fmt(totalCommission)}
            </Tag>
          </Space>
        }
      >
        <Table
          dataSource={commissions}
          columns={commissionColumns}
          rowKey="restaurant_id"
          size="small"
          scroll={{ x: 700 }}
          pagination={false}
          rowClassName={(r) => r.commission_amount > 0 ? '' : 'opacity-50'}
        />
      </Card>

      <PaymentModal
        open={payModal.open}
        record={payModal.record}
        onClose={() => setPayModal({ open: false, record: null })}
        onPaid={handlePaid}
      />
      <ConfirmPaymentModal
        open={confirmModal.open}
        payment={confirmModal.payment}
        onClose={() => setConfirmModal({ open: false, payment: null })}
        onConfirm={handleConfirm}
        onReject={handleReject}
      />
      <HistoryDrawer
        open={histDrawer.open}
        onClose={() => setHistDrawer({ ...histDrawer, open: false })}
        history={histDrawer.history}
        name={histDrawer.name}
      />
    </div>
  )
}
