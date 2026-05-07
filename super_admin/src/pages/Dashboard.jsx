import { useEffect, useState } from 'react'
import {
  Row, Col, Card, Statistic, Typography, Spin, Alert, Tag, Space,
} from 'antd'
import {
  ShopOutlined, ShoppingCartOutlined, DollarOutlined,
  HeartOutlined, ThunderboltOutlined, ApiOutlined,
} from '@ant-design/icons'
import { Line, Pie } from '@ant-design/charts'
import dayjs from 'dayjs'
import { getSuperAdminStats, getHealth } from '../api'
import { fmtTashkent } from '../utils/datetime'

const { Title, Text } = Typography

function fmtUZS(v) {
  return new Intl.NumberFormat('uz-UZ').format(Math.round(v || 0))
}

function HealthBadge({ status }) {
  if (status === 'ok')      return <Tag color="green">✓ ok</Tag>
  if (status === 'skipped') return <Tag color="default">— skipped</Tag>
  if (status === 'error')   return <Tag color="red">✗ error</Tag>
  return <Tag>{status || '?'}</Tag>
}

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState(null)

  useEffect(() => {
    let alive = true
    Promise.all([
      getSuperAdminStats({ days: 30 }),
      getHealth().catch((e) => ({ data: { error: e.message } })),
    ])
      .then(([s, h]) => {
        if (!alive) return
        setStats(s.data); setHealth(h.data)
      })
      .catch((e) => alive && setErr(e?.response?.data?.detail || 'Yuklashda xato'))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 100 }} />
  if (err)     return <Alert type="error" message={err} showIcon />

  const lineData = (stats?.series || []).flatMap((d) => [
    { date: d.date, value: d.revenue, type: "Tushum (so'm)" },
    { date: d.date, value: d.orders * 50000, type: 'Buyurtmalar (×50k)' },
  ])

  const pieData = Object.entries(stats?.plan_distribution || {})
    .map(([slug, n]) => ({ type: slug, value: n }))
    .filter((d) => d.value > 0)

  return (
    <div>
      <Title level={3} style={{ marginBottom: 4 }}>👑 Platforma boshqaruvi</Title>
      <Text type="secondary">
        Barcha restoranlar bo'yicha umumiy holat — oxirgi {stats?.period_days || 30} kun
      </Text>

      {/* Stat kartochkalar */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="Restoranlar"
              value={stats?.restaurants?.total || 0}
              prefix={<ShopOutlined />}
              suffix={<Text type="secondary">/ {stats?.restaurants?.active} aktiv</Text>}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="Bugungi buyurtmalar"
              value={stats?.orders?.today || 0}
              prefix={<ShoppingCartOutlined />}
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="Bugungi tushum"
              value={fmtUZS(stats?.revenue?.today_uzs)}
              suffix="so'm"
              prefix={<DollarOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="Umumiy tushum"
              value={fmtUZS(stats?.revenue?.total_uzs)}
              suffix="so'm"
              prefix={<ThunderboltOutlined />}
              valueStyle={{ color: '#fa8c16' }}
            />
          </Card>
        </Col>
      </Row>

      {/* Health widget */}
      <Card
        title={<><HeartOutlined /> Tizim sog'lig'i (Health Check)</>}
        size="small"
        style={{ marginTop: 16 }}
      >
        {health?.error ? (
          <Alert type="error" message="/health endpoint javob bermadi" description={String(health.error)} />
        ) : (
          <Row gutter={[16, 8]}>
            <Col xs={24} md={6}>
              <Space direction="vertical" size={2}>
                <Text type="secondary">Database</Text>
                <Space>
                  <HealthBadge status={health?.components?.database?.status} />
                  <Text>{health?.components?.database?.driver}</Text>
                  {health?.components?.database?.latency_ms != null && (
                    <Text type="secondary">{health.components.database.latency_ms} ms</Text>
                  )}
                </Space>
              </Space>
            </Col>
            <Col xs={24} md={6}>
              <Space direction="vertical" size={2}>
                <Text type="secondary">OpenAI</Text>
                <HealthBadge status={health?.components?.openai?.status} />
              </Space>
            </Col>
            <Col xs={24} md={6}>
              <Space direction="vertical" size={2}>
                <Text type="secondary">Yandex Delivery</Text>
                <HealthBadge status={health?.components?.yandex?.status} />
              </Space>
            </Col>
            <Col xs={24} md={6}>
              <Space direction="vertical" size={2}>
                <Text type="secondary">Server vaqti ({health?.server_time?.timezone})</Text>
                <Text strong>
                  <ApiOutlined />{' '}
                  {fmtTashkent(health?.server_time?.iso, 'YYYY-MM-DD HH:mm:ss')}
                </Text>
              </Space>
            </Col>
          </Row>
        )}
      </Card>

      {/* Grafiklar */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={16}>
          <Card title="Tushum dinamikasi (so'nggi 30 kun)" size="small">
            {lineData.length === 0 ? (
              <Alert type="info" message="Bu davrda buyurtma yo'q" />
            ) : (
              <Line
                data={lineData}
                xField="date"
                yField="value"
                seriesField="type"
                height={280}
                smooth
                point={{ size: 3 }}
                color={['#722ed1', '#1677ff']}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="Tarif taqsimoti" size="small">
            {pieData.length === 0 ? (
              <Alert type="info" message="Hech qaysi restoran tarifda emas" />
            ) : (
              <Pie
                data={pieData}
                angleField="value"
                colorField="type"
                height={280}
                radius={0.85}
                label={{ type: 'inner', content: '{name}\n{percentage}' }}
              />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}
