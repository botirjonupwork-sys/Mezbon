import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Form, Input, Button, Card, Typography, message } from 'antd'
import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { superLogin } from '../api'
import { useAuthStore } from '../store/auth'

const { Title } = Typography

export default function Login() {
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)

  const onFinish = async (values) => {
    setLoading(true)
    try {
      const res = await superLogin(values)
      setAuth(res.data.token)
      navigate('/')
    } catch {
      message.error('Login yoki parol noto\'g\'ri')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#f0f2f5' }}>
      <Card style={{ width: 360 }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={3} style={{ color: '#722ed1', margin: 0 }}>Super Admin</Title>
          <Typography.Text type="secondary">SaaS Platforma</Typography.Text>
        </div>
        <Form layout="vertical" onFinish={onFinish}>
          <Form.Item name="username" rules={[{ required: true }]}>
            <Input prefix={<UserOutlined />} placeholder="Username" size="large" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="Parol" size="large" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block size="large" loading={loading}
            style={{ background: '#722ed1', borderColor: '#722ed1' }}>
            Kirish
          </Button>
        </Form>
      </Card>
    </div>
  )
}
