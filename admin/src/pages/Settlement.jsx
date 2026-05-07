import { useEffect, useState, useCallback } from 'react'
import {
  Card, Row, Col, Button, Typography, Space, DatePicker, Statistic, Table, Tag, message, Spin,
} from 'antd'
import {
  DollarOutlined, DownloadOutlined, ReloadOutlined, CreditCardOutlined,
  RollbackOutlined, BankOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { getSettlement, getSettlementCsvUrl } from '../api'
import { useAuthStore } from '../store/auth'

const { Title, Text } = Typography
const { RangePicker } = DatePicker

function fmt(uzs) {
  return new Intl.NumberFormat('uz-UZ').format(Math.round(uzs || 0))
}

export default function Settlement() {
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
      const d = await getSettlement(params)
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
    const url = getSettlementCsvUrl(params)
    // Token bilan yuklash uchun blob orqali
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.blob())
      .then(blob => {
        const a = document.createElement('a')
        a.href = URL.createObjectURL(blob)
        a.download = `settlement_${params.date_from}_${params.date_to}.csv`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
      })
      .catch(() => message.error('CSV yuklab bo\'lmadi'))
  }

  const providerColumns = [
    { title: 'Provider', dataIndex: 'provider', render: v => <Tag color="blue">{v || 'manual'}</Tag> },
    { title: 'Soni', dataIndex: 'count', align: 'right' },
    { title: 'Summa (so\'m)', dataIndex: 'amount_uzs', align: 'right', render: fmt },
  ]

  return (
    <div>
      <Space style={{ marginBottom: 16, justifyContent: 'space-between', width: '100%' }}>
        <Title level={3} style={{ margin: 0 }}>
          <BankOutlined /> Moliyaviy hisobot (Settlement)
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
                    title="To'langan buyurtmalar"
                    value={data.orders.count}
                    prefix={<CreditCardOutlined />}
                  />
                  <div style={{ marginTop: 8 }}>
                    <Text type="secondary">Jami: <b>{fmt(data.orders.paid_total_uzs)}</b> so'm</Text>
                  </div>
                </Card>
              </Col>
              <Col xs={24} sm={12} md={6}>
                <Card>
                  <Statistic
                    title="Pul qaytarilishi (Refund)"
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
                    title="Platforma komissiyasi"
                    value={data.commission_uzs}
                    formatter={fmt}
                    suffix="so'm"
                    prefix={<DollarOutlined />}
                    valueStyle={{ color: '#fa8c16' }}
                  />
                </Card>
              </Col>
              <Col xs={24} sm={12} md={6}>
                <Card>
                  <Statistic
                    title="Sof daromad (Net)"
                    value={data.net_uzs}
                    formatter={fmt}
                    suffix="so'm"
                    valueStyle={{ color: data.net_uzs >= 0 ? '#3f8600' : '#cf1322' }}
                  />
                  <div style={{ marginTop: 8 }}>
                    <Text type="secondary">paid − refund − komissiya</Text>
                  </div>
                </Card>
              </Col>
            </Row>

            <Card title="To'lov provayderlari bo'yicha taqsimot" size="small">
              <Table
                size="small"
                rowKey="provider"
                dataSource={data.orders.by_provider}
                columns={providerColumns}
                pagination={false}
                locale={{ emptyText: 'Bu davrda to\'langan buyurtma yo\'q' }}
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
