import { useEffect, useState } from 'react'
import { Card, Table, Tag, Typography, Alert, Statistic, Row, Col, Spin, Button } from 'antd'
import { PhoneOutlined, RobotOutlined } from '@ant-design/icons'
import { getRestaurants } from '../api'

const { Title, Text } = Typography


export default function AiAgent() {
  const [loading, setLoading] = useState(true)
  const [restaurants, setRestaurants] = useState([])

  useEffect(() => {
    getRestaurants()
      .then(r => setRestaurants(r.data || []))
      .catch(() => setRestaurants([]))
      .finally(() => setLoading(false))
  }, [])

  // AI agent yoqilgan restoranlar va tariflar bo'yicha statistika
  const aiCount = restaurants.filter(r => r.ai_agent_enabled).length
  const totalRestaurants = restaurants.length

  const columns = [
    { title: 'Restoran', dataIndex: 'name', key: 'name' },
    { title: 'Tarif', dataIndex: 'plan_name', key: 'plan',
      render: (v) => <Tag color="purple">{v || '—'}</Tag> },
    { title: 'AI yoqilgan?', dataIndex: 'ai_agent_enabled', key: 'enabled',
      render: (v) => v ? <Tag color="green">✓ Yoqilgan</Tag> : <Tag>O'chiq</Tag> },
    { title: 'Provider', dataIndex: 'ai_agent_provider', key: 'provider',
      render: (v) => v ? <Tag>{v}</Tag> : '—' },
    { title: 'Model', dataIndex: 'ai_agent_model', key: 'model',
      render: (v) => v || '—' },
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
            <div>• Mijoz restoran raqamiga qo'ng'iroq qiladi → Vapi/Retell oraqali AI javob beradi</div>
            <div>• AI menyu, narx, manzil so'raydi, buyurtmani DB'ga yozadi</div>
            <div>• Catering buyurtma bo'lsa operatorga uzatadi</div>
            <div>• Faqat <b>has_ai_agent</b> tarifdagi restoranlar foydalanishi mumkin</div>
            <div>• Restoran admin panelida: <code>Sozlamalar → AI Operator</code></div>
          </div>
        }
        style={{ marginBottom: 24 }}
      />

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={8}>
          <Card>
            <Statistic title="Jami restoran" value={totalRestaurants} prefix={<RobotOutlined />} />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card>
            <Statistic title="AI yoqilgan" value={aiCount} valueStyle={{ color: '#52c41a' }} />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card>
            <Statistic
              title="Foydalanish"
              value={totalRestaurants > 0 ? Math.round(aiCount / totalRestaurants * 100) : 0}
              suffix="%"
            />
          </Card>
        </Col>
      </Row>

      <Card title="Restoranlar ro'yxati" styles={{ body: { padding: 0 } }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center' }}><Spin /></div>
        ) : (
          <Table dataSource={restaurants} columns={columns} rowKey="id" pagination={{ pageSize: 20 }} />
        )}
      </Card>
    </div>
  )
}
