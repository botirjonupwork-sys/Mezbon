import { useEffect, useState } from 'react'
import { Card, Table, Tag, Typography, Alert, Statistic, Row, Col, Spin } from 'antd'
import {
  PhoneOutlined, RobotOutlined, DollarOutlined, ClockCircleOutlined,
} from '@ant-design/icons'
import { getRestaurants, getAiAggregateStats } from '../api'

const { Title, Text } = Typography

function fmtDuration(seconds) {
  if (!seconds) return '0s'
  const s = Math.round(seconds)
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
}

export default function AiAgent() {
  const [loading, setLoading] = useState(true)
  const [restaurants, setRestaurants] = useState([])
  const [stats, setStats] = useState(null)

  useEffect(() => {
    Promise.all([
      getRestaurants().catch(() => ({ data: [] })),
      getAiAggregateStats({ days: 30 }).catch(() => ({ data: null })),
    ])
      .then(([rRes, sRes]) => {
        setRestaurants(rRes.data || [])
        setStats(sRes.data || null)
      })
      .finally(() => setLoading(false))
  }, [])

  const aiCount = restaurants.filter(r => r.ai_agent_enabled).length
  const totalRestaurants = restaurants.length

  const restaurantCostMap = {}
  if (stats?.by_restaurant) {
    stats.by_restaurant.forEach(r => { restaurantCostMap[r.restaurant_id] = r })
  }

  const columns = [
    { title: 'Restoran', dataIndex: 'name', key: 'name' },
    {
      title: 'Tarif', dataIndex: 'plan_name', key: 'plan',
      render: (v) => <Tag color="purple">{v || '—'}</Tag>,
    },
    {
      title: 'AI yoqilgan?', dataIndex: 'ai_agent_enabled', key: 'enabled',
      render: (v) => v ? <Tag color="green">✓ Yoqilgan</Tag> : <Tag>O'chiq</Tag>,
    },
    {
      title: 'Suhbatlar (30k)', key: 'calls',
      render: (_, r) => restaurantCostMap[r.id]?.calls || 0,
    },
    {
      title: 'Buyurtmalar', key: 'orders',
      render: (_, r) => restaurantCostMap[r.id]?.orders || 0,
    },
    {
      title: 'Xarajat (USD)', key: 'cost',
      sorter: (a, b) => (restaurantCostMap[a.id]?.cost_usd || 0) - (restaurantCostMap[b.id]?.cost_usd || 0),
      render: (_, r) => {
        const c = restaurantCostMap[r.id]?.cost_usd || 0
        return c > 0 ? <Text strong>${c.toFixed(4)}</Text> : '—'
      },
    },
  ]

  return (
    <div>
      <Title level={3}>
        <PhoneOutlined style={{ marginRight: 8, color: '#9333ea' }} />
        AI Telefon Operator
      </Title>
      <Text type="secondary" style={{ display: 'block', marginBottom: 24 }}>
        Restoranlarning AI Operator sozlamalari va foydalanish statistikasi
      </Text>

      <Alert
        type="info"
        showIcon
        message="AI Operator nima va qanday ishlaydi"
        description={
          <div style={{ lineHeight: 1.8 }}>
            <div>• Mijoz restoran raqamiga/Telegram'ga ovoz xabar yuboradi → AI javob beradi</div>
            <div>• AI <b>faqat shu restoranning menyusidan</b> mahsulot taklif qiladi, narx va manzil so'raydi</div>
            <div>• Buyurtmani avtomatik DB'ga yozadi; Catering bo'lsa operatorga uzatadi</div>
            <div>• Faqat <b>has_ai_agent</b> tarifdagi restoranlar foydalanishi mumkin</div>
            <div>• LLM va API kalit: <code>Sozlamalar → AI Operator</code> tab'ida</div>
            <div>• Restoran admin panelida faqat ovoz va maxsus prompt sozlanadi</div>
          </div>
        }
        style={{ marginBottom: 24 }}
      />

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="Jami restoran" value={totalRestaurants} prefix={<RobotOutlined />} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="AI yoqilgan"
              value={aiCount}
              valueStyle={{ color: '#52c41a' }}
              suffix={totalRestaurants > 0 ? `(${Math.round(aiCount / totalRestaurants * 100)}%)` : ''}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="Suhbatlar (30 kun)"
              value={stats?.global?.total_calls || 0}
              prefix={<PhoneOutlined />}
              suffix={
                stats?.global?.orders_created
                  ? <Text type="secondary" style={{ fontSize: 13 }}>{` (${stats.global.orders_created} buyurtma)`}</Text>
                  : null
              }
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="Jami xarajat (30 kun)"
              value={(stats?.global?.total_cost_usd || 0).toFixed(2)}
              prefix={<DollarOutlined />}
              suffix="USD"
            />
          </Card>
        </Col>
      </Row>

      {stats?.global?.total_duration_seconds > 0 && (
        <Alert
          type="success" showIcon style={{ marginBottom: 24 }}
          icon={<ClockCircleOutlined />}
          message={`Jami suhbat vaqti: ${fmtDuration(stats.global.total_duration_seconds)} — ${(stats.global.tokens_in + stats.global.tokens_out).toLocaleString()} ta token`}
        />
      )}

      <Card title="Restoranlar bo'yicha foydalanish" styles={{ body: { padding: 0 } }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center' }}><Spin /></div>
        ) : (
          <Table
            dataSource={restaurants}
            columns={columns}
            rowKey="id"
            pagination={{ pageSize: 20 }}
          />
        )}
      </Card>
    </div>
  )
}
