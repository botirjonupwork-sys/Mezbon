import { useEffect, useState } from 'react'
import {
  Tabs, Form, Input, InputNumber, Button, Card, Typography,
  message, Divider, Row, Col, Select, Spin, Alert
} from 'antd'
import {
  UserOutlined, LockOutlined, GlobalOutlined, PhoneOutlined,
  MailOutlined, SaveOutlined
} from '@ant-design/icons'
import { useAuthStore } from '../store/auth'
import {
  getSuperProfile, updateSuperProfile,
  getPlatformSettings, updatePlatformSettings,
} from '../api'

const { Title, Text } = Typography

export default function Settings() {
  const [profileForm] = Form.useForm()
  const [platformForm] = Form.useForm()
  const [profileLoading, setProfileLoading] = useState(false)
  const [platformLoading, setPlatformLoading] = useState(false)
  const [fetching, setFetching] = useState(true)
  const setAuth = useAuthStore((s) => s.setAuth)
  const logout = useAuthStore((s) => s.logout)

  useEffect(() => {
    Promise.all([getSuperProfile(), getPlatformSettings()])
      .then(([profRes, platRes]) => {
        profileForm.setFieldsValue({ username: profRes.data.username })
        platformForm.setFieldsValue(platRes.data)
      })
      .catch(() => message.error('Yuklab bo\'lmadi'))
      .finally(() => setFetching(false))
  }, [])

  const onProfileSave = async (values) => {
    if (!values.current_password) {
      message.warning('Joriy parolni kiriting')
      return
    }
    setProfileLoading(true)
    try {
      const res = await updateSuperProfile({
        new_username: values.new_username || undefined,
        current_password: values.current_password,
        new_password: values.new_password || undefined,
      })
      message.success('Profil yangilandi')
      profileForm.setFieldsValue({ current_password: '', new_password: '', confirm_password: '' })
      // Agar username yoki parol o'zgardi — yangi token bilan qayta login
      if (res.data.new_token) {
        setAuth(res.data.new_token)
      }
    } catch (e) {
      message.error(e.response?.data?.detail || 'Xato yuz berdi')
    } finally {
      setProfileLoading(false)
    }
  }

  const onPlatformSave = async (values) => {
    setPlatformLoading(true)
    try {
      const res = await updatePlatformSettings(values)
      platformForm.setFieldsValue(res.data)
      message.success('Platforma sozlamalari saqlandi')
    } catch (e) {
      message.error(e.response?.data?.detail || 'Xato yuz berdi')
    } finally {
      setPlatformLoading(false)
    }
  }

  if (fetching) return <Spin size="large" style={{ display: 'block', margin: '80px auto' }} />

  const items = [
    {
      key: 'profile',
      label: <span><UserOutlined /> Profil</span>,
      children: (
        <Card style={{ maxWidth: 520 }}>
          <Title level={5} style={{ marginBottom: 20 }}>Super Admin profili</Title>
          <Form form={profileForm} layout="vertical" onFinish={onProfileSave}>
            <Form.Item name="username" label="Joriy username">
              <Input prefix={<UserOutlined />} disabled style={{ color: '#666' }} />
            </Form.Item>

            <Divider>Username o'zgartirish (ixtiyoriy)</Divider>
            <Form.Item
              name="new_username"
              label="Yangi username"
              rules={[{ min: 4, message: 'Kamida 4 ta belgi' }]}
            >
              <Input prefix={<UserOutlined />} placeholder="Yangi login (ixtiyoriy)" />
            </Form.Item>

            <Divider>Parol o'zgartirish</Divider>
            <Form.Item
              name="current_password"
              label="Joriy parol"
              rules={[{ required: true, message: 'Joriy parolni kiriting' }]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="Hozirgi parol" />
            </Form.Item>
            <Form.Item
              name="new_password"
              label="Yangi parol (ixtiyoriy)"
              rules={[{ min: 6, message: 'Kamida 6 ta belgi' }]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="Yangi parol" />
            </Form.Item>
            <Form.Item
              name="confirm_password"
              label="Yangi parolni tasdiqlang"
              dependencies={['new_password']}
              rules={[
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    const np = getFieldValue('new_password')
                    if (!np || !value || np === value) return Promise.resolve()
                    return Promise.reject(new Error('Parollar mos emas'))
                  },
                }),
              ]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="Parolni tasdiqlang" />
            </Form.Item>

            <Alert
              message="Eslatma: username yoki parol o'zgartirilsa, sahifa qayta yuklanadi."
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
            />

            <Button type="primary" htmlType="submit" loading={profileLoading}
              icon={<SaveOutlined />}
              style={{ background: '#722ed1', borderColor: '#722ed1' }}>
              Saqlash
            </Button>
          </Form>
        </Card>
      ),
    },
    {
      key: 'platform',
      label: <span><GlobalOutlined /> Platforma</span>,
      children: (
        <Card style={{ maxWidth: 720 }}>
          <Title level={5} style={{ marginBottom: 20 }}>Platforma sozlamalari</Title>
          <Form form={platformForm} layout="vertical" onFinish={onPlatformSave}>

            <Divider orientation="left">Platforma ma'lumotlari</Divider>
            <Row gutter={16}>
              <Col xs={24} sm={12}>
                <Form.Item name="platform_name" label="Platforma nomi">
                  <Input prefix={<GlobalOutlined />} placeholder="SaaS Buyurtma Platformasi" />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item name="platform_url" label="Platforma URL">
                  <Input placeholder="https://buyurtmalar.uz" />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item name="support_phone" label="Qo'llab-quvvatlash telefon">
                  <Input prefix={<PhoneOutlined />} placeholder="+998901234567" />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item name="support_email" label="Qo'llab-quvvatlash email">
                  <Input prefix={<MailOutlined />} placeholder="support@buyurtmalar.uz" />
                </Form.Item>
              </Col>
            </Row>

            <Divider orientation="left">Yangi restoranlar uchun standart qiymatlar</Divider>
            <Row gutter={16}>
              <Col xs={12} sm={6}>
                <Form.Item name="default_plan" label="Standart tarif">
                  <Select options={[
                    { value: 'free', label: 'Free' },
                    { value: 'basic', label: 'Basic' },
                    { value: 'pro', label: 'Pro' },
                  ]} />
                </Form.Item>
              </Col>
              <Col xs={12} sm={6}>
                <Form.Item name="default_min_order" label="Min. buyurtma (so'm)">
                  <InputNumber style={{ width: '100%' }} min={0} step={1000} />
                </Form.Item>
              </Col>
              <Col xs={12} sm={6}>
                <Form.Item name="default_delivery_base_fee" label="Dastavka narxi">
                  <InputNumber style={{ width: '100%' }} min={0} step={500} />
                </Form.Item>
              </Col>
              <Col xs={12} sm={6}>
                <Form.Item name="default_delivery_per_km" label="Km narxi">
                  <InputNumber style={{ width: '100%' }} min={0} step={500} />
                </Form.Item>
              </Col>
              <Col xs={12} sm={6}>
                <Form.Item name="default_work_from" label="Standart ochilish">
                  <Input placeholder="09:00" />
                </Form.Item>
              </Col>
              <Col xs={12} sm={6}>
                <Form.Item name="default_work_until" label="Standart yopilish">
                  <Input placeholder="22:00" />
                </Form.Item>
              </Col>
              <Col xs={12} sm={6}>
                <Form.Item name="commission_percent" label="Komissiya (%)">
                  <InputNumber style={{ width: '100%' }} min={0} max={100} step={0.5}
                    formatter={(v) => `${v}%`} parser={(v) => v.replace('%', '')} />
                </Form.Item>
              </Col>
            </Row>

            <Button type="primary" htmlType="submit" loading={platformLoading}
              icon={<SaveOutlined />}
              style={{ background: '#722ed1', borderColor: '#722ed1' }}>
              Saqlash
            </Button>
          </Form>
        </Card>
      ),
    },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 24 }}>Sozlamalar</Title>
      <Tabs items={items} defaultActiveKey="profile" />
    </div>
  )
}
