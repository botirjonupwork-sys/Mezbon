import { useEffect, useState } from 'react'
import { Table, Card, Rate, Typography, Statistic, Row, Col, Tooltip, message } from 'antd'
import { getReviews, getReviewStats } from '../api'
import { useBranchStore } from '../store/branch'
import { useAuthStore } from '../store/auth'

const { Title } = Typography

export default function Reviews() {
  const [reviews, setReviews] = useState([])
  const [stats, setStats] = useState({})
  const [loading, setLoading] = useState(true)
  const [pageSize, setPageSize] = useState(10)
  const selectedBranchId = useBranchStore((s) => s.selectedBranchId)
  const restaurantId = useAuthStore((s) => s.restaurantId)

  useEffect(() => {
    setLoading(true)
    const params = {}
    if (restaurantId) params.restaurant_id = restaurantId
    if (selectedBranchId) params.branch_id = selectedBranchId
    Promise.all([getReviews(params), getReviewStats(params)])
      .then(([revRes, statsRes]) => {
        setReviews(revRes.data || [])
        setStats(statsRes.data || {})
      })
      .catch(() => message.error('Yuklashda xato'))
      .finally(() => setLoading(false))
  }, [selectedBranchId])

  const columns = [
    { title: '#', dataIndex: 'id', width: 60 },
    {
      title: 'Mijoz', dataIndex: 'user',
      render: (u) => u?.full_name || '—'
    },
    {
      title: 'Telefon', dataIndex: 'user',
      render: (u) => u?.phone || '—'
    },
    {
      title: 'Baho', dataIndex: 'rating',
      render: (v) => <Rate disabled value={v} style={{ fontSize: 14 }} />
    },
    {
      title: 'Izoh',
      dataIndex: 'comment',
      ellipsis: true,
      render: (comment) => comment
        ? (
          <Tooltip
            title={
              <div style={{ maxWidth: 260, lineHeight: 1.6 }}>{comment}</div>
            }
            overlayStyle={{ maxWidth: 300 }}
            mouseEnterDelay={0.15}
          >
            <span
              style={{
                cursor: 'pointer',
                borderBottom: '1px dashed #aaa',
                transition: 'color 0.3s',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.color = '#fa8c16' }}
              onMouseLeave={(e) => { e.currentTarget.style.color = '' }}
            >
              {comment.length > 40 ? comment.slice(0, 40) + '…' : comment}
            </span>
          </Tooltip>
        )
        : <span style={{ color: '#bbb' }}>—</span>
    },
    {
      title: 'Sana', dataIndex: 'created_at',
      render: (v) => v ? new Date(v).toLocaleDateString('uz') : '—'
    },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>Baholar</Title>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={8}>
          <Card
            style={{
              transition: 'box-shadow 0.3s',
              cursor: 'default',
            }}
            onMouseEnter={(e) => e.currentTarget.style.boxShadow = '0 4px 16px rgba(250,140,22,0.2)'}
            onMouseLeave={(e) => e.currentTarget.style.boxShadow = ''}
          >
            <Statistic
              title="O'rtacha reyting"
              value={stats.average_rating || 0}
              suffix="/ 5"
              valueStyle={{ color: '#fadb14' }}
            />
            <Rate disabled value={stats.average_rating || 0} allowHalf style={{ marginTop: 8 }} />
          </Card>
        </Col>
        <Col xs={12} sm={8}>
          <Card
            style={{ transition: 'box-shadow 0.3s' }}
            onMouseEnter={(e) => e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.12)'}
            onMouseLeave={(e) => e.currentTarget.style.boxShadow = ''}
          >
            <Statistic title="Jami baholar" value={stats.total_reviews || 0} suffix="ta" />
          </Card>
        </Col>
      </Row>

      <style>{`
        .review-row {
          transition: background-color 0.3s, opacity 0.3s;
        }
        .review-row:hover td {
          background-color: #fff7e6 !important;
        }
      `}</style>
      <Card>
        <Table
          dataSource={reviews}
          columns={columns}
          rowKey="id"
          loading={loading}
          scroll={{ x: 700 }}
          pagination={{
            pageSize,
            pageSizeOptions: ['10', '30', '50'],
            showSizeChanger: true,
            onShowSizeChange: (_, size) => setPageSize(size),
            showTotal: (total) => `Jami: ${total} ta`,
          }}
          rowClassName="review-row"
        />
      </Card>
    </div>
  )
}
