import { useState } from 'react'
import { Form, Input, Button, Card, Typography, message } from 'antd'
import { UserOutlined, LockOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/auth'
import { login } from '../api'

const { Title, Text } = Typography

export default function Login() {
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [loading, setLoading] = useState(false)

  const onFinish = async ({ username, password }) => {
    setLoading(true)
    try {
      const res = await login({ username, password })
      setAuth(res.data.token, { name: res.data.name }, res.data.restaurant_id)
      message.success('Xush kelibsiz!')
      navigate('/')
    } catch {
      message.error("Login yoki parol noto'g'ri!")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'linear-gradient(135deg, #fa8c16 0%, #d4380d 100%)',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* Background decoration */}
      <div style={{
        position: 'absolute',
        top: '-50%',
        right: '-20%',
        width: '600px',
        height: '600px',
        borderRadius: '50%',
        background: 'rgba(255,255,255,0.05)',
      }} />
      <div style={{
        position: 'absolute',
        bottom: '-30%',
        left: '-10%',
        width: '400px',
        height: '400px',
        borderRadius: '50%',
        background: 'rgba(255,255,255,0.05)',
      }} />

      <Card style={{
        width: 400,
        borderRadius: 16,
        boxShadow: '0 12px 40px rgba(0,0,0,0.2)',
        border: 'none',
        position: 'relative',
        zIndex: 1,
      }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <img src="/logo.svg" alt="Mezbon" width="80" height="80"
               style={{ marginBottom: 12, filter: 'drop-shadow(0 4px 8px rgba(250, 140, 22, 0.3))' }} />
          <Title level={2} style={{
            margin: 0,
            background: 'linear-gradient(135deg, #fa8c16, #d4380d)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            letterSpacing: '-1px',
            fontWeight: 800,
          }}>
            MEZBON
          </Title>
          <Text type="secondary" style={{ fontSize: 13 }}>
            Restoran boshqaruv tizimi
          </Text>
        </div>

        <Form onFinish={onFinish} layout="vertical" size="large">
          <Form.Item name="username" rules={[{ required: true, message: 'Login kiriting' }]}>
            <Input prefix={<UserOutlined />} placeholder="Login" autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: 'Parol kiriting' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="Parol" autoComplete="current-password" />
          </Form.Item>
          <Button
            type="primary" htmlType="submit" block loading={loading}
            style={{
              background: 'linear-gradient(135deg, #fa8c16, #d4380d)',
              borderColor: '#fa8c16',
              height: 44,
              fontSize: 15,
              fontWeight: 600,
              boxShadow: '0 4px 12px rgba(250, 140, 22, 0.3)',
            }}
          >
            Kirish
          </Button>
        </Form>

        <div style={{ textAlign: 'center', marginTop: 24, fontSize: 12, color: '#999' }}>
          Restoraningizni boshqaring,<br/>
          biznesingizni rivojlantiring 🚀
        </div>
      </Card>

      {/* Brand mark bottom */}
      <div style={{
        position: 'absolute',
        bottom: 24,
        textAlign: 'center',
        width: '100%',
        color: 'rgba(255,255,255,0.7)',
        fontSize: 12,
      }}>
        © 2026 Mezbon · SaaS for restaurants
      </div>
    </div>
  )
}
