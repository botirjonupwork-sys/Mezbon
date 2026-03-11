import { useEffect, useState } from 'react'
import { Table, Tag, Button, Space, Typography, message, Popconfirm } from 'antd'
import { CheckOutlined, StopOutlined, UserOutlined } from '@ant-design/icons'
import { getCouriers, updateCourierStatus } from '../api'
import { useBranchStore } from '../store/branch'

const { Title } = Typography

const TRANSPORT = {
  car: '🚗 Avtomobil',
  motorcycle: '🏍 Motosikl',
  bicycle: '🚲 Velosiped',
  walk: '🚶 Piyoda',
}

const STATUS_TAG = {
  pending: <Tag color="orange">Kutilmoqda</Tag>,
  active: <Tag color="green">Faol</Tag>,
  blocked: <Tag color="red">Bloklangan</Tag>,
}

export default function Couriers() {
  const [couriers, setCouriers] = useState([])
  const [loading, setLoading] = useState(true)
  const selectedBranchId = useBranchStore((s) => s.selectedBranchId)

  const load = () => {
    setLoading(true)
    const params = selectedBranchId ? { branch_id: selectedBranchId } : {}
    getCouriers(params)
      .then((r) => setCouriers(r.data))
      .catch(() => message.error('Kuryer ma\'lumotlarini yuklashda xato'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [selectedBranchId])

  const handleStatus = async (id, status) => {
    try {
      await updateCourierStatus(id, status)
      message.success(status === 'active' ? 'Kuryer tasdiqlandi!' : 'Kuryer bloklandi!')
      load()
    } catch {
      message.error('Xato!')
    }
  }

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      width: 60,
    },
    {
      title: 'Ism',
      dataIndex: 'full_name',
      render: (name) => <><UserOutlined /> {name}</>,
    },
    {
      title: 'Telefon',
      dataIndex: 'phone',
    },
    {
      title: 'Transport',
      dataIndex: 'transport_type',
      render: (t) => TRANSPORT[t] || t,
    },
    {
      title: 'Holat',
      dataIndex: 'status',
      render: (s) => STATUS_TAG[s] || s,
    },
    {
      title: 'Sana',
      dataIndex: 'created_at',
      render: (d) => d ? new Date(d).toLocaleDateString('uz') : '—',
    },
    {
      title: 'Amallar',
      render: (_, record) => (
        <Space>
          {record.status !== 'active' && (
            <Popconfirm
              title="Kuryerni tasdiqlaysizmi?"
              onConfirm={() => handleStatus(record.id, 'active')}
            >
              <Button type="primary" size="small" icon={<CheckOutlined />}>
                Tasdiqlash
              </Button>
            </Popconfirm>
          )}
          {record.status !== 'blocked' && (
            <Popconfirm
              title="Kuryerni bloklaysizmi?"
              onConfirm={() => handleStatus(record.id, 'blocked')}
            >
              <Button danger size="small" icon={<StopOutlined />}>
                Bloklash
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>🚗 Kuryerlar</Title>
      <Table
        columns={columns}
        dataSource={couriers}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 20 }}
        size="small"
        scroll={{ x: 700 }}
      />
    </div>
  )
}
