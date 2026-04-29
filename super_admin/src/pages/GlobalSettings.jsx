import { useEffect, useState } from 'react'
import {
  Card, Switch, Input, Button, Typography, Alert, Spin, message,
  Table, Tag, Space, Modal, Tooltip,
} from 'antd'
import {
  ToolOutlined, HistoryOutlined, ReloadOutlined,
  WarningOutlined, EyeOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { getMaintenance, setMaintenance, getSuperActions } from '../api'

const { Title, Text, Paragraph } = Typography

function ActionTag({ action }) {
  if (action?.startsWith('maintenance.')) return <Tag color="orange">{action}</Tag>
  if (action?.startsWith('restaurant.'))  return <Tag color="purple">{action}</Tag>
  return <Tag>{action}</Tag>
}

export default function GlobalSettings() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [maintenanceMode, setMaintenanceMode] = useState(false)
  const [maintenanceMsg, setMaintenanceMsg] = useState('')
  const [actions, setActions] = useState([])
  const [details, setDetails] = useState(null)

  const load = async () => {
    setLoading(true)
    try {
      const [m, a] = await Promise.all([getMaintenance(), getSuperActions({ limit: 100 })])
      setMaintenanceMode(!!m.data?.maintenance_mode)
      setMaintenanceMsg(m.data?.maintenance_message || '')
      setActions(a.data || [])
    } catch (e) {
      message.error(e?.response?.data?.detail || 'Yuklashda xato')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const onSaveMaintenance = async () => {
    if (maintenanceMode) {
      const ok = await new Promise((resolve) => {
        Modal.confirm({
          title: '⚠️ Maintenance rejimi yoqilsinmi?',
          content: (
            <Space direction="vertical">
              <Text>Bu rejim yoqilsa:</Text>
              <ul style={{ paddingLeft: 20 }}>
                <li>Barcha restoran botlari va API <Text strong>503</Text> qaytaradi</li>
                <li>Mijozlar buyurtma bera olmaydi</li>
                <li>Faqat super-admin paneli va /health ishlaydi</li>
              </ul>
            </Space>
          ),
          icon: <WarningOutlined style={{ color: '#ff4d4f' }} />,
          okText: 'Ha, yoqish',
          okButtonProps: { danger: true },
          cancelText: 'Bekor',
          onOk: () => resolve(true),
          onCancel: () => resolve(false),
        })
      })
      if (!ok) return
    }
    setSaving(true)
    try {
      await setMaintenance({
        maintenance_mode: maintenanceMode,
        maintenance_message: maintenanceMsg || undefined,
      })
      message.success(maintenanceMode ? 'Maintenance rejimi YOQILDI' : "Maintenance rejimi o'chirildi")
      await load()
    } catch (e) {
      message.error(e?.response?.data?.detail || 'Saqlashda xato')
    } finally {
      setSaving(false)
    }
  }

  const actionColumns = [
    { title: 'Vaqt', dataIndex: 'created_at', width: 160,
      render: (v) => v ? dayjs(v).format('DD.MM.YYYY HH:mm:ss') : '—' },
    { title: 'Foydalanuvchi', dataIndex: 'actor', width: 120 },
    { title: 'Amal', dataIndex: 'action', render: (v) => <ActionTag action={v} /> },
    { title: 'Maqsad', render: (_, r) => r.target_type
        ? <Text code>{r.target_type}#{r.target_id ?? '—'}</Text>
        : <Text type="secondary">—</Text>,
    },
    { title: 'IP', dataIndex: 'ip', width: 130, render: (v) => v ? <Text code>{v}</Text> : '—' },
    {
      title: 'Tafsilot', width: 80,
      render: (_, r) => r.details
        ? <Tooltip title="JSON ko'rish"><Button size="small" icon={<EyeOutlined />} onClick={() => setDetails(r)} /></Tooltip>
        : <Text type="secondary">—</Text>,
    },
  ]

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 100 }} />

  return (
    <div>
      <Title level={3}>⚙️ Global sozlamalar</Title>

      {/* Maintenance Mode */}
      <Card title={<><ToolOutlined /> Maintenance Mode (Texnik tanaffus)</>}
            size="small" style={{ marginBottom: 16 }}>
        {maintenanceMode && (
          <Alert
            type="error" showIcon style={{ marginBottom: 16 }}
            message="Maintenance rejimi YOQILGAN"
            description="Barcha restoran API'lari 503 qaytaradi. Faqat super-admin paneli ishlayapti."
          />
        )}
        <Paragraph type="secondary">
          Yoqilganda butun platforma bo'yicha barcha restoran API/bot endpointlari
          vaqtincha to'xtaydi va mijozlarga texnik tanaffus xabari ko'rsatiladi.
          Faqat <Text code>/super-admin/*</Text>, <Text code>/health</Text> va auth ishlashda davom etadi.
        </Paragraph>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Space align="center">
            <Switch
              checked={maintenanceMode}
              onChange={setMaintenanceMode}
              checkedChildren="YOQILGAN"
              unCheckedChildren="O'chiq"
            />
            <Text strong>{maintenanceMode ? 'YOQILGAN' : "O'chiq"}</Text>
          </Space>
          <Input.TextArea
            rows={2}
            placeholder="Mijozlarga ko'rsatiladigan xabar"
            value={maintenanceMsg}
            onChange={(e) => setMaintenanceMsg(e.target.value)}
          />
          <Button type="primary" loading={saving} onClick={onSaveMaintenance}
            danger={maintenanceMode}
            style={!maintenanceMode ? { background: '#722ed1', borderColor: '#722ed1' } : {}}>
            Saqlash
          </Button>
        </Space>
      </Card>

      {/* Action Logs */}
      <Card
        title={<><HistoryOutlined /> Audit log (so'nggi {actions.length} ta)</>}
        size="small"
        extra={<Button size="small" icon={<ReloadOutlined />} onClick={load}>Yangilash</Button>}
      >
        <Table
          rowKey="id"
          dataSource={actions}
          columns={actionColumns}
          size="small"
          pagination={{ pageSize: 20 }}
          scroll={{ x: 700 }}
        />
      </Card>

      <Modal
        title={`${details?.action} — tafsilot`}
        open={!!details}
        onCancel={() => setDetails(null)}
        footer={null}
        width={600}
      >
        <pre style={{
          background: '#f5f5f5', padding: 12, borderRadius: 4,
          maxHeight: 400, overflow: 'auto', fontSize: 12,
        }}>
          {details ? JSON.stringify(details.details, null, 2) : ''}
        </pre>
      </Modal>
    </div>
  )
}
