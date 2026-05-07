import { useEffect, useState } from 'react'
import {
  Card, Row, Col, Button, Tag, Typography, Space, Alert, Spin, Modal,
  Table, Empty, Divider, message, Tooltip, Radio,
} from 'antd'
import {
  CheckCircleOutlined, CloseCircleOutlined, CreditCardOutlined,
  ThunderboltOutlined, RocketOutlined, GiftOutlined, RobotOutlined,
  CalendarOutlined, HistoryOutlined, LockOutlined, ClockCircleOutlined,
  ThunderboltFilled,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  getBillingPlans, getBillingPayments, createInvoice, mockCompletePayment,
  getBillingStatus, upgradeBillingPlan, getProfile,
} from '../api'
import { useAuthStore } from '../store/auth'
import { fmtTashkent } from '../utils/datetime'

const { Title, Text, Paragraph } = Typography

const PLAN_GRADIENTS = {
  free:  'linear-gradient(135deg, #f5f5f5, #e8e8e8)',
  basic: 'linear-gradient(135deg, #e6f7ff, #bae7ff)',
  pro:   'linear-gradient(135deg, #fff7e6, #ffd591)',
}

function formatUZS(uzs) {
  return new Intl.NumberFormat('uz-UZ').format(uzs || 0)
}

function PaymentStatusTag({ status }) {
  const map = {
    pending: { color: 'orange', text: '⏳ Kutilmoqda' },
    success: { color: 'green',  text: '✅ Muvaffaqiyatli' },
    failed:  { color: 'red',    text: '❌ Muvaffaqiyatsiz' },
  }
  const v = map[status] || { color: 'default', text: status }
  return <Tag color={v.color}>{v.text}</Tag>
}

export default function Billing() {
  const { restaurantId } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(null)
  const [data, setData] = useState({ current_plan_id: null, current_plan_expires_at: null, plans: [] })
  const [payments, setPayments] = useState([])
  const [paymentModal, setPaymentModal] = useState(null)
  // Faza 6: Upgrade modal (immediate vs queued)
  const [upgradeModal, setUpgradeModal] = useState(null)   // { plan, provider }
  const [billingStatus, setBillingStatus] = useState(null)
  const [profile, setProfile] = useState(null)             // is_verified ni o'qish uchun

  const load = async () => {
    if (!restaurantId) { setLoading(false); return }
    setLoading(true)
    try {
      const [plansRes, paymentsRes, statusRes, profileRes] = await Promise.all([
        getBillingPlans({ restaurant_id: restaurantId }),
        getBillingPayments({ restaurant_id: restaurantId }),
        getBillingStatus({ restaurant_id: restaurantId }).catch(() => ({ data: null })),
        getProfile({ restaurant_id: restaurantId }).catch(() => ({ data: null })),
      ])
      setData(plansRes.data || { plans: [] })
      setPayments(paymentsRes.data || [])
      setBillingStatus(statusRes.data)
      setProfile(profileRes.data)
    } catch (e) {
      message.error('Ma\'lumotlarni yuklashda xato')
    } finally {
      setLoading(false)
    }
  }

  // ── Faza 6: Upgrade flow (modal orqali) ─────────────────
  const openUpgradeModal = (plan, provider) => {
    if (!profile?.is_verified) {
      message.warning('Tarif sotib olish uchun INN tasdiqlangan bo\'lishi kerak')
      return
    }
    setUpgradeModal({ plan, provider })
  }

  const handleUpgrade = async (upgradeType) => {
    if (!upgradeModal) return
    setCreating(upgradeModal.plan.id)
    try {
      const res = await upgradeBillingPlan({
        plan_id: upgradeModal.plan.id,
        upgrade_type: upgradeType,        // 'immediate' yoki 'queued'
        provider: upgradeModal.provider,
      }, { restaurant_id: restaurantId })
      const d = res.data
      setUpgradeModal(null)
      setPaymentModal({
        url: d.payment_url,
        payment_id: d.payment_id,
        merchant_trans_id: d.merchant_trans_id,
        amount_uzs: d.amount_uzs,
        provider: upgradeModal.provider,
        upgrade_type: upgradeType,
        message: d.message,
      })
    } catch (e) {
      const detail = e?.response?.data?.detail
      message.error(typeof detail === 'string' ? detail : (detail?.message || 'Upgrade xato'))
    } finally {
      setCreating(null)
    }
  }

  useEffect(() => { load() }, [restaurantId])

  const handlePay = async (planId, provider) => {
    setCreating(planId)
    try {
      const res = await createInvoice({ plan_id: planId, provider }, { restaurant_id: restaurantId })
      const d = res.data
      setPaymentModal({
        url: d.payment_url,
        payment_id: d.payment_id,
        merchant_trans_id: d.merchant_trans_id,
        amount_uzs: d.amount_uzs,
        provider: d.provider,
      })
    } catch (e) {
      const detail = e?.response?.data?.detail || 'To\'lov yaratishda xato'
      message.error(detail)
    } finally {
      setCreating(null)
    }
  }

  const handleMockComplete = async () => {
    if (!paymentModal) return
    try {
      await mockCompletePayment(paymentModal.merchant_trans_id, { restaurant_id: restaurantId })
      message.success('To\'lov muvaffaqiyatli o\'tdi (mock)')
      setPaymentModal(null)
      await load()
    } catch (e) {
      message.error('Mock complete xato')
    }
  }

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 100 }} />

  const expiresAt = data.current_plan_expires_at ? dayjs(data.current_plan_expires_at) : null
  const daysLeft = expiresAt ? expiresAt.diff(dayjs(), 'day') : null
  const expiringSoon = daysLeft !== null && daysLeft <= 7 && daysLeft >= 0

  const paymentColumns = [
    { title: '#', dataIndex: 'id', width: 60 },
    {
      title: 'Sana', dataIndex: 'created_at',
      render: (v) => fmtTashkent(v),
    },
    {
      title: 'Summa', dataIndex: 'amount_uzs',
      render: (v) => `${formatUZS(v)} so'm`,
    },
    {
      title: 'Provayder', dataIndex: 'provider',
      render: (v) => <Tag>{v?.toUpperCase()}</Tag>,
    },
    {
      title: 'Holat', dataIndex: 'status',
      render: (s) => <PaymentStatusTag status={s} />,
    },
    {
      title: 'To\'lov sahifasi', dataIndex: 'payment_url',
      render: (url, r) => r.status === 'pending' && url
        ? <Button type="link" size="small" href={url} target="_blank">Ochish</Button>
        : '—',
    },
    {
      title: 'External ID', dataIndex: 'external_id',
      render: (v) => v ? <Text code style={{ fontSize: 11 }}>{v}</Text> : '—',
    },
  ]

  return (
    <div>
      <Title level={4}>💳 Tariflar va to'lovlar</Title>

      {/* Joriy holat */}
      {expiresAt && (
        <Alert
          type={expiringSoon ? 'warning' : 'info'}
          showIcon
          icon={<CalendarOutlined />}
          message={
            expiringSoon
              ? `⚠️ Tarifingiz ${daysLeft} kundan so'ng tugaydi (${expiresAt.format('DD.MM.YYYY')})`
              : `Tarifingiz ${expiresAt.format('DD.MM.YYYY')} gacha amal qiladi (${daysLeft} kun qoldi)`
          }
          style={{ marginBottom: 24 }}
        />
      )}

      {/* Plan cards */}
      <Row gutter={[16, 16]}>
        {(data.plans || []).map((plan) => {
          const isCurrent = plan.id === data.current_plan_id
          const isFree = plan.monthly_price === 0
          return (
            <Col xs={24} md={8} key={plan.id}>
              <Card
                style={{
                  background: PLAN_GRADIENTS[plan.slug] || '#fff',
                  borderRadius: 12,
                  border: isCurrent ? '2px solid #fa8c16' : '1px solid #d9d9d9',
                  boxShadow: isCurrent ? '0 4px 16px rgba(250,140,22,0.2)' : 'none',
                  height: '100%',
                }}
              >
                <Space direction="vertical" size={12} style={{ width: '100%' }}>
                  <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                    <Title level={3} style={{ margin: 0 }}>
                      {plan.slug === 'pro' && <RocketOutlined style={{ color: '#fa8c16' }} />}
                      {plan.slug === 'basic' && <ThunderboltOutlined style={{ color: '#1677ff' }} />}
                      {' '}{plan.name}
                    </Title>
                    {isCurrent && <Tag color="orange">Joriy tarif</Tag>}
                  </Space>

                  <Paragraph type="secondary" style={{ minHeight: 44, marginBottom: 0 }}>
                    {plan.description}
                  </Paragraph>

                  <div>
                    <Text style={{ fontSize: 28, fontWeight: 700 }}>
                      {isFree ? 'Bepul' : `${formatUZS(plan.monthly_price)} so'm`}
                    </Text>
                    {!isFree && <Text type="secondary"> / oy</Text>}
                  </div>

                  <Divider style={{ margin: '4px 0' }} />

                  <Space direction="vertical" size={6} style={{ width: '100%' }}>
                    <Feature label="Catering" enabled={plan.has_catering} icon={<GiftOutlined />} />
                    <Feature label="Yandex Delivery" enabled={plan.has_yandex} icon={<RocketOutlined />} />
                    <Feature label="AI Call Operator" enabled={plan.has_ai_agent} icon={<RobotOutlined />} />
                    <div style={{ fontSize: 13, color: '#666' }}>
                      📦 Buyurtmalar: <b>{plan.order_limit === 0 ? 'cheksiz' : `${plan.order_limit}/oy`}</b>
                    </div>
                    {plan.commission_percent > 0 && (
                      <div style={{ fontSize: 13, color: '#666' }}>
                        💰 Komissiya: <b>{plan.commission_percent}%</b>
                      </div>
                    )}
                  </Space>

                  {/* Action button */}
                  {isCurrent ? (
                    <Button block size="large" disabled icon={<CheckCircleOutlined />}>
                      Joriy tarif
                    </Button>
                  ) : isFree ? (
                    <Button block size="large" disabled>
                      Bepul tarif (downgrade)
                    </Button>
                  ) : !profile?.is_verified ? (
                    <Tooltip title="INN tasdiqlangan bo'lishi kerak. Super-admin bilan bog'laning.">
                      <Button block size="large" disabled icon={<LockOutlined />}>
                        🔒 Tasdiqlash kerak
                      </Button>
                    </Tooltip>
                  ) : (
                    <Space.Compact style={{ width: '100%' }}>
                      <Button
                        block size="large" type="primary"
                        loading={creating === plan.id}
                        icon={<CreditCardOutlined />}
                        onClick={() => openUpgradeModal(plan, 'click')}
                        style={{ background: '#1677ff' }}
                      >
                        Click
                      </Button>
                      <Button
                        block size="large" type="primary"
                        loading={creating === plan.id}
                        icon={<CreditCardOutlined />}
                        onClick={() => openUpgradeModal(plan, 'payme')}
                        style={{ background: '#00a884' }}
                      >
                        Payme
                      </Button>
                    </Space.Compact>
                  )}
                </Space>
              </Card>
            </Col>
          )
        })}
      </Row>

      {/* Faza 6: Upgrade options modal — "Hozir o'tish" vs "Navbat" */}
      <Modal
        title={<><RocketOutlined /> Tarifga o'tish — variantni tanlang</>}
        open={!!upgradeModal}
        onCancel={() => setUpgradeModal(null)}
        footer={null}
        width={620}
      >
        {upgradeModal && (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Alert
              type="info" showIcon
              message={`Tanlangan tarif: ${upgradeModal.plan.name}`}
              description={`Oylik narx: ${formatUZS(upgradeModal.plan.monthly_price)} so'm`}
            />

            {billingStatus?.current_plan && billingStatus.days_left > 0 && (
              <Alert
                type="warning"
                message={`Joriy tarif: ${billingStatus.current_plan.name}`}
                description={`Qoldi: ${billingStatus.days_left} kun.`}
              />
            )}

            <Card hoverable
              onClick={() => handleUpgrade('immediate')}
              style={{ borderColor: '#fa8c16', cursor: 'pointer' }}
            >
              <Space align="start" size={16}>
                <div style={{ fontSize: 32 }}>🚀</div>
                <div>
                  <Text strong style={{ fontSize: 16 }}>Hozir o'tish</Text>
                  <Tag color="orange" style={{ marginLeft: 8 }}>Tavsiya</Tag>
                  <Paragraph type="secondary" style={{ marginBottom: 4, marginTop: 4 }}>
                    Yangi tarif darhol boshlanadi.
                    {billingStatus?.days_left > 0 && (
                      <> Joriy tarifning <b>{billingStatus.days_left} kuni muzlatilib</b> saqlanadi
                      (30 kun ichida ishlatish mumkin).</>
                    )}
                  </Paragraph>
                  <Button type="primary" icon={<ThunderboltFilled />}
                    loading={creating === upgradeModal.plan.id}
                    style={{ background: '#fa8c16', borderColor: '#fa8c16' }}>
                    Hozir o'tish va to'lash
                  </Button>
                </div>
              </Space>
            </Card>

            <Card hoverable
              onClick={() => handleUpgrade('queued')}
              style={{ borderColor: '#1677ff', cursor: 'pointer' }}
            >
              <Space align="start" size={16}>
                <div style={{ fontSize: 32 }}>📅</div>
                <div>
                  <Text strong style={{ fontSize: 16 }}>Navbat bilan o'tish</Text>
                  <Paragraph type="secondary" style={{ marginBottom: 4, marginTop: 4 }}>
                    To'lov hozir, lekin yangi tarif faqat
                    <b> {billingStatus?.current_plan?.name || 'joriy tarif'} 30-kuni tugashi bilan </b>
                    avtomatik faollashadi. Hech narsa muzlatilmaydi.
                  </Paragraph>
                  <Button type="primary" icon={<ClockCircleOutlined />}
                    loading={creating === upgradeModal.plan.id}>
                    Navbat bilan to'lash
                  </Button>
                </div>
              </Space>
            </Card>

            <Text type="secondary" style={{ fontSize: 12 }}>
              Provayder: <b>{upgradeModal.provider.toUpperCase()}</b>.
              To'lov muvaffaqiyatli bo'lgach, tarif tanlangan variantga ko'ra qo'llanadi.
            </Text>
          </Space>
        )}
      </Modal>

      {/* Payment modal */}
      <Modal
        title="💳 To'lovga o'tish"
        open={!!paymentModal}
        onCancel={() => setPaymentModal(null)}
        footer={null}
        width={500}
      >
        {paymentModal && (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Alert
              type="info" showIcon
              message={`Summa: ${formatUZS(paymentModal.amount_uzs)} so'm`}
              description={`Provayder: ${paymentModal.provider.toUpperCase()}`}
            />

            <Text>To'lov tugmasini bosing — yangi sahifa ochiladi:</Text>
            <Button
              type="primary" size="large" block
              icon={<CreditCardOutlined />}
              href={paymentModal.url}
              target="_blank"
            >
              To'lash sahifasini ochish
            </Button>

            {paymentModal.url?.includes('mock.payments.local') && (
              <Alert
                type="warning" showIcon
                message="Bu test (mock) to'lov"
                description="Real provayder hali ulanmagan. Test uchun pastdagi tugmani bosing."
                action={
                  <Button onClick={handleMockComplete} type="primary" danger size="small">
                    Mock complete
                  </Button>
                }
              />
            )}

            <Text type="secondary" style={{ fontSize: 12 }}>
              Order ID: <code>{paymentModal.merchant_trans_id}</code>
            </Text>
          </Space>
        )}
      </Modal>

      {/* Tarix */}
      <Title level={5} style={{ marginTop: 32 }}>
        <HistoryOutlined /> To'lovlar tarixi
      </Title>
      {payments.length === 0 ? (
        <Empty description="Hali to'lovlar yo'q" />
      ) : (
        <Table
          dataSource={payments}
          columns={paymentColumns}
          rowKey="id"
          size="small"
          pagination={{ pageSize: 10 }}
          scroll={{ x: 700 }}
        />
      )}
    </div>
  )
}

function Feature({ label, enabled, icon }) {
  return (
    <div style={{ fontSize: 13 }}>
      {enabled
        ? <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 6 }} />
        : <CloseCircleOutlined style={{ color: '#bfbfbf', marginRight: 6 }} />
      }
      <span style={{ color: enabled ? '#262626' : '#999' }}>
        {icon} {label}
      </span>
    </div>
  )
}
