import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Table, Tag, Typography, Statistic, Row, Col, Spin, Button, Drawer,
  Empty, message, Tooltip,
} from 'antd'
import {
  ArrowLeftOutlined, ReloadOutlined, EyeOutlined,
  ClockCircleOutlined, DollarOutlined, PhoneOutlined,
} from '@ant-design/icons'
import { getAiLogs, getAiLogDetail, getAiStats } from '../../api'
import { useAuthStore } from '../../store/auth'

const { Title, Text } = Typography

const REASON_TAGS = {
  confirmed: { color: 'green', label: '✓ Buyurtma' },
  transferred: { color: 'orange', label: 'Catering uzatildi' },
  time_limit: { color: 'red', label: 'Vaqt limiti' },
  outside_work_hours: { color: 'default', label: 'Yopiq vaqt' },
  user_hangup: { color: 'blue', label: 'Foydalanuvchi uzdi' },
  error: { color: 'magenta', label: 'Xato' },
}

function ReasonTag({ reason }) {
  const meta = REASON_TAGS[reason] || { color: 'default', label: reason || '—' }
  return <Tag color={meta.color}>{meta.label}</Tag>
}

function fmtDuration(seconds) {
  if (!seconds) return '0s'
  const s = Math.round(seconds)
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}m ${s % 60}s`
}

function fmtCost(usd) {
  if (!usd) return '$0'
  return `$${usd.toFixed(4)}`
}

export default function AiLogs() {
  const navigate = useNavigate()
  const { currentRestaurantId: restaurantId } = useAuthStore()
  const restParams = restaurantId ? { restaurant_id: restaurantId } : {}

  const [logs, setLogs] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [detail, setDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const [lRes, sRes] = await Promise.all([
        getAiLogs({ ...restParams, limit: 100 }),
        getAiStats({ ...restParams, days: 30 }).catch(() => ({ data: null })),
      ])
      setLogs(lRes.data?.items || [])
      setStats(sRes.data || null)
    } catch (e) {
      message.error("Ma'lumotlarni yuklashda xato")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [restaurantId])

  const openDetail = async (id) => {
    setDetailLoading(true)
    setDetail({})
    try {
      const r = await getAiLogDetail(id, restParams)
      setDetail(r.data)
    } catch (e) {
      message.error("Tafsilotni yuklab bo'lmadi")
      setDetail(null)
    } finally {
      setDetailLoading(false)
    }
  }

  const columns = [
    {
      title: 'Vaqt', dataIndex: 'started_at', width: 140,
      render: (v) => v ? new Date(v).toLocaleString('uz-UZ', { hour12: false }) : '—',
    },
    { title: 'Telefon', dataIndex: 'user_phone', width: 130,
      render: (v) => v ? <Text code>{v}</Text> : '—' },
    {
      title: 'Davomiyligi', dataIndex: 'duration_seconds', width: 100,
      render: (v) => fmtDuration(v),
    },
    {
      title: 'Suhbat', dataIndex: 'message_count', width: 80,
      render: (v) => `${v || 0} turn`,
    },
    {
      title: 'Xarajat', dataIndex: 'cost_usd', width: 90,
      render: (v) => <Tooltip title={`Tokens: ${v ? '~' : '0'}`}>{fmtCost(v)}</Tooltip>,
    },
    {
      title: 'Natija', dataIndex: 'ended_reason', width: 140,
      render: (v, r) => (
        <>
          <ReasonTag reason={v} />
          {r.order_id && <Tag color="cyan">№{r.order_id}</Tag>}
        </>
      ),
    },
    {
      title: '', width: 50,
      render: (_, r) => (
        <Button size="small" icon={<EyeOutlined />} onClick={() => openDetail(r.id)} />
      ),
    },
  ]

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ marginBottom: 24 }}>
        <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/settings')} style={{ marginBottom: 8, padding: 0, color: '#6b7280' }}>
          Sozlamalar
        </Button>
        <Title level={3} style={{ marginBottom: 4, marginTop: 0 }}>
          AI Operator — Suhbat tarixi
        </Title>
        <Text type="secondary">
          Oxirgi 100 ta AI suhbati; har bir suhbat tafsiloti va transkripti
        </Text>
      </div>

      {/* Statistika */}
      {stats && (
        <Row gutter={16} style={{ marginBottom: 24 }}>
          <Col xs={12} md={6}>
            <Card><Statistic title="Suhbatlar (30 kun)" value={stats.total_calls} prefix={<PhoneOutlined />} /></Card>
          </Col>
          <Col xs={12} md={6}>
            <Card><Statistic title="Buyurtmalar" value={stats.orders_created} valueStyle={{ color: '#52c41a' }} /></Card>
          </Col>
          <Col xs={12} md={6}>
            <Card>
              <Statistic
                title="Jami xarajat (30 kun)"
                value={(stats.total_cost_usd || 0).toFixed(2)}
                prefix={<DollarOutlined />}
                suffix="USD"
              />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card>
              <Statistic
                title="Jami davomiyligi"
                value={fmtDuration(stats.total_duration_seconds)}
                prefix={<ClockCircleOutlined />}
              />
            </Card>
          </Col>
        </Row>
      )}

      <Card
        title="Suhbatlar"
        extra={<Button icon={<ReloadOutlined />} onClick={load} size="small">Yangilash</Button>}
        styles={{ body: { padding: 0 } }}
      >
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center' }}><Spin /></div>
        ) : logs.length === 0 ? (
          <Empty description="Hali AI suhbatlari yo'q" style={{ padding: 40 }} />
        ) : (
          <Table
            rowKey="id"
            dataSource={logs}
            columns={columns}
            pagination={{ pageSize: 20 }}
            size="small"
            scroll={{ x: 800 }}
          />
        )}
      </Card>

      <Drawer
        title={detail?.id ? `Suhbat #${detail.id}` : 'Yuklanmoqda...'}
        open={!!detail}
        onClose={() => setDetail(null)}
        width={620}
      >
        {detailLoading ? (
          <Spin />
        ) : detail?.id ? (
          <>
            <Row gutter={[16, 12]} style={{ marginBottom: 16 }}>
              <Col span={12}><Text type="secondary">Telefon:</Text> <Text code>{detail.user_phone || '—'}</Text></Col>
              <Col span={12}><Text type="secondary">Boshi:</Text> {detail.started_at ? new Date(detail.started_at).toLocaleString('uz-UZ', { hour12: false }) : '—'}</Col>
              <Col span={12}><Text type="secondary">Davomiyligi:</Text> {fmtDuration(detail.duration_seconds)}</Col>
              <Col span={12}><Text type="secondary">Xarajat:</Text> {fmtCost(detail.cost_usd)}</Col>
              <Col span={12}><Text type="secondary">Tokenlar:</Text> {detail.tokens_in} → {detail.tokens_out}</Col>
              <Col span={12}><Text type="secondary">Natija:</Text> <ReasonTag reason={detail.ended_reason} /></Col>
              {detail.order_id && (
                <Col span={24}><Text type="secondary">Buyurtma:</Text> <Tag color="cyan">№{detail.order_id}</Tag></Col>
              )}
            </Row>

            <Title level={5}>Transkripti</Title>
            {(detail.transcript || []).length === 0 ? (
              <Empty description="Transkripti yo'q" />
            ) : (
              <div style={{ maxHeight: 500, overflow: 'auto' }}>
                {(detail.transcript || []).map((m, i) => (
                  <div key={i} style={{
                    background: m.role === 'user' ? '#f0f5ff' : '#f6ffed',
                    padding: 10, borderRadius: 8, marginBottom: 8,
                  }}>
                    <Text strong style={{ fontSize: 12, color: '#6b7280' }}>
                      {m.role === 'user' ? '👤 Mijoz' : '🤖 AI'}
                    </Text>
                    <div style={{ marginTop: 4, whiteSpace: 'pre-wrap' }}>{m.content}</div>
                  </div>
                ))}
              </div>
            )}
          </>
        ) : null}
      </Drawer>
    </div>
  )
}
