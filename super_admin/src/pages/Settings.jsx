import { useEffect, useState } from 'react'
import {
  Tabs, Form, Input, InputNumber, Button, Card, Typography,
  message, Divider, Row, Col, Select, Spin, Alert, Tag
} from 'antd'
import {
  UserOutlined, LockOutlined, GlobalOutlined, PhoneOutlined,
  MailOutlined, SaveOutlined, RobotOutlined, KeyOutlined,
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
  const [aiForm] = Form.useForm()
  const [profileLoading, setProfileLoading] = useState(false)
  const [platformLoading, setPlatformLoading] = useState(false)
  const [aiLoading, setAiLoading] = useState(false)
  const [aiStatus, setAiStatus] = useState({ llm_set: false, llm_masked: '', tts_set: false, tts_masked: '' })
  const [fetching, setFetching] = useState(true)
  const setAuth = useAuthStore((s) => s.setAuth)
  const logout = useAuthStore((s) => s.logout)

  const applyPlatformData = (d) => {
    platformForm.setFieldsValue(d)
    aiForm.setFieldsValue({
      ai_llm_provider: d.ai_llm_provider || 'openai',
      ai_llm_model: d.ai_llm_model || 'gpt-4o-mini',
      ai_llm_api_key: '',  // hech qachon plaintext kelmaydi
      ai_tts_provider: d.ai_tts_provider || 'openai',
      ai_tts_api_key: '',
      ai_voice_gateway: d.ai_voice_gateway || 'telegram',
    })
    setAiStatus({
      llm_set: !!d.ai_llm_api_key_set,
      llm_masked: d.ai_llm_api_key_masked || '',
      tts_set: !!d.ai_tts_api_key_set,
      tts_masked: d.ai_tts_api_key_masked || '',
    })
  }

  useEffect(() => {
    Promise.all([getSuperProfile(), getPlatformSettings()])
      .then(([profRes, platRes]) => {
        profileForm.setFieldsValue({ username: profRes.data.username })
        applyPlatformData(platRes.data)
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
      applyPlatformData(res.data)
      message.success('Platforma sozlamalari saqlandi')
    } catch (e) {
      message.error(e.response?.data?.detail || 'Xato yuz berdi')
    } finally {
      setPlatformLoading(false)
    }
  }

  const onAiSave = async (values) => {
    // API kalitlar bo'sh bo'lsa — yubormaymiz (eski qiymat saqlanib qoladi)
    const payload = {
      ai_llm_provider: values.ai_llm_provider,
      ai_llm_model: values.ai_llm_model,
      ai_tts_provider: values.ai_tts_provider,
      ai_voice_gateway: values.ai_voice_gateway,
    }
    if (values.ai_llm_api_key && values.ai_llm_api_key.trim()) {
      payload.ai_llm_api_key = values.ai_llm_api_key.trim()
    }
    if (values.ai_tts_api_key && values.ai_tts_api_key.trim()) {
      payload.ai_tts_api_key = values.ai_tts_api_key.trim()
    }
    setAiLoading(true)
    try {
      const res = await updatePlatformSettings(payload)
      applyPlatformData(res.data)
      message.success('AI sozlamalari saqlandi')
    } catch (e) {
      message.error(e.response?.data?.detail || 'Xato yuz berdi')
    } finally {
      setAiLoading(false)
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
    {
      key: 'ai',
      label: <span><RobotOutlined /> AI Operator</span>,
      children: (
        <Card style={{ maxWidth: 720 }}>
          <Title level={5} style={{ marginBottom: 4 }}>AI Call Operator — global konfiguratsiya</Title>
          <Text type="secondary" style={{ display: 'block', marginBottom: 20 }}>
            Bu sozlamalar barcha restoranlar uchun amal qiladi. Restoran adminlari bu yerga kirmaydi —
            ular faqat ovoz turi va maxsus ko'rsatmani sozlaydi.
          </Text>

          <Form form={aiForm} layout="vertical" onFinish={onAiSave}>
            <Divider orientation="left">LLM (matn modeli)</Divider>
            <Row gutter={16}>
              <Col xs={24} sm={12}>
                <Form.Item name="ai_llm_provider" label="Provayder">
                  <Select options={[
                    { value: 'openai', label: 'OpenAI' },
                  ]} />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item name="ai_llm_model" label="Model">
                  <Select options={[
                    { value: 'gpt-4o-mini', label: 'gpt-4o-mini (tez, arzon ~$0.15/1M)' },
                    { value: 'gpt-4o', label: 'gpt-4o (aniqroq ~$2.50/1M)' },
                  ]} />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item
              name="ai_llm_api_key"
              label={
                <span>
                  OpenAI API kalit{' '}
                  {aiStatus.llm_set
                    ? <Tag color="green" icon={<KeyOutlined />}>O'rnatilgan: {aiStatus.llm_masked}</Tag>
                    : <Tag color="red">Hali kiritilmagan</Tag>}
                </span>
              }
              extra={aiStatus.llm_set
                ? "Yangi qiymat kiritilsagina almashtiriladi. Bo'sh qoldirilsa eski kalit saqlanadi."
                : "sk-... bilan boshlanadigan OpenAI kalitni kiriting. https://platform.openai.com/api-keys"}
            >
              <Input.Password autoComplete="new-password" placeholder={aiStatus.llm_set ? '••••••••••••' : 'sk-...'} />
            </Form.Item>

            <Divider orientation="left">TTS (ovozli javob) — keyingi bosqich</Divider>
            <Alert
              type="info" showIcon style={{ marginBottom: 16 }}
              message="TTS hali ulanmagan"
              description="Hozir AI faqat matn javob qaytaradi. TTS (Text-to-Speech) keyingi bosqichda ulanadi — OpenAI TTS yoki ElevenLabs."
            />
            <Row gutter={16}>
              <Col xs={24} sm={12}>
                <Form.Item name="ai_tts_provider" label="TTS provayder">
                  <Select options={[
                    { value: 'openai', label: 'OpenAI TTS' },
                    { value: 'elevenlabs', label: 'ElevenLabs (yuqori sifat)' },
                  ]} />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item
                  name="ai_tts_api_key"
                  label={
                    <span>
                      TTS API kalit{' '}
                      {aiStatus.tts_set
                        ? <Tag color="green">…{aiStatus.tts_masked}</Tag>
                        : <Tag>Yo'q</Tag>}
                    </span>
                  }
                  extra="Bo'sh bo'lsa OpenAI kalit (yuqorida) ishlatiladi"
                >
                  <Input.Password autoComplete="new-password" placeholder={aiStatus.tts_set ? '••••••••' : "TTS uchun alohida kalit (ixtiyoriy)"} />
                </Form.Item>
              </Col>
            </Row>

            <Divider orientation="left">Ovoz gateway (telefon ulanish)</Divider>
            <Form.Item
              name="ai_voice_gateway"
              label="Qaysi kanal orqali mijoz AI bilan gaplashadi"
              extra="Telegram MVP — Telegram bot orqali ovoz xabar; Vapi/Twilio — real telefon raqami (keyingi bosqich)"
            >
              <Select options={[
                { value: 'telegram', label: '📱 Telegram voice xabarlar (MVP)' },
                { value: 'vapi', label: '☎️ Vapi (real telefon, hali ulanmagan)' },
                { value: 'twilio', label: '☎️ Twilio (real telefon, hali ulanmagan)' },
              ]} />
            </Form.Item>

            <Button type="primary" htmlType="submit" loading={aiLoading}
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
