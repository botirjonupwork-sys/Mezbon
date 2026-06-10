import { useEffect, useState, useRef } from 'react'
import {
  Card, Button, Space, Tag, Table, Typography, Alert, Spin,
  Badge, Tooltip, Row, Col, Statistic, message, Popconfirm,
} from 'antd'
import {
  ReloadOutlined, RobotOutlined, CheckCircleOutlined, CloseCircleOutlined,
  WarningOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import { getBotsStatus, restartBots, restartBot } from '../api'

const { Title, Text } = Typography

export default function Bots() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [restarting, setRestarting] = useState(false)
  const [restartingId, setRestartingId] = useState(null)
  const intervalRef = useRef(null)

  const fetchStatus = async () => {
    try {
      const res = await getBotsStatus()
      setData(res.data)
    } catch (e) {
      // silent for polling
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStatus()
    intervalRef.current = setInterval(fetchStatus, 15000)  // har 15 soniya
    return () => clearInterval(intervalRef.current)
  }, [])

  const onRestart = async () => {
    setRestarting(true)
    try {
      const r = await restartBots()
      if (r.data?.ok) {
        message.success(r.data?.message || 'Barcha botlar restart signali yuborildi (~10s)')
        setTimeout(fetchStatus, 12000)
      } else {
        message.error(r.data?.error || 'Restart xato')
      }
    } catch (e) {
      message.error(e?.response?.data?.detail || 'Xato')
    } finally {
      setRestarting(false)
    }
  }

  const onRestartOne = async (restaurantId) => {
    setRestartingId(restaurantId)
    try {
      const r = await restartBot(restaurantId)
      message.success(r.data?.message || 'Bot restart signali yuborildi (~10s)')
      setTimeout(fetchStatus, 12000)
    } catch (e) {
      message.error(e?.response?.data?.detail || 'Xato')
    } finally {
      setRestartingId(null)
    }
  }

  const renderBotCell = (bot) => {
    if (!bot?.configured) {
      return <Tag color="default">Token yo'q</Tag>
    }
    if (bot.online) {
      return (
        <Space direction="vertical" size={0}>
          <Tag color="green" icon={<CheckCircleOutlined />}>
            Online
          </Tag>
          <Text style={{ fontSize: 11, color: '#666' }}>
            @{bot.username || '—'}
          </Text>
        </Space>
      )
    }
    return (
      <Tooltip title={bot.error || ''}>
        <Tag color="red" icon={<CloseCircleOutlined />}>
          Offline
        </Tag>
      </Tooltip>
    )
  }

  const columns = [
    { title: 'ID', dataIndex: 'restaurant_id', width: 60, render: id => <b>#{id}</b> },
    {
      title: 'Restoran',
      render: (_, r) => (
        <Space direction="vertical" size={0}>
          <b>{r.restaurant_name}</b>
          <Space size={4}>
            <Tag color={r.status === 'active' ? 'green' : 'default'} style={{ fontSize: 10 }}>{r.status}</Tag>
            {r.subscription_status !== 'active' && (
              <Tag color="orange" style={{ fontSize: 10 }}>{r.subscription_status}</Tag>
            )}
          </Space>
        </Space>
      ),
    },
    {
      title: 'Customer Bot', dataIndex: 'customer_bot', width: 160,
      render: renderBotCell,
    },
    {
      title: 'Courier Bot', dataIndex: 'courier_bot', width: 160,
      render: renderBotCell,
    },
    {
      title: 'Amal', width: 120,
      render: (_, r) => {
        const hasBot = r.customer_bot?.configured || r.courier_bot?.configured
        return (
          <Popconfirm
            title="Shu restoran botini restart qilasizmi?"
            description="~10 soniya ichida qayta ishga tushadi."
            onConfirm={() => onRestartOne(r.restaurant_id)}
            disabled={!hasBot}
          >
            <Button
              size="small" icon={<ThunderboltOutlined />}
              loading={restartingId === r.restaurant_id}
              disabled={!hasBot}
            >
              Restart
            </Button>
          </Popconfirm>
        )
      },
    },
  ]

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '80px auto' }} />

  const summary = data?.summary || {}

  return (
    <div>
      <Space style={{ marginBottom: 16, justifyContent: 'space-between', width: '100%' }}>
        <Title level={3} style={{ margin: 0 }}>
          <RobotOutlined /> Botlar holati
        </Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={fetchStatus}>Yangilash</Button>
          <Popconfirm
            title="BARCHA botlarni qayta ishga tushirish?"
            description="Har bir restoran boti restart qilinadi. ~10 soniya."
            onConfirm={onRestart}
          >
            <Button type="primary" icon={<ThunderboltOutlined />} loading={restarting}>
              Hammasini restart
            </Button>
          </Popconfirm>
        </Space>
      </Space>

      <Alert type="info" showIcon style={{ marginBottom: 16 }}
        message="Bot menejeri har bir restoran botini alohida boshqaradi"
        description="Restart tugmasi DB signal yuboradi — bot menejeri (bot/manager.py) ~10s ichida botni qayta ishga tushiradi. Har bir restoran uchun alohida 'Restart', yoki yuqorida 'Hammasini restart'. Token o'zgartirilganda restart bosing." />

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="Restoranlar"
              value={summary.total_restaurants || 0}
              prefix={<RobotOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="Customer botlar online"
              value={summary.customer_bots_online || 0}
              suffix={`/ ${summary.customer_bots_configured || 0}`}
              valueStyle={{ color: '#52c41a' }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="Courier botlar online"
              value={summary.courier_bots_online || 0}
              suffix={`/ ${summary.courier_bots_configured || 0}`}
              valueStyle={{ color: '#1890ff' }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="Token yo'q"
              value={(summary.total_restaurants || 0) - (summary.customer_bots_configured || 0)}
              prefix={<WarningOutlined />}
              valueStyle={{ color: '#fa8c16' }}
            />
          </Card>
        </Col>
      </Row>

      <Card>
        <Table
          rowKey="restaurant_id" size="middle"
          dataSource={data?.items || []}
          columns={columns}
          pagination={false}
          locale={{ emptyText: 'Restoran yo\'q' }}
        />
      </Card>

      <div style={{ marginTop: 12, color: '#888', fontSize: 12 }}>
        💡 Avtomatik yangilanadi har 15 soniyada. Online holat — Telegram bilan jonli ulanish tekshiruvi (getMe API).
      </div>
    </div>
  )
}
