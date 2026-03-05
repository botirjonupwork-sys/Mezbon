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
      setAuth(res.data.token, { name: res.data.name })
      message.success('Xush kelibsiz!')
      navigate('/')
    } catch {
      message.error("Login yoki parol noto'g'ri!")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'linear-gradient(135deg, #fa8c16 0%, #d46b08 100%)' }}>
      <Card style={{ width: 380, borderRadius: 12, boxShadow: '0 8px 32px rgba(0,0,0,0.15)' }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{ fontSize: 48, marginBottom: 8 }}>🥟</div>
          <Title level={3} style={{ margin: 0 }}>Muhsina Dollar Somsa</Title>
          <Text type="secondary">Admin Panel</Text>
        </div>

        <Form onFinish={onFinish} layout="vertical" size="large">
          <Form.Item name="username" rules={[{ required: true, message: 'Login kiriting' }]}>
            <Input prefix={<UserOutlined />} placeholder="Login" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: 'Parol kiriting' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="Parol" />
          </Form.Item>
          <Button
            type="primary" htmlType="submit" block loading={loading}
            style={{ background: '#fa8c16', borderColor: '#fa8c16' }}
          >
            Kirish
          </Button>
        </Form>
      </Card>
    </div>
  )
}
