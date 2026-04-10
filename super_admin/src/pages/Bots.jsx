import { useEffect, useState, useRef } from 'react'
import {
  Card, Button, Space, Tag, Table, Typography, Alert, Spin,
  Badge, Tooltip, Row, Col, Statistic, Divider
} from 'antd'
import {
  PlayCircleOutlined, StopOutlined, ReloadOutlined,
  RobotOutlined, CheckCircleOutlined, CloseCircleOutlined,
  CopyOutlined, FileTextOutlined
} from '@ant-design/icons'
import { getBotsStatus, startBots, stopBots, restartBots } from '../api'
import { message } from 'antd'

const { Title, Text } = Typography

export default function Bots() {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState('')
  const logRef = useRef(null)
  const intervalRef = useRef(null)

  const fetchStatus = async () => {
    try {
      const res = await getBotsStatus()
      setStatus(res.data)
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStatus()
    intervalRef.current = setInterval(fetchStatus, 4000)
    return () => clearInterval(intervalRef.current)
  }, [])

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [status?.logs])

  const handleAction = async (action, label) => {
    setActionLoading(action)
    try {
      const fn = action === 'start' ? startBots : action === 'stop' ? stopBots : restartBots
      const res = await fn()
      const st = res.data?.status
      if (st === 'already_running') message.info('Botlar allaqachon ishlayapti')
      else if (st === 'not_running') message.info('Botlar ishlayotgan emas')
      else message.success(`${label} bajarildi`)
      await fetchStatus()
    } catch (e) {
      message.error(e.response?.data?.detail || 'Xato yuz berdi')
    } finally {
      setActionLoading('')
    }
  }

  const copyCommand = () => {
    navigator.clipboard.writeText('python scripts/run_all_bots.py')
    message.success('Nusxalandi')
  }

  const botColumns = [
    {
      title: 'Restoran',
      dataIndex: 'name',
      render: (v, r) => (
        <Space direction="vertical" size={0}>
          <b>{v}</b>
          <Text type="secondary" style={{ fontSize: 11 }}>{r.slug}</Text>
        </Space>
      ),
    },
    {
      title: 'Customer Bot',
      dataIndex: 'has_bot',
      width: 140,
      render: (v) => v
        ? <Tag color="green" icon={<CheckCircleOutlined />}>Token bor</Tag>
        : <Tag color="red" icon={<CloseCircleOutlined />}>Token yo'q</Tag>,
    },
    {
      title: 'Kuryer Bot',
      dataIndex: 'has_courier_bot',
      width: 140,
      render: (v) => v
        ? <Tag color="green" icon={<CheckCircleOutlined />}>Token bor</Tag>
        : <Tag color="orange" icon={<CloseCircleOutlined />}>Token yo'q</Tag>,
    },
    {
      title: '',
      width: 120,
      render: (_, r) => (
        <Button size="small" type="link"
          href={`/restaurants/${r.id}/edit`}
          onClick={(e) => { e.preventDefault(); window.location.href = `/restaurants/${r.id}/edit` }}>
          Token qo'shish →
        </Button>
      ),
    },
  ]

  const isRunning = status?.running
  const botsWithToken = status?.restaurants?.filter(r => r.has_bot || r.has_courier_bot).length ?? 0
  const totalBots = status?.restaurants?.length ?? 0

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '80px auto' }} />

  return (
    <div>
      <Title level={4} style={{ marginBottom: 24 }}>
        <RobotOutlined style={{ marginRight: 8 }} />
        Bot boshqaruvi
      </Title>

      {/* Holat kartasi */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={8}>
          <Card>
            <Statistic
              title="Bot holati"
              value={isRunning ? 'Ishlayapti' : 'To\'xtatilgan'}
              valueStyle={{ color: isRunning ? '#52c41a' : '#ff4d4f', fontWeight: 700 }}
              prefix={
                isRunning
                  ? <Badge status="processing" color="green" />
                  : <Badge status="error" />
              }
            />
            {status?.pid && (
              <Text type="secondary" style={{ fontSize: 11 }}>PID: {status.pid}</Text>
            )}
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card>
            <Statistic
              title="Token bor restoranlar"
              value={botsWithToken}
              suffix={`/ ${totalBots}`}
              prefix={<RobotOutlined style={{ color: '#722ed1' }} />}
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 12, color: '#999', marginBottom: 8 }}>Qo'lda ishlatish</div>
              <Space>
                <Text code style={{ fontSize: 12 }}>python scripts/run_all_bots.py</Text>
                <Tooltip title="Nusxalash">
                  <Button size="small" icon={<CopyOutlined />} onClick={copyCommand} />
                </Tooltip>
              </Space>
            </div>
          </Card>
        </Col>
      </Row>

      {/* Boshqaruv tugmalari */}
      <Card
        title="Amallar"
        style={{ marginBottom: 24 }}
        extra={
          <Button size="small" icon={<ReloadOutlined />} onClick={fetchStatus} loading={loading}>
            Yangilash
          </Button>
        }
      >
        {botsWithToken === 0 && (
          <Alert
            message="Hech qanday bot tokeni kiritilmagan"
            description="Restoranlar sahifasida restoranlarni tahrirlash orqali bot_token va courier_bot_token kiriting."
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
          />
        )}

        <Space size="middle" wrap>
          <Button
            type="primary"
            size="large"
            icon={<PlayCircleOutlined />}
            loading={actionLoading === 'start'}
            disabled={isRunning || botsWithToken === 0}
            onClick={() => handleAction('start', 'Ishga tushirildi')}
            style={{ background: '#52c41a', borderColor: '#52c41a', minWidth: 160 }}
          >
            Ishga tushirish
          </Button>

          <Button
            size="large"
            danger
            icon={<StopOutlined />}
            loading={actionLoading === 'stop'}
            disabled={!isRunning}
            onClick={() => handleAction('stop', 'To\'xtatildi')}
            style={{ minWidth: 160 }}
          >
            To'xtatish
          </Button>

          <Button
            size="large"
            icon={<ReloadOutlined />}
            loading={actionLoading === 'restart'}
            disabled={botsWithToken === 0}
            onClick={() => handleAction('restart', 'Qayta ishga tushirildi')}
            style={{ minWidth: 160 }}
          >
            Restart
          </Button>
        </Space>

        <Divider />

        {isRunning ? (
          <Alert
            message={`Barcha botlar ishlayapti (PID: ${status.pid})`}
            type="success"
            showIcon
          />
        ) : (
          <Alert
            message="Botlar hozir ishlamayapti"
            description="Yuqoridagi 'Ishga tushirish' tugmasini bosing."
            type="info"
            showIcon
          />
        )}
      </Card>

      {/* Restoranlar jadval */}
      <Card title="Restoranlar — bot holati" style={{ marginBottom: 24 }}>
        <Table
          dataSource={status?.restaurants ?? []}
          columns={botColumns}
          rowKey="id"
          size="small"
          pagination={false}
          rowClassName={(r) => (!r.has_bot && !r.has_courier_bot) ? 'ant-table-row-disabled' : ''}
        />
      </Card>

      {/* Log */}
      <Card
        title={<><FileTextOutlined /> Bot log (oxirgi 40 qator)</>}
        extra={
          <Tag color={isRunning ? 'green' : 'default'}>
            {isRunning ? 'Yangilanmoqda...' : 'To\'xtatilgan'}
          </Tag>
        }
      >
        <div
          ref={logRef}
          style={{
            background: '#1a1a2e',
            color: '#e0e0e0',
            fontFamily: 'monospace',
            fontSize: 12,
            padding: 16,
            borderRadius: 6,
            height: 320,
            overflowY: 'auto',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all',
          }}
        >
          {(status?.logs ?? []).length === 0
            ? <span style={{ color: '#666' }}>Log bo'sh. Botlarni ishga tushiring.</span>
            : (status.logs ?? []).map((line, i) => {
                const color =
                  line.includes('✅') || line.includes('ishga tushdi') ? '#52c41a'
                  : line.includes('❌') || line.includes('xato') || line.includes('Error') ? '#ff4d4f'
                  : line.includes('⚠️') || line.includes('warning') ? '#fa8c16'
                  : '#e0e0e0'
                return <div key={i} style={{ color, lineHeight: 1.6 }}>{line || '\u00A0'}</div>
              })
          }
        </div>
      </Card>
    </div>
  )
}
