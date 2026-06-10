import { useEffect, useState } from 'react'
import {
  Tabs, Form, Input, InputNumber, Button, Card, Typography,
  message, Divider, Row, Col, Select, Spin, Alert, Tag
} from 'antd'
import {
  UserOutlined, LockOutlined, GlobalOutlined, PhoneOutlined,
  MailOutlined, SaveOutlined, RobotOutlined, KeyOutlined,
  CreditCardOutlined,
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
  const [paymeForm] = Form.useForm()
  const [profileLoading, setProfileLoading] = useState(false)
  const [platformLoading, setPlatformLoading] = useState(false)
  const [aiLoading, setAiLoading] = useState(false)
  const [paymeLoading, setPaymeLoading] = useState(false)
  const [paymeKeyStatus, setPaymeKeyStatus] = useState({ set: false, masked: '' })
  const [providersMeta, setProvidersMeta] = useState([])         // backend'dan kelgan provider katalog
  const [keysStatus, setKeysStatus] = useState({})               // {openai: {set, masked}, groq: ...}
  const [selectedProvider, setSelectedProvider] = useState('openai')
  const [fetching, setFetching] = useState(true)
  const setAuth = useAuthStore((s) => s.setAuth)
  const logout = useAuthStore((s) => s.logout)

  const applyPlatformData = (d) => {
    platformForm.setFieldsValue(d)
    const prov = d.ai_llm_provider || 'openai'
    aiForm.setFieldsValue({
      ai_llm_provider: prov,
      ai_llm_model: d.ai_llm_model || 'gpt-4o-mini',
      ai_llm_api_key: '',   // hech qachon plaintext kelmaydi
      ai_stt_provider: d.ai_stt_provider || 'openai',
      ai_tts_provider: d.ai_tts_provider || 'openai',
      ai_voice_gateway: d.ai_voice_gateway || 'telegram',
    })
    setProvidersMeta(d.ai_providers || [])
    setKeysStatus(d.ai_llm_api_keys_status || {})
    setSelectedProvider(prov)
    // Payme Subscribe (obuna avtopay)
    paymeForm.setFieldsValue({
      payme_subscribe_merchant_id: d.payme_subscribe_merchant_id || '',
      payme_subscribe_test_mode: d.payme_subscribe_test_mode !== false,
      payme_subscribe_key: '',   // kalit hech qachon plaintext kelmaydi
    })
    setPaymeKeyStatus(d.payme_subscribe_key_status || { set: false, masked: '' })
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
    const payload = {
      ai_llm_provider: values.ai_llm_provider,
      ai_llm_model: values.ai_llm_model,
      ai_stt_provider: values.ai_stt_provider,
      ai_tts_provider: values.ai_tts_provider,
      ai_voice_gateway: values.ai_voice_gateway,
    }
    // API kalit faqat kiritilgan bo'lsa yuboriladi (tanlangan provayder uchun)
    const keys = {}
    if (values.ai_llm_api_key && values.ai_llm_api_key.trim()) {
      keys[values.ai_llm_provider] = values.ai_llm_api_key.trim()
    }
    if (values.ai_aisha_api_key && values.ai_aisha_api_key.trim()) {
      keys.aisha = values.ai_aisha_api_key.trim()
    }
    if (Object.keys(keys).length) {
      payload.ai_llm_api_keys = keys
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

  const onPaymeSave = async (values) => {
    const payload = {
      payme_subscribe_merchant_id: values.payme_subscribe_merchant_id || '',
      payme_subscribe_test_mode: !!values.payme_subscribe_test_mode,
    }
    // Kalit faqat kiritilgan bo'lsa yuboriladi (bo'sh → eski saqlanadi)
    if (values.payme_subscribe_key && values.payme_subscribe_key.trim()) {
      payload.payme_subscribe_key = values.payme_subscribe_key.trim()
    }
    setPaymeLoading(true)
    try {
      const res = await updatePlatformSettings(payload)
      applyPlatformData(res.data)
      message.success('Avtomatik to\'lov sozlamalari saqlandi')
    } catch (e) {
      message.error(e.response?.data?.detail || 'Xato yuz berdi')
    } finally {
      setPaymeLoading(false)
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
      children: (() => {
        // Joriy tanlangan provayder uchun metadata
        const currentMeta = providersMeta.find(p => p.name === selectedProvider) || {}
        const currentKeyStatus = keysStatus[selectedProvider] || { set: false, masked: '' }
        const modelOptions = (currentMeta.models || []).map(m => ({
          value: m.value,
          label: `${m.label}${m.notes ? ' — ' + m.notes : ''}`,
        }))

        // Provayder tanlanganda model'ni avtomatik birinchi modelga o'rnatish
        const onProviderChange = (newProvider) => {
          setSelectedProvider(newProvider)
          const meta = providersMeta.find(p => p.name === newProvider)
          const defaultModel = meta?.models?.[0]?.value
          if (defaultModel) {
            aiForm.setFieldsValue({ ai_llm_model: defaultModel, ai_llm_api_key: '' })
          }
        }

        return (
        <Card style={{ maxWidth: 760 }}>
          <Title level={5} style={{ marginBottom: 4 }}>AI Call Operator — global konfiguratsiya</Title>
          <Text type="secondary" style={{ display: 'block', marginBottom: 20 }}>
            Bu sozlamalar barcha restoranlar uchun amal qiladi. Restoran adminlari bu yerga kirmaydi —
            ular faqat ovoz turi va maxsus ko'rsatmani sozlaydi.
          </Text>

          <Form form={aiForm} layout="vertical" onFinish={onAiSave}>
            <Divider orientation="left">LLM (matn modeli)</Divider>

            <Alert
              type="success" showIcon style={{ marginBottom: 16 }}
              message="Bepul variantlar mavjud"
              description="Groq (Llama 3.x) va Google Gemini bepul tier'da yaxshi sifat beradi — kreditka kerak emas. OpenAI/Claude esa pullik lekin yuqori sifat."
            />

            <Row gutter={16}>
              <Col xs={24} sm={12}>
                <Form.Item name="ai_llm_provider" label="LLM Provayder">
                  <Select onChange={onProviderChange} options={providersMeta.map(p => ({
                    value: p.name,
                    label: p.display_name + (p.requires_billing ? '' : ' 🆓'),
                  }))} />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item name="ai_llm_model" label="Model">
                  <Select options={modelOptions} />
                </Form.Item>
              </Col>
            </Row>

            <Form.Item
              name="ai_llm_api_key"
              label={
                <span>
                  {currentMeta.display_name || 'API'} kalit{' '}
                  {currentKeyStatus.set
                    ? <Tag color="green" icon={<KeyOutlined />}>O'rnatilgan: {currentKeyStatus.masked}</Tag>
                    : <Tag color="red">Hali kiritilmagan</Tag>}
                </span>
              }
              extra={
                <span>
                  {currentKeyStatus.set
                    ? "Yangi qiymat kiritilsagina almashtiriladi. Bo'sh qoldirilsa eski kalit saqlanadi. "
                    : `${currentMeta.api_key_prefix || ''}... bilan boshlanadigan kalitni kiriting. `}
                  {currentMeta.api_key_help_url && (
                    <a href={currentMeta.api_key_help_url} target="_blank" rel="noreferrer">
                      Kalit olish →
                    </a>
                  )}
                </span>
              }
            >
              <Input.Password
                autoComplete="new-password"
                placeholder={currentKeyStatus.set ? '••••••••••••' : `${currentMeta.api_key_prefix || 'API key'}...`}
              />
            </Form.Item>

            {/* Boshqa provayder kalit holatlari — tezkor ko'rinish */}
            <div style={{ marginBottom: 16, padding: 12, background: '#fafafa', borderRadius: 8 }}>
              <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 6 }}>
                BARCHA PROVAYDER KALITLARI HOLATI (har birini alohida sozlay olasiz):
              </Text>
              {providersMeta.map(p => {
                const st = keysStatus[p.name] || {}
                return (
                  <Tag
                    key={p.name}
                    color={st.set ? 'green' : 'default'}
                    style={{ marginBottom: 4, cursor: 'pointer' }}
                    onClick={() => onProviderChange(p.name)}
                  >
                    {p.display_name}: {st.set ? `…${st.masked.replace('…', '')}` : 'yo\'q'}
                  </Tag>
                )
              })}
            </div>

            <Divider orientation="left">STT (ovozni matnga)</Divider>
            <Form.Item
              name="ai_stt_provider"
              label="Speech-to-Text provayder"
              extra={
                <span>
                  <b>Aisha</b> — O'zbek tili uchun maxsus, ~90% aniqlik (425 so'm/daq).{' '}
                  <b>Groq Whisper</b> — bepul, ~75% aniqlik.{' '}
                  <b>OpenAI</b> — $0.006/daq, ~75% aniqlik.
                </span>
              }
            >
              <Select options={[
                { value: 'aisha', label: '🇺🇿 Aisha (O\'zbek tili uchun, 90% aniqlik — tavsiya)' },
                { value: 'groq', label: 'Groq Whisper (BEPUL, 75% aniqlik)' },
                { value: 'openai', label: 'OpenAI Whisper ($0.006/daq, 75% aniqlik)' },
              ]} />
            </Form.Item>

            <Form.Item
              shouldUpdate={(prev, cur) => prev.ai_stt_provider !== cur.ai_stt_provider}
              noStyle
            >
              {({ getFieldValue }) => getFieldValue('ai_stt_provider') === 'aisha' && (
                <Form.Item
                  name="ai_aisha_api_key"
                  label={
                    <span>
                      Aisha API kalit{' '}
                      {(keysStatus.aisha && keysStatus.aisha.set)
                        ? <Tag color="green" icon={<KeyOutlined />}>O'rnatilgan: {keysStatus.aisha.masked}</Tag>
                        : <Tag color="red">Hali kiritilmagan</Tag>}
                    </span>
                  }
                  extra={
                    <span>
                      Aisha hisobingizdan API kalitni oling: {' '}
                      <a href="https://aisha.group" target="_blank" rel="noreferrer">aisha.group</a> → Space → API Keys.
                      {' '}Yangi qiymat kiritilsagina almashtiriladi.
                    </span>
                  }
                >
                  <Input.Password
                    autoComplete="new-password"
                    placeholder={(keysStatus.aisha && keysStatus.aisha.set) ? '••••••••••••' : 'aisha-key...'}
                  />
                </Form.Item>
              )}
            </Form.Item>

            <Divider orientation="left">TTS (matnni ovozga)</Divider>
            <Form.Item
              name="ai_tts_provider"
              label="Text-to-Speech provayder"
              extra="OpenAI TTS — ~$0.015/1000 belgi. 'O'chirilgan' bo'lsa AI faqat matn javob qaytaradi (bepul rejim)."
            >
              <Select options={[
                { value: 'openai', label: 'OpenAI TTS ($0.015/1k belgi)' },
                { value: 'none', label: "🆓 O'chirilgan — faqat matn javob (bepul)" },
              ]} />
            </Form.Item>

            <Divider orientation="left">Ovoz gateway</Divider>
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
        )
      })(),
    },
    {
      key: 'payme_subscribe',
      label: <span><CreditCardOutlined /> Avtomatik to'lov</span>,
      children: (
        <Card style={{ maxWidth: 600 }}>
          <Title level={5} style={{ marginBottom: 4 }}>Payme Subscribe — obuna avtopay</Title>
          <Text type="secondary" style={{ display: 'block', marginBottom: 20 }}>
            Restoran obunalarini avtomatik undirish uchun PLATFORMA (Mezbon) Payme kassasi
            credential'lari. Bu restoran kassasi emas — platforma yuridik shaxsi kassasi.
            Payme Business kabinetidan olinadi.
          </Text>

          <Form form={paymeForm} layout="vertical" onFinish={onPaymeSave}>
            <Form.Item name="payme_subscribe_merchant_id" label="Subscribe kassa ID (merchant_id)">
              <Input prefix={<CreditCardOutlined />} placeholder="5e7c1e..." />
            </Form.Item>

            <Form.Item
              name="payme_subscribe_key"
              label={
                <span>
                  Subscribe kassa kaliti{' '}
                  {paymeKeyStatus.set
                    ? <Tag color="green" icon={<KeyOutlined />}>O'rnatilgan: {paymeKeyStatus.masked}</Tag>
                    : <Tag color="red">Hali kiritilmagan</Tag>}
                </span>
              }
              extra={paymeKeyStatus.set
                ? "Yangi qiymat kiritilsagina almashtiriladi. Bo'sh qoldirilsa eski kalit saqlanadi."
                : "Payme Business kabinetidan Subscribe kassa kalitini kiriting."}
            >
              <Input.Password
                autoComplete="new-password"
                placeholder={paymeKeyStatus.set ? '••••••••••••' : 'kalit...'}
              />
            </Form.Item>

            <Form.Item name="payme_subscribe_test_mode" label="Rejim">
              <Select options={[
                { value: true, label: '🧪 Sandbox (test.paycom.uz)' },
                { value: false, label: '🟢 Live (checkout.paycom.uz)' },
              ]} />
            </Form.Item>

            <Alert
              type="warning" showIcon style={{ marginBottom: 16 }}
              message="Yuridik shaxs talab qilinadi"
              description="Subscribe kassasi faqat ro'yxatdan o'tgan yuridik shaxs (YaTT/MChJ) uchun ochiladi. Token shifrlash kaliti (PAYME_TOKEN_ENC_KEY) serverda .env'da bo'lishi shart."
            />

            <Button type="primary" htmlType="submit" loading={paymeLoading}
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
