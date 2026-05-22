import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Form, Input, Button, Typography, Row, Col,
  message, Spin, Alert, Divider
} from 'antd'
import {
  ArrowLeftOutlined, SaveOutlined, UserOutlined,
  LockOutlined, MailOutlined,
} from '@ant-design/icons'
import { getProfile, updateProfile } from '../../api'
import { useAuthStore } from '../../store/auth'

const { Title, Text } = Typography

const cardStyle = { marginBottom: 12, borderRadius: 14, border: '1px solid #ececec', boxShadow: 'none' }
const cardBody = { padding: 24 }
const sectionLabel = { fontSize: 12, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: 18, display: 'block' }

export default function ProfileSettings() {
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const { currentRestaurantId: restaurantId, token, setAuth } = useAuthStore()
  const restParams = restaurantId ? { restaurant_id: restaurantId } : {}

  useEffect(() => {
    setLoading(true)
    getProfile(restParams)
      .then((res) => {
        const p = res.data || {}
        form.setFieldsValue({ username: p.username, name: p.name })
      })
      .catch(() => message.error("Ma'lumotlarni yuklashda xato"))
      .finally(() => setLoading(false))
  }, [restaurantId])

  const handleSave = async () => {
    setSaving(true)
    try {
      const values = await form.validateFields()
      const payload = {}

      if (values.username) payload.username = values.username

      if (values.new_password) {
        if (!values.current_password) {
          message.error("Parolni o'zgartirish uchun eski parol kerak")
          setSaving(false)
          return
        }
        if (values.new_password !== values.confirm_password) {
          message.error('Yangi parol va tasdiq mos kelmaydi')
          setSaving(false)
          return
        }
        payload.new_password = values.new_password
        payload.current_password = values.current_password
      }

      await updateProfile(payload, restParams)
      form.setFieldsValue({
        new_password: '',
        confirm_password: '',
        current_password: '',
      })

      if (values.username) {
        setAuth(token, { name: values.username }, restaurantId)
      }

      message.success('Profil yangilandi')
    } catch (err) {
      if (err?.response?.data?.detail) {
        message.error(err.response.data.detail)
      } else if (!err?.errorFields) {
        message.error('Xato')
      }
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <Spin size="large" />
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 600, margin: '0 auto' }}>
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
          Profil
        </Title>
        <Text type="secondary" style={{ fontSize: 14 }}>
          Login va parolni boshqaring
        </Text>
      </div>

      <Form form={form} layout="vertical" requiredMark="optional">
        {/* Username */}
        <Card style={cardStyle} styles={{ body: cardBody }}>
          <span style={sectionLabel}>Login ma'lumotlari</span>

          <Form.Item
            name="username"
            label="Username"
            rules={[{ required: true, message: 'Username kiriting' }]}
            style={{ marginBottom: 0 }}
          >
            <Input
              prefix={<UserOutlined style={{ color: '#bfbfbf' }} />}
              placeholder="admin"
              size="large"
            />
          </Form.Item>
        </Card>

        {/* Password Change */}
        <Card style={{ ...cardStyle, marginBottom: 24 }} styles={{ body: cardBody }}>
          <span style={sectionLabel}>Parolni o'zgartirish</span>
          <Text type="secondary" style={{ display: 'block', marginBottom: 16, marginTop: -8, fontSize: 13 }}>
            Parolni o'zgartirish uchun eski parolni kiritish majburiy
          </Text>

          <Alert
            type="warning"
            message="Bo'sh qoldirsangiz parol o'zgarmaydi"
            style={{ marginBottom: 16, borderRadius: 8 }}
          />

          <Form.Item
            name="current_password"
            label="Joriy parol"
            extra="Faqat parolni o'zgartirsangiz kerak"
          >
            <Input.Password
              prefix={<LockOutlined style={{ color: '#bfbfbf' }} />}
              placeholder="Eski parol"
              autoComplete="current-password"
              size="large"
            />
          </Form.Item>

          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item
                name="new_password"
                label="Yangi parol"
              >
                <Input.Password
                  prefix={<LockOutlined style={{ color: '#bfbfbf' }} />}
                  placeholder="Yangi parol"
                  autoComplete="new-password"
                  size="large"
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item
                name="confirm_password"
                label="Parolni tasdiqlang"
                dependencies={['new_password']}
                rules={[
                  ({ getFieldValue }) => ({
                    validator(_, v) {
                      if (!v && !getFieldValue('new_password')) return Promise.resolve()
                      if (v === getFieldValue('new_password')) return Promise.resolve()
                      return Promise.reject('Parollar mos emas!')
                    },
                  }),
                ]}
              >
                <Input.Password
                  prefix={<LockOutlined style={{ color: '#bfbfbf' }} />}
                  placeholder="Parolni takrorlang"
                  autoComplete="new-password"
                  size="large"
                />
              </Form.Item>
            </Col>
          </Row>
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
