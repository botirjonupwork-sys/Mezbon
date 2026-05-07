import { useEffect, useState, useCallback } from 'react'
import {
  Card, Row, Col, Button, Typography, Space, DatePicker, Statistic, Table, Tag, message, Spin, Empty,
} from 'antd'
import {
  DollarOutlined, DownloadOutlined, ReloadOutlined, BankOutlined,
  RollbackOutlined, CrownOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { getFinanceSummary, getFinanceCsvUrl } from '../api'
import { useAuthStore } from '../store/auth'

const { Title, Text } = Typography
const { RangePicker } = DatePicker

function fmt(uzs) {
  return new Intl.NumberFormat('uz-UZ').format(Math.round(uzs || 0))
}

export default function Finance() {
  const token = useAuthStore(s => s.token)
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState(null)
  const [range, setRange] = useState([dayjs().subtract(30, 'day'), dayjs()])

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const params = {
        date_from: range[0].format('YYYY-MM-DD'),
        date_to: range[1].format('YYYY-MM-DD'),
      }
      const d = await getFinanceSummary(params)
      setData(d)
    } catch (e) {
      message.error(e?.response?.data?.detail || 'Hisobotni yuklashda xato')
    } finally {
      setLoading(false)
    }
  }, [range])

  useEffect(() => { fetchData() }, [fetchData])

  const downloadCsv = () => {
    const params = {
      date_from: range[0].format('YYYY-MM-DD'),
      date_to: range[1].format('YYYY-MM-DD'),
    }
    fetch(getFinanceCsvUrl(params), { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.blob())
      .then(blob => {
        const a = document.createElement('a')
        a.href = URL.createObjectURL(blob)
        a.download = `platform_finance_${params.date_from}_${params.date_to}.csv`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
      })
      .catch(() => message.error('CSV yuklab bo\'lmadi'))
  }

  const topRestaurantColumns = [
    { title: '#', render: (_, __, idx) => idx + 1, width: 50 },
    { title: 'Restoran', dataIndex: 'name' },
    { title: 'Tushum (so\'m)', dataIndex: 'revenue_uzs', align: 'right', render: fmt },
    { title: 'Komissiya (so\'m)', dataIndex: 'commission_uzs', align: 'right',
      render: v => <b style={{ color: '#fa8c16' }}>{fmt(v)}</b> },
  ]

  const planColumns = [
    { title: 'Tarif', dataIndex: 'plan', render: v => <Tag color={v === 'pro' ? 'gold' : v === 'basic' ? 'blue' : 'default'}>{v}</Tag> },
    { title: 'Oylik narx', dataIndex: 'monthly_price', align: 'right', render: fmt },
    { title: 'Restoranlar', dataIndex: 'restaurants', align: 'right' },
  ]

  const providerColumns = [
    { title: 'Provider', dataIndex: 'provider', render: v => <Tag color="blue">{v || 'manual'}</Tag> },
    { title: 'Buyurtmalar', dataIndex: 'orders', align: 'right' },
    { title: 'Summa (so\'m)', dataIndex: 'amount_uzs', align: 'right', render: fmt },
  ]

  return (
    <div>
      <Space style={{ marginBottom: 16, justifyContent: 'space-between', width: '100%' }}>
        <Title level={3} style={{ margin: 0 }}>
          <BankOutlined /> Moliyaviy Dashboard
        </Title>
        <Space>
          <RangePicker value={range} onChange={(v) => v && setRange(v)} format="DD.MM.YYYY" />
          <Button icon={<ReloadOutlined />} onClick={fetchData}>Yangilash</Button>
          <Button type="primary" icon={<DownloadOutlined />} onClick={downloadCsv}>CSV eksport</Button>
        </Space>
      </Space>

      <Spin spinning={loading}>
        {data && (
          <>
            <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
              <Col xs={24} sm={12} md={6}>
                <Card>
                  <Statistic
                    title="Komissiya daromadi"
                    value={data.platform_revenue.commission_uzs}
                    formatter={fmt}
                    suffix="so'm"
                    prefix={<DollarOutlined />}
                    valueStyle={{ color: '#3f8600' }}
                  />
                </Card>
              </Col>
              <Col xs={24} sm={12} md={6}>
                <Card>
                  <Statistic
                    title="SaaS tarif tushumi"
                    value={data.platform_revenue.saas_uzs}
                    formatter={fmt}
                    suffix="so'm"
                    prefix={<CrownOutlined />}
                    valueStyle={{ color: '#1890ff' }}
                  />
                  <div style={{ marginTop: 8 }}>
                    <Text type="secondary">{data.platform_revenue.saas_payments_count} ta to'lov</Text>
                  </div>
                </Card>
              </Col>
              <Col xs={24} sm={12} md={6}>
                <Card>
                  <Statistic
                    title="Refund hajmi"
                    value={data.refunds.total_uzs}
                    formatter={fmt}
                    suffix="so'm"
                    prefix={<RollbackOutlined />}
                    valueStyle={{ color: '#cf1322' }}
                  />
                  <div style={{ marginTop: 8 }}>
                    <Text type="secondary">{data.refunds.count} ta refund</Text>
                  </div>
                </Card>
              </Col>
              <Col xs={24} sm={12} md={6}>
                <Card>
                  <Statistic
                    title="Jami daromad"
                    value={data.platform_revenue.total_uzs}
                    formatter={fmt}
                    suffix="so'm"
                    valueStyle={{ color: '#722ed1', fontWeight: 'bold' }}
                  />
                  <div style={{ marginTop: 8 }}>
                    <Text type="secondary">komissiya + SaaS</Text>
                  </div>
                </Card>
              </Col>
            </Row>

            {data.daily_series.length > 0 && (
              <Card title="📈 Kunlik komissiya daromadi" size="small" style={{ marginBottom: 16 }}>
                <Table
                  rowKey="date" size="small" pagination={false}
                  dataSource={data.daily_series}
                  columns={[
                    { title: 'Sana', dataIndex: 'date' },
                    { title: 'Tranzaksiyalar', dataIndex: 'count', align: 'right' },
                    { title: 'Komissiya (so\'m)', dataIndex: 'commission_uzs', align: 'right',
                      render: v => <b style={{ color: '#fa8c16' }}>{fmt(v)}</b> },
                  ]}
                />
              </Card>
            )}

            <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
              <Col xs={24} md={12}>
                <Card title="🏆 Top-10 restoranlar (komissiya bo'yicha)" size="small">
                  <Table
                    rowKey="id" size="small" pagination={false}
                    dataSource={data.top_restaurants}
                    columns={topRestaurantColumns}
                    locale={{ emptyText: <Empty description="Bu davrda komissiya yo'q" /> }}
                  />
                </Card>
              </Col>
              <Col xs={24} md={12}>
                <Card title="📊 Tarif taqsimoti" size="small">
                  <Table
                    rowKey="plan" size="small" pagination={false}
                    dataSource={data.plan_distribution}
                    columns={planColumns}
                  />
                </Card>
              </Col>
            </Row>

            <Card title="💳 To'lov provayderlari taqsimoti" size="small">
              <Table
                rowKey="provider" size="small" pagination={false}
                dataSource={data.by_provider}
                columns={providerColumns}
                locale={{ emptyText: 'Bu davrda to\'lov yo\'q' }}
              />
            </Card>

            <div style={{ marginTop: 12, color: '#888', fontSize: 12 }}>
              📅 Davr: <b>{data.period.from}</b> — <b>{data.period.to}</b>
            </div>
          </>
        )}
      </Spin>
    </div>
  )
}
