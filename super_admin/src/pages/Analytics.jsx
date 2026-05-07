import { useEffect, useState, useCallback } from 'react'
import {
  Card, Row, Col, Button, Typography, Space, DatePicker, Statistic, Table, Tag,
  message, Spin, Empty, Progress, Alert,
} from 'antd'
import {
  LineChartOutlined, ReloadOutlined, ThunderboltOutlined,
  WarningOutlined, ClockCircleOutlined, ApiOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { getPaymentAnalytics, getWebhookMonitoring } from '../api'

const { Title, Text } = Typography
const { RangePicker } = DatePicker

function fmt(uzs) {
  return new Intl.NumberFormat('uz-UZ').format(Math.round(uzs || 0))
}

export default function Analytics() {
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState(null)
  const [mon, setMon] = useState(null)
  const [range, setRange] = useState([dayjs().subtract(30, 'day'), dayjs()])

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const params = {
        date_from: range[0].format('YYYY-MM-DD'),
        date_to: range[1].format('YYYY-MM-DD'),
      }
      const [d, m] = await Promise.all([
        getPaymentAnalytics(params),
        getWebhookMonitoring({ window_seconds: 3600 }),
      ])
      setData(d)
      setMon(m)
    } catch (e) {
      message.error(e?.response?.data?.detail || 'Yuklab bo\'lmadi')
    } finally {
      setLoading(false)
    }
  }, [range])

  useEffect(() => { fetchData() }, [fetchData])

  const providerCols = [
    { title: 'Provider', dataIndex: 'provider', render: v => <Tag color="blue">{v}</Tag> },
    { title: 'Jami', dataIndex: 'total', align: 'right' },
    { title: 'To\'langan', dataIndex: 'paid', align: 'right' },
    { title: 'Success rate', dataIndex: 'success_rate_pct', align: 'right',
      render: v => <Progress percent={Math.round(v)} size="small" status={v >= 80 ? 'success' : v >= 50 ? 'normal' : 'exception'} /> },
  ]

  const monitoringCols = [
    { title: 'Endpoint', dataIndex: 'endpoint', render: v => <Tag color="purple">{v}</Tag> },
    { title: 'So\'rovlar', dataIndex: 'samples', align: 'right' },
    { title: 'Success', dataIndex: 'success_rate_pct', align: 'right',
      render: v => <Tag color={v >= 95 ? 'success' : v >= 80 ? 'warning' : 'error'}>{v != null ? `${v}%` : '—'}</Tag> },
    { title: 'P50 (ms)', dataIndex: 'p50_ms', align: 'right', render: v => v != null ? v.toFixed(0) : '—' },
    { title: 'P95 (ms)', dataIndex: 'p95_ms', align: 'right', render: v => v != null ? v.toFixed(0) : '—' },
    { title: 'P99 (ms)', dataIndex: 'p99_ms', align: 'right', render: v => v != null ? v.toFixed(0) : '—' },
  ]

  const failureCols = [
    { title: 'Sabab', dataIndex: 'reason', ellipsis: true },
    { title: 'Soni', dataIndex: 'count', align: 'right', width: 100 },
  ]

  return (
    <div>
      <Space style={{ marginBottom: 16, justifyContent: 'space-between', width: '100%' }}>
        <Title level={3} style={{ margin: 0 }}>
          <LineChartOutlined /> Analytics & Monitoring
        </Title>
        <Space>
          <RangePicker value={range} onChange={(v) => v && setRange(v)} format="DD.MM.YYYY" />
          <Button icon={<ReloadOutlined />} onClick={fetchData}>Yangilash</Button>
        </Space>
      </Space>

      <Spin spinning={loading}>
        {data && (
          <>
            {/* Top stats */}
            <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
              <Col xs={24} sm={12} md={6}>
                <Card>
                  <Statistic
                    title="Conversion rate"
                    value={data.orders.conversion_rate_pct}
                    suffix="%"
                    prefix={<ThunderboltOutlined />}
                    valueStyle={{ color: data.orders.conversion_rate_pct >= 50 ? '#3f8600' : '#fa8c16' }}
                  />
                  <div style={{ marginTop: 8 }}>
                    <Text type="secondary">{data.orders.paid} / {data.orders.total} buyurtma</Text>
                  </div>
                </Card>
              </Col>
              <Col xs={24} sm={12} md={6}>
                <Card>
                  <Statistic
                    title="AOV (o'rtacha buyurtma)"
                    value={data.aov_uzs}
                    formatter={fmt}
                    suffix="so'm"
                    valueStyle={{ color: '#1890ff' }}
                  />
                </Card>
              </Col>
              <Col xs={24} sm={12} md={6}>
                <Card>
                  <Statistic
                    title="Bekor qilish foizi"
                    value={data.orders.cancellation_rate_pct}
                    suffix="%"
                    prefix={<WarningOutlined />}
                    valueStyle={{ color: data.orders.cancellation_rate_pct < 10 ? '#3f8600' : '#cf1322' }}
                  />
                  <div style={{ marginTop: 8 }}>
                    <Text type="secondary">{data.orders.cancelled} ta bekor</Text>
                  </div>
                </Card>
              </Col>
              <Col xs={24} sm={12} md={6}>
                <Card>
                  <Statistic
                    title="Jami buyurtmalar"
                    value={data.orders.total}
                    prefix={<ApiOutlined />}
                  />
                </Card>
              </Col>
            </Row>

            {/* Webhook monitoring */}
            <Card title={<><ClockCircleOutlined /> Webhook Monitoring (oxirgi 1 soat)</>}
                  size="small" style={{ marginBottom: 16 }}>
              {mon?.anomalies?.length > 0 && (
                <Alert type="error" showIcon style={{ marginBottom: 12 }}
                  message={`Anomaliyalar topildi: ${mon.anomalies.length}`}
                  description={
                    <ul style={{ margin: 0, paddingLeft: 18 }}>
                      {mon.anomalies.map((a, i) => (
                        <li key={i}>
                          <b>{a.endpoint}</b> — {a.type === 'high_failure_rate'
                            ? `Xatolik: ${a.value_pct}% (chegara: ${a.threshold_pct}%)`
                            : `Sekin: P95=${a.p95_ms}ms (chegara: ${a.threshold_ms}ms)`}
                        </li>
                      ))}
                    </ul>
                  } />
              )}
              <Table size="small" rowKey="endpoint" pagination={false}
                dataSource={mon?.endpoints?.filter(e => e.samples > 0) || []}
                columns={monitoringCols}
                locale={{ emptyText: 'Hozircha webhook so\'rovlari yo\'q' }} />
            </Card>

            <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
              <Col xs={24} md={12}>
                <Card title="💳 Provider success rate" size="small">
                  <Table size="small" rowKey="provider" pagination={false}
                    dataSource={data.by_provider}
                    columns={providerCols}
                    locale={{ emptyText: <Empty description="Karta to'lovlari yo'q" /> }} />
                </Card>
              </Col>
              <Col xs={24} md={12}>
                <Card title="❌ SaaS to'lov xatoliklari (top-10)" size="small">
                  <Table size="small" rowKey="reason" pagination={false}
                    dataSource={data.saas_failure_reasons}
                    columns={failureCols}
                    locale={{ emptyText: 'Xatoliklar yo\'q' }} />
                </Card>
              </Col>
            </Row>

            <Row gutter={[16, 16]}>
              <Col xs={24} md={12}>
                <Card title="📊 Buyurtma status'lari" size="small">
                  <Space wrap>
                    {Object.entries(data.by_status).map(([s, n]) => (
                      <Tag key={s} color="default" style={{ fontSize: 13, padding: '4px 10px' }}>
                        {s}: <b>{n}</b>
                      </Tag>
                    ))}
                  </Space>
                </Card>
              </Col>
              <Col xs={24} md={12}>
                <Card title="💵 To'lov status'lari" size="small">
                  <Space wrap>
                    {Object.entries(data.by_payment_status).map(([s, n]) => (
                      <Tag key={s} color="blue" style={{ fontSize: 13, padding: '4px 10px' }}>
                        {s}: <b>{n}</b>
                      </Tag>
                    ))}
                  </Space>
                </Card>
              </Col>
            </Row>

            {data.by_hour_24h.length > 0 && (
              <Card title="⏰ Soatlik tahlil (oxirgi 24 soat)" size="small" style={{ marginTop: 16 }}>
                <Table size="small" rowKey="hour" pagination={false}
                  dataSource={data.by_hour_24h}
                  columns={[
                    { title: 'Soat', dataIndex: 'hour', render: v => `${v}:00` },
                    { title: 'Buyurtmalar', dataIndex: 'orders', align: 'right' },
                    { title: 'To\'langan', dataIndex: 'paid', align: 'right' },
                  ]} />
              </Card>
            )}

            <div style={{ marginTop: 12, color: '#888', fontSize: 12 }}>
              📅 Davr: <b>{data.period.from}</b> — <b>{data.period.to}</b>
            </div>
          </>
        )}
      </Spin>
    </div>
  )
}
