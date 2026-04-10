import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Table, Button, Tag, Space, Typography, Popconfirm, message, Card, Input, Tooltip
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, LinkOutlined, SearchOutlined
} from '@ant-design/icons'
import { getRestaurants, deleteRestaurant } from '../api'

const { Title } = Typography

const planColor = { free: 'default', basic: 'blue', pro: 'gold' }
const statusColor = { active: 'green', blocked: 'red' }

export default function Restaurants() {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const navigate = useNavigate()

  const load = () => {
    setLoading(true)
    getRestaurants()
      .then((r) => setData(r.data))
      .catch(() => message.error('Yuklashda xato'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const handleDelete = async (id) => {
    try {
      await deleteRestaurant(id)
      message.success('O\'chirildi')
      load()
    } catch (e) {
      message.error(e.response?.data?.detail || 'Xato')
    }
  }

  const filtered = data.filter(
    (r) =>
      r.name.toLowerCase().includes(search.toLowerCase()) ||
      r.slug.toLowerCase().includes(search.toLowerCase())
  )

  const columns = [
    { title: '#', dataIndex: 'id', width: 50 },
    {
      title: 'Nomi', dataIndex: 'name', render: (name, r) => (
        <Space direction="vertical" size={0}>
          <b>{name}</b>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>{r.slug}</Typography.Text>
        </Space>
      )
    },
    { title: 'Telefon', dataIndex: 'phone', render: (v) => v || '—' },
    {
      title: 'Plan', dataIndex: 'plan',
      render: (v) => <Tag color={planColor[v] || 'default'}>{(v || 'free').toUpperCase()}</Tag>
    },
    {
      title: 'Status', dataIndex: 'status',
      render: (v) => <Tag color={statusColor[v] || 'default'}>{v === 'active' ? 'Faol' : 'Bloklangan'}</Tag>
    },
    { title: 'Zakazlar', dataIndex: 'order_count', width: 90 },
    {
      title: 'Ish vaqti', render: (_, r) => `${r.work_hours_from} – ${r.work_hours_until}`
    },
    {
      title: 'Amallar', width: 140, render: (_, r) => (
        <Space>
          <Tooltip title="Admin panelni ochish">
            <Button
              size="small"
              icon={<LinkOutlined />}
              onClick={() => window.open(r.admin_panel_url, '_blank')}
            />
          </Tooltip>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => navigate(`/restaurants/${r.id}/edit`)}
          />
          <Popconfirm title="O'chirishni tasdiqlang" onConfirm={() => handleDelete(r.id)} disabled={r.id === 1}>
            <Button size="small" danger icon={<DeleteOutlined />} disabled={r.id === 1} />
          </Popconfirm>
        </Space>
      )
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, gap: 8, flexWrap: 'wrap' }}>
        <Title level={4} style={{ margin: 0 }}>Restoranlar ({data.length})</Title>
        <Space wrap>
          <Input
            placeholder="Qidirish..."
            prefix={<SearchOutlined />}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 200 }}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/restaurants/new')}
            style={{ background: '#722ed1', borderColor: '#722ed1' }}>
            Yangi restoran
          </Button>
        </Space>
      </div>

      <Card>
        <Table
          dataSource={filtered}
          columns={columns}
          rowKey="id"
          loading={loading}
          scroll={{ x: 800 }}
          pagination={{ pageSize: 20, showTotal: (t) => `Jami: ${t}` }}
        />
      </Card>
    </div>
  )
}
