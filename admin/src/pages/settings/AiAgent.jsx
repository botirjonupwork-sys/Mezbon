import { useEffect, useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Form, Input, InputNumber, Button, Typography, Row, Col,
  message, Spin, Switch, Alert, Select, Modal, Tag,
} from 'antd'
import {
  ArrowLeftOutlined, SaveOutlined, PhoneOutlined, ExperimentOutlined,
  SendOutlined, ReloadOutlined,
} from '@ant-design/icons'
import { getSettings, updateSettings, getMyPlan, aiProcessCall } from '../../api'
import { useAuthStore } from '../../store/auth'

const { Title, Text } = Typography

const cardStyle = { marginBottom: 12, borderRadius: 14, border: '1px solid #ececec', boxShadow: 'none' }
const cardBody = { padding: 24 }
const sectionLabel = { fontSize: 12, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: 18, display: 'block' }

export default function AiAgentSettings() {
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [hasFeature, setHasFeature] = useState(true)
  const { currentRestaurantId: restaurantId } = useAuthStore()
  const restParams = restaurantId ? { restaurant_id: restaurantId } : {}

  // Test rejimi
  const [testOpen, setTestOpen] = useState(false)
  const [testCallId, setTestCallId] = useState('')
  const [testInput, setTestInput] = useState('')
  const [testMessages, setTestMessages] = useState([])
  const [testSending, setTestSending] = useState(false)
  const testEndRef = useRef(null)

  const openTest = () => {
    setTestCallId(`test:${Date.now()}`)
    setTestMessages([])
    setTestInput('')
    setTestOpen(true)
  }

  const closeTest = () => {
    setTestOpen(false)
    setTestMessages([])
  }

  const resetTest = () => {
    setTestCallId(`test:${Date.now()}`)
    setTestMessages([])
  }

  const sendTest = async () => {
    const text = testInput.trim()
    if (!text) return
    setTestSending(true)
    setTestMessages((m) => [...m, { role: 'user', content: text }])
    setTestInput('')
    try {
      const r = await aiProcessCall(
        { call_id: testCallId, user_phone: '+998000000000', message: text, user_name: 'Test' },
        restParams,
      )
      const data = r.data || {}
      setTestMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: data.reply || '(bo\'sh javob)',
          actions: data.actions || [],
          cart: data.cart || [],
          confirmed: data.confirmed,
          order_id: data.order_id,
        },
      ])
      if (data.order_id || data.transferred || (data.actions || []).some(a => a.type === 'end_call')) {
        // Sessiya yakunlandi, yangi ID generatsiya qilamiz
        setTestCallId(`test:${Date.now()}`)
      }
    } catch (e) {
      const detail = e?.response?.data?.detail || e.message
      setTestMessages((m) => [...m, { role: 'error', content: detail }])
    } finally {
      setTestSending(false)
      setTimeout(() => testEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
    }
  }

  useEffect(() => {
    if (!restaurantId) { setLoading(false); return }
    setLoading(true)
    Promise.all([
      getSettings(restParams).catch(() => ({ data: {} })),
      getMyPlan(restParams).catch(() => ({ data: { features: {} } })),
    ])
      .then(([sRes, pRes]) => {
        const d = sRes.data || {}
        form.setFieldsValue(d)
        const features = pRes.data?.features || {}
        setHasFeature(!!features.ai_agent)
      })
      .catch(() => message.error("Ma'lumotlarni yuklashda xato"))
      .finally(() => setLoading(false))
  }, [restaurantId])

  const handleSave = async () => {
    setSaving(true)
    try {
      const values = await form.validateFields()
      await updateSettings(values, restParams)
      message.success('AI Agent sozlamalari saqlandi')
    } catch (err) {
      if (!err?.errorFields) message.error('Saqlashda xato')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div style={{ display: 'flex', justifyContent: 'center', minHeight: 400, alignItems: 'center' }}><Spin size="large" /></div>
  }

  if (!hasFeature) {
    return (
      <div style={{ maxWidth: 800, margin: '0 auto' }}>
        <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/settings')} style={{ marginBottom: 16, padding: 0, color: '#6b7280' }}>
          Sozlamalar
        </Button>
        <Alert
          type="warning" showIcon
          message="AI Agent tarifda yo'q"
          description="Bu funksiyadan foydalanish uchun yuqori tarifga o'tishingiz kerak."
          action={<Button type="primary" onClick={() => navigate('/billing')}>Tariflar</Button>}
        />
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <div style={{ marginBottom: 24 }}>
        <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/settings')} style={{ marginBottom: 8, padding: 0, color: '#6b7280' }}>
          Sozlamalar
        </Button>
        <Title level={3} style={{ marginBottom: 4, marginTop: 0, fontWeight: 600 }}>
          AI Telefon Operator
        </Title>
        <Text type="secondary" style={{ fontSize: 14 }}>
          Mijoz qo'ng'irog'iga AI javob beradi, buyurtmani qabul qiladi va yetkazadi
        </Text>
      </div>

      <Form form={form} layout="vertical" requiredMark={false}>
        {/* Yoqish/o'chirish */}
        <Card style={cardStyle} styles={{ body: cardBody }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <span style={{ ...sectionLabel, marginBottom: 4 }}>AI Agent</span>
              <Text type="secondary" style={{ fontSize: 13 }}>
                Yoqilganda restoran telefon raqamiga AI operator javob beradi
              </Text>
            </div>
            <Form.Item name="ai_agent_enabled" valuePropName="checked" style={{ marginBottom: 0 }}>
              <Switch />
            </Form.Item>
          </div>
        </Card>

        <Form.Item noStyle shouldUpdate={(p, c) => p.ai_agent_enabled !== c.ai_agent_enabled}>
          {({ getFieldValue }) => getFieldValue('ai_agent_enabled') && (
            <>
              {/* Ovoz va til */}
              <Card style={cardStyle} styles={{ body: cardBody }}>
                <span style={sectionLabel}>Ovoz va til</span>
                <Row gutter={16}>
                  <Col xs={24} md={12}>
                    <Form.Item name="ai_agent_voice" label="Operator ovozi">
                      <Select options={[
                        { value: 'female', label: '👩 Ayol ovozi' },
                        { value: 'male', label: '👨 Erkak ovozi' },
                      ]} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item name="ai_agent_language" label="Suhbat tili">
                      <Select options={[
                        { value: 'uz', label: "🇺🇿 O'zbekcha" },
                        { value: 'ru', label: '🇷🇺 Ruscha' },
                        { value: 'auto', label: '🌐 Avto (mijoz tiliga moslashadi)' },
                      ]} />
                    </Form.Item>
                  </Col>
                </Row>
              </Card>

              {/* Kirish tabrigi */}
              <Card style={cardStyle} styles={{ body: cardBody }}>
                <span style={sectionLabel}>Kirish tabrigi</span>
                <Text type="secondary" style={{ display: 'block', marginBottom: 12, fontSize: 13 }}>
                  AI qo'ng'iroqni qabul qilganda yoki Telegram'da ovoz xabar olganda
                  aytadigan birinchi gap. Bo'sh qoldirilsa standart tabrik ishlatiladi.
                </Text>
                <Form.Item name="ai_agent_greeting" style={{ marginBottom: 0 }}>
                  <Input.TextArea
                    rows={2}
                    placeholder="Misol: Assalomu alaykum, Muhsina Dollar Somsa, sizni eshityapman. Buyurtma berasizmi?"
                    maxLength={300}
                    showCount
                  />
                </Form.Item>
              </Card>

              {/* Ish vaqti va xarajat nazorati */}
              <Card style={cardStyle} styles={{ body: cardBody }}>
                <span style={sectionLabel}>Ish vaqti va limitlar</span>
                <Row gutter={16}>
                  <Col xs={24}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
                      <div>
                        <Text strong style={{ display: 'block' }}>Faqat ish vaqtida javob berish</Text>
                        <Text type="secondary" style={{ fontSize: 13 }}>
                          Yoqilsa, restoran yopiq vaqtida AI javob bermaydi. Restoran sozlamalaridagi ish vaqti ishlatiladi.
                        </Text>
                      </div>
                      <Form.Item name="ai_agent_work_hours_only" valuePropName="checked" style={{ marginBottom: 0 }}>
                        <Switch />
                      </Form.Item>
                    </div>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item
                      name="ai_agent_max_call_minutes"
                      label="Max suhbat (daqiqa)"
                      extra="Xarajat nazorati uchun. Shu vaqtdan oshsa AI suhbatni yakunlaydi"
                    >
                      <InputNumber style={{ width: '100%' }} min={1} max={60} step={1} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item
                      name="ai_agent_fallback_phone"
                      label="Operator telefoni (uzatish)"
                      extra="AI mijoz so'rovini tushunmasa shu raqamga uzatadi (ixtiyoriy)"
                    >
                      <Input prefix={<PhoneOutlined />} placeholder="+998901234567" />
                    </Form.Item>
                  </Col>
                </Row>
              </Card>

              {/* System prompt */}
              <Card style={{ ...cardStyle, marginBottom: 24 }} styles={{ body: cardBody }}>
                <span style={sectionLabel}>Maxsus ko'rsatma</span>
                <Text type="secondary" style={{ display: 'block', marginBottom: 12, fontSize: 13 }}>
                  Restoraningizga oid qo'shimcha qoidalar (masalan: "Pishloqsiz somsa ham bor" yoki "Penshenerlar uchun 10% chegirma").
                  AI <b>faqat sizning menyungizdan</b> mahsulot taklif qiladi va buyurtma qabul qiladi.
                </Text>
                <Form.Item name="ai_agent_prompt" style={{ marginBottom: 0 }}>
                  <Input.TextArea
                    rows={5}
                    placeholder="Misol: Bizning restoran 5 turli somsa pishiradi. Diyetik (mantili 200 kkal) ham bor. Mijozdan har doim manzilni aniq so'rang."
                  />
                </Form.Item>
              </Card>

              {/* Texnik ma'lumot */}
              <Alert
                type="info" showIcon style={{ marginBottom: 24, borderRadius: 10 }}
                message="LLM va API kalit"
                description="AI provayder (OpenAI), model va API kalit mezbon platforma tomonidan boshqariladi — qo'shimcha sozlash kerak emas."
              />
            </>
          )}
        </Form.Item>

        <Row gutter={12}>
          <Col xs={24} md={8}>
            <Button
              icon={<ExperimentOutlined />} block size="large"
              onClick={openTest}
              style={{ height: 46, fontWeight: 500, borderRadius: 10 }}
            >
              Sinab ko'rish
            </Button>
          </Col>
          <Col xs={24} md={16}>
            <Button
              type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSave}
              size="large" block
              style={{ height: 46, fontWeight: 500, borderRadius: 10, background: '#111827', borderColor: '#111827' }}
            >
              Saqlash
            </Button>
          </Col>
        </Row>
      </Form>

      {/* Test rejimi — matn orqali AI bilan suhbat */}
      <Modal
        title={<span><ExperimentOutlined /> AI Operatorni sinab ko'rish</span>}
        open={testOpen}
        onCancel={closeTest}
        width={640}
        footer={null}
      >
        <Alert
          type="info" showIcon style={{ marginBottom: 12 }}
          message="Matnli test rejimi"
          description="Bu yerda mijoz tomonidan yuborilgan xabarni simulyatsiya qila olasiz. AI'ning haqiqiy menyungiz bo'yicha qanday javob berishini ko'rasiz. Test buyurtmasi yaratiladi (real), shuning uchun keyinroq uni bekor qiling."
        />
        <div style={{
          maxHeight: 360, overflowY: 'auto', padding: 12,
          background: '#fafafa', borderRadius: 8, marginBottom: 12,
          border: '1px solid #f0f0f0',
        }}>
          {testMessages.length === 0 ? (
            <Text type="secondary">Suhbatni boshlash uchun pastdagi maydonga yozing…</Text>
          ) : testMessages.map((m, i) => (
            <div key={i} style={{
              marginBottom: 10,
              display: 'flex',
              justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start',
            }}>
              <div style={{
                maxWidth: '75%', padding: '8px 12px', borderRadius: 12,
                background: m.role === 'user' ? '#1677ff' : (m.role === 'error' ? '#fff1f0' : '#fff'),
                color: m.role === 'user' ? '#fff' : (m.role === 'error' ? '#cf1322' : '#111'),
                border: m.role !== 'user' ? '1px solid #f0f0f0' : 'none',
                whiteSpace: 'pre-wrap',
              }}>
                <div>{m.content}</div>
                {m.cart && m.cart.length > 0 && (
                  <div style={{ marginTop: 6, fontSize: 12 }}>
                    🛒 {m.cart.map(c => `${c.name} x${c.quantity}`).join(', ')}
                  </div>
                )}
                {m.order_id && <Tag color="green" style={{ marginTop: 6 }}>✓ Order #{m.order_id}</Tag>}
                {(m.actions || []).some(a => a.type === 'transfer_to_catering') && (
                  <Tag color="orange" style={{ marginTop: 6 }}>Catering kanaliga uzatildi</Tag>
                )}
                {(m.actions || []).some(a => a.type === 'end_call') && (
                  <Tag style={{ marginTop: 6 }}>Suhbat yakunlandi</Tag>
                )}
              </div>
            </div>
          ))}
          <div ref={testEndRef} />
        </div>
        <Input.Group compact>
          <Input
            value={testInput}
            onChange={(e) => setTestInput(e.target.value)}
            onPressEnter={sendTest}
            placeholder="Masalan: 5 ta somsa olaman"
            style={{ width: 'calc(100% - 120px)' }}
            disabled={testSending}
          />
          <Button icon={<ReloadOutlined />} onClick={resetTest} disabled={testSending} />
          <Button
            type="primary" icon={<SendOutlined />}
            onClick={sendTest} loading={testSending} disabled={!testInput.trim()}
          >
            Yuborish
          </Button>
        </Input.Group>
      </Modal>
    </div>
  )
}
