import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Form, Input, Button, Typography, Row, Col,
  message, Spin, Alert, Tag
} from 'antd'
import {
  ArrowLeftOutlined, SaveOutlined, RobotOutlined,
  CheckCircleOutlined, CloseCircleOutlined, LoadingOutlined,
} from '@ant-design/icons'
import { getSettings, updateSettings } from '../../api'
import { useAuthStore } from '../../store/auth'

const { Title, Text } = Typography

const cardStyle = { marginBottom: 12, borderRadius: 14, border: '1px solid #ececec', boxShadow: 'none' }
const cardBody = { padding: 24 }
const sectionLabel = { fontSize: 12, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: 18, display: 'block' }

export default function BotsSettings() {
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [checking, setChecking] = useState(false)
  const [botStatus, setBotStatus] = useState(null)

  const { currentRestaurantId: restaurantId, token } = useAuthStore()
  const restParams = restaurantId ? { restaurant_id: restaurantId } : {}

  useEffect(() => {
    if (!restaurantId) {
      setLoading(false)
      return
    }

    setLoading(true)
    getSettings(restParams)
      .then((res) => {
        form.setFieldsValue(res.data || {})
      })
      .catch(() => message.error("Ma'lumotlarni yuklashda xato"))
      .finally(() => setLoading(false))
  }, [restaurantId])

  const handleSave = async () => {
    setSaving(true)
    try {
      const values = await form.validateFields()
      await updateSettings(values, restParams)
      message.success('Sozlamalar saqlandi')
    } catch (err) {
      if (!err?.errorFields) message.error('Saqlashda xato')
    } finally {
      setSaving(false)
    }
  }

  const checkBots = async () => {
    setChecking(true)
    try {
      const r = await fetch(`/api/admin/bots/check?restaurant_id=${restaurantId}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      const d = await r.json()
      setBotStatus(d)
    } catch (e) {
      message.error("Tekshirib bo'lmadi")
    } finally {
      setChecking(false)
    }
  }

  const renderBotStatus = (key, label) => {
    const s = botStatus?.[key]
    if (!s) return null

    if (!s.configured) {
      return (
        <Alert
          type="warning"
          icon={<CloseCircleOutlined />}
          message={`${label}: Token kiritilmagan`}
          style={{ marginTop: 8, borderRadius: 8 }}
        />
      )
    }

    if (s.online) {
      return (
        <Alert
          type="success"
          icon={<CheckCircleOutlined />}
          message={
            <span>
              {label}: Online — <Text code>@{s.username || '?'}</Text> ({s.first_name || '?'})
            </span>
          }
          style={{ marginTop: 8, borderRadius: 8 }}
        />
      )
    }

    return (
      <Alert
        type="error"
        icon={<CloseCircleOutlined />}
        message={`${label}: Offline — ${s.error || 'Telegram javob bermadi'}`}
        style={{ marginTop: 8, borderRadius: 8 }}
      />
    )
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <Spin size="large" />
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <Button
          type="text"
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/settings')}
          style={{ marginBottom: 8, padding: 0, color: '#6b7280' }}
        >
          Sozlamalar
        </Button>
        <Title level={3} style={{ marginBottom: 4, marginTop: 0, fontWeight: 600 }}>
          Telegram botlar
        </Title>
        <Text type="secondary" style={{ fontSize: 14 }}>
          Mijoz va kuryer bot tokenlarini sozlang
        </Text>
      </div>

      <Form form={form} layout="vertical" requiredMark="optional">
        {/* Instructions */}
        <Card style={{ ...cardStyle, background: '#f8fafc' }} styles={{ body: { padding: 20 } }}>
          <span style={{ ...sectionLabel, marginBottom: 12 }}>Token olish tartibi</span>
          <ol style={{ margin: 0, paddingLeft: 20, color: '#374151', lineHeight: 1.9 }}>
            <li>Telegram'da <Text code>@BotFather</Text> ni oching</li>
            <li><Text code>/newbot</Text> buyrug'ini yuboring</li>
            <li>Bot nomi va username'ni kiriting</li>
            <li>Olingan tokenni (<Text code>1234567:ABC...</Text>) quyiga kiriting</li>
          </ol>
        </Card>

        {/* Customer Bot */}
        <Card style={cardStyle} styles={{ body: cardBody }}>
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 16, fontWeight: 600, color: '#111827' }}>Mijoz boti</div>
            <Text type="secondary" style={{ fontSize: 13 }}>
              Mijozlar buyurtma berish uchun ishlatadi
            </Text>
          </div>

          <Form.Item name="bot_token" label="Bot tokeni" style={{ marginBottom: 0 }}>
            <Input.Password autoComplete="off" placeholder="1234567:ABC..." size="large" />
          </Form.Item>
        </Card>

        {/* Courier Bot */}
        <Card style={cardStyle} styles={{ body: cardBody }}>
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 16, fontWeight: 600, color: '#111827' }}>Kuryer boti</div>
            <Text type="secondary" style={{ fontSize: 13 }}>
              Kuryerlar buyurtmalarni qabul qilish uchun ishlatadi
            </Text>
          </div>

          <Form.Item name="courier_bot_token" label="Bot tokeni" style={{ marginBottom: 0 }}>
            <Input.Password autoComplete="off" placeholder="1234567:DEF..." size="large" />
          </Form.Item>
        </Card>

        {/* Check Bots */}
        <Card style={{ ...cardStyle, marginBottom: 24 }} styles={{ body: cardBody }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <div>
              <span style={{ ...sectionLabel, marginBottom: 4 }}>Holatni tekshirish</span>
              <Text type="secondary" style={{ fontSize: 13 }}>
                Tokenlar to'g'ri kiritilganini tekshiring
              </Text>
            </div>
            <Button
              onClick={checkBots}
              loading={checking}
              icon={checking ? <LoadingOutlined /> : <RobotOutlined />}
            >
              Tekshirish
            </Button>
          </div>

          {botStatus && (
            <div>
              {renderBotStatus('customer_bot', 'Mijoz boti')}
              {renderBotStatus('courier_bot', 'Kuryer boti')}
            </div>
          )}

          <Alert
            type="warning"
            message="Muhim"
            description="Token o'zgartirilgandan so'ng super-admin'dan 'Bots service restart' so'rang"
            style={{ marginTop: 16, borderRadius: 8 }}
          />
        </Card>

        {/* Save Button */}
        <Button
          type="primary"
          icon={<SaveOutlined />}
          loading={saving}
          onClick={handleSave}
          size="large"
          block
          style={{ height: 46, fontWeight: 500, borderRadius: 10, background: '#111827', borderColor: '#111827' }}
        >
          Saqlash
        </Button>
      </Form>
    </div>
  )
}
