import { useEffect, useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Form, Input, InputNumber, Button, Typography, Row, Col,
  message, Spin, Switch, Alert, Select, Modal, Tag, Collapse, Divider,
} from 'antd'
import {
  ArrowLeftOutlined, SaveOutlined, PhoneOutlined, ExperimentOutlined,
  SendOutlined, ReloadOutlined, SoundOutlined, CommentOutlined,
  FileTextOutlined, ClockCircleOutlined, MessageOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import { getSettings, updateSettings, getMyPlan, aiProcessCall, aiCallStart, getAiSystemPromptPreview } from '../../api'
import { useAuthStore } from '../../store/auth'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

const cardStyle = { marginBottom: 12, borderRadius: 14, border: '1px solid #ececec', boxShadow: 'none' }
const cardBody = { padding: 24 }
const sectionLabel = {
  fontSize: 12, fontWeight: 600, color: '#6b7280',
  textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: 12, display: 'block',
}

const DEFAULT_CFG = {
  offline_reply: '',
  time_limit_reply: '',
  upsell_enabled: true,
  sms_location_enabled: true,
  sms_location_template: '',
  system_prompt_override: '',
  farewell_hint: '',
}

const PROMPT_HELP = `Standart operator qoidalari (tizim tomonidan):
• Faqat sizning menyungizdan taklif qiladi
• Salom → buyurtma → upsell → yetkazish/pickup → manzil → tasdiqlash → xayrlash
• Narxni so‘rasa darhol aytadi
• Noaniq ovozda taxmin qilmaydi, qayta so‘raydi
• Katta miqdorda cateringga uzatadi

Pastdagi maydonlarga o‘zingizning qo‘shimcha qoidalaringizni yozing.`

export default function AiAgentSettings() {
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [hasFeature, setHasFeature] = useState(true)
  const { currentRestaurantId: restaurantId } = useAuthStore()
  const restParams = restaurantId ? { restaurant_id: restaurantId } : {}

  const [testOpen, setTestOpen] = useState(false)
  const [testCallId, setTestCallId] = useState('')
  const [testInput, setTestInput] = useState('')
  const [testMessages, setTestMessages] = useState([])
  const [testSending, setTestSending] = useState(false)
  const testEndRef = useRef(null)

  // Vaqtinchalik: tizim promptini ko'rsatish
  const [sysPrompt, setSysPrompt] = useState('')
  const [sysPromptLoading, setSysPromptLoading] = useState(false)
  const [sysPromptChars, setSysPromptChars] = useState(0)

  const loadSysPrompt = () => {
    if (!restaurantId) return
    setSysPromptLoading(true)
    getAiSystemPromptPreview(restParams)
      .then((r) => {
        setSysPrompt(r.data?.prompt || '')
        setSysPromptChars(r.data?.chars || 0)
      })
      .catch(() => setSysPrompt('Yuklab bo‘lmadi'))
      .finally(() => setSysPromptLoading(false))
  }

  const openTest = async () => {
    const cid = `test:${Date.now()}`
    setTestCallId(cid)
    setTestMessages([])
    setTestInput('')
    setTestOpen(true)
    try {
      const r = await aiCallStart({ call_id: cid, user_phone: '+998000000000' }, restParams)
      const greeting = r.data?.reply || ''
      if (greeting) setTestMessages([{ role: 'assistant', content: greeting, greeting: true }])
    } catch { /* ignore */ }
  }

  const closeTest = () => { setTestOpen(false); setTestMessages([]) }
  const resetTest = () => { setTestCallId(`test:${Date.now()}`); setTestMessages([]) }

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
      setTestMessages((m) => [...m, {
        role: 'assistant',
        content: data.reply || '(bo\'sh javob)',
        actions: data.actions || [],
        cart: data.cart || [],
        confirmed: data.confirmed,
        order_id: data.order_id,
      }])
      if (
        data.ended_reason === 'conversation_complete'
        || data.transferred
        || (data.actions || []).some(a => a.type === 'end_call' && a.reason !== 'user_hangup')
      ) {
        setTestCallId(`test:${Date.now()}`)
      }
    } catch (e) {
      setTestMessages((m) => [...m, { role: 'error', content: e?.response?.data?.detail || e.message }])
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
        const cfg = { ...DEFAULT_CFG, ...(d.ai_agent_config || {}) }
        form.setFieldsValue({
          ai_agent_enabled: !!d.ai_agent_enabled,
          ai_agent_voice: d.ai_agent_voice || 'female',
          ai_agent_language: d.ai_agent_language || 'uz',
          ai_agent_greeting: d.ai_agent_greeting || '',
          ai_agent_prompt: d.ai_agent_prompt || '',
          ai_agent_work_hours_only: !!d.ai_agent_work_hours_only,
          ai_agent_max_call_minutes: d.ai_agent_max_call_minutes ?? 10,
          ai_agent_fallback_phone: d.ai_agent_fallback_phone || '',
          ...cfg,
        })
        setHasFeature(!!(pRes.data?.features || {}).ai_agent)
        if ((pRes.data?.features || {}).ai_agent) {
          getAiSystemPromptPreview(restParams)
            .then((r) => {
              setSysPrompt(r.data?.prompt || '')
              setSysPromptChars(r.data?.chars || 0)
            })
            .catch(() => {})
        }
      })
      .catch(() => message.error("Ma'lumotlarni yuklashda xato"))
      .finally(() => setLoading(false))
  }, [restaurantId])

  const handleSave = async () => {
    setSaving(true)
    try {
      const v = await form.validateFields()
      const payload = {
        ai_agent_enabled: !!v.ai_agent_enabled,
        ai_agent_voice: v.ai_agent_voice,
        ai_agent_language: v.ai_agent_language,
        ai_agent_greeting: v.ai_agent_greeting || '',
        ai_agent_prompt: v.ai_agent_prompt || '',
        ai_agent_work_hours_only: !!v.ai_agent_work_hours_only,
        ai_agent_max_call_minutes: Number(v.ai_agent_max_call_minutes) || 10,
        ai_agent_fallback_phone: v.ai_agent_fallback_phone || '',
        ai_agent_config: {
          offline_reply: v.offline_reply || '',
          time_limit_reply: v.time_limit_reply || '',
          upsell_enabled: v.upsell_enabled !== false,
          sms_location_enabled: v.sms_location_enabled !== false,
          sms_location_template: v.sms_location_template || '',
          system_prompt_override: v.system_prompt_override || '',
          farewell_hint: v.farewell_hint || '',
        },
      }
      await updateSettings(payload, restParams)
      message.success('AI Operator sozlamalari saqlandi')
      loadSysPrompt()
    } catch (err) {
      if (!err?.errorFields) message.error('Saqlashda xato')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', minHeight: 400, alignItems: 'center' }}>
        <Spin size="large" />
      </div>
    )
  }

  if (!hasFeature) {
    return (
      <div style={{ maxWidth: 860, margin: '0 auto' }}>
        <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/settings')} style={{ marginBottom: 16, padding: 0, color: '#6b7280' }}>
          Sozlamalar
        </Button>
        <Alert
          type="warning" showIcon
          message="AI Operator tarifda yo'q"
          description="Bu funksiyadan foydalanish uchun yuqori tarifga o'ting."
          action={<Button type="primary" onClick={() => navigate('/billing')}>Tariflar</Button>}
        />
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 860, margin: '0 auto' }}>
      <div style={{ marginBottom: 20 }}>
        <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/settings')} style={{ marginBottom: 8, padding: 0, color: '#6b7280' }}>
          Sozlamalar
        </Button>
        <Title level={3} style={{ marginBottom: 4, marginTop: 0, fontWeight: 600 }}>
          AI Telefon Operator
        </Title>
        <Text type="secondary" style={{ fontSize: 14 }}>
          Prompt, salom, ovoz, SMS, limitlar — hammasi shu yerda. Oddiy til bilan sozlang.
        </Text>
      </div>

      <Form form={form} layout="vertical" requiredMark={false} initialValues={DEFAULT_CFG}>
        {/* 1. Asosiy */}
        <Card style={cardStyle} styles={{ body: cardBody }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <span style={{ ...sectionLabel, marginBottom: 4 }}>1. Asosiy</span>
              <Text strong style={{ display: 'block', fontSize: 15 }}>AI Operatorni yoqish</Text>
              <Text type="secondary" style={{ fontSize: 13 }}>
                Yoqilganda mijoz ovoz/chat orqali buyurtma berishi mumkin
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
              {/* 2. Ovoz va til */}
              <Card style={cardStyle} styles={{ body: cardBody }}>
                <span style={sectionLabel}><SoundOutlined /> 2. Ovoz va til</span>
                <Row gutter={16}>
                  <Col xs={24} md={12}>
                    <Form.Item name="ai_agent_voice" label="Operator ovozi" extra="TTS da eshitiladigan ovoz">
                      <Select options={[
                        { value: 'female', label: 'Ayol ovozi' },
                        { value: 'male', label: 'Erkak ovozi' },
                      ]} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item name="ai_agent_language" label="Suhbat tili">
                      <Select options={[
                        { value: 'uz', label: "O'zbekcha" },
                        { value: 'ru', label: 'Ruscha' },
                        { value: 'auto', label: 'Avto (mijoz tiliga moslashadi)' },
                      ]} />
                    </Form.Item>
                  </Col>
                </Row>
              </Card>

              {/* 3. Salom */}
              <Card style={cardStyle} styles={{ body: cardBody }}>
                <span style={sectionLabel}><CommentOutlined /> 3. Salomlashish</span>
                <Text type="secondary" style={{ display: 'block', marginBottom: 12, fontSize: 13 }}>
                  Qo‘ng‘iroq / ovoz xabar boshida aytiladigan birinchi gap. Bo‘sh qoldirsangiz — standart tabrik.
                </Text>
                <Form.Item name="ai_agent_greeting" style={{ marginBottom: 0 }}>
                  <TextArea
                    rows={3}
                    maxLength={400}
                    showCount
                    placeholder="Assalomu alaykum! Muhsina Dollar Somsa. Buyurtma berasizmi yoki menyu bilan tanishasizmi?"
                  />
                </Form.Item>
              </Card>

              {/* 4. Prompt */}
              <Card style={cardStyle} styles={{ body: cardBody }}>
                <span style={sectionLabel}><FileTextOutlined /> 4. Prompt va ko‘rsatmalar</span>

                <Alert
                  type="warning" showIcon style={{ marginBottom: 12, borderRadius: 10 }}
                  message={`Tizim prompti (vaqtinchalik ko‘rsatiladi) · ${sysPromptChars || '…'} belgi`}
                  description="LLM ga yuboriladigan to‘liq system prompt. O‘zgartirish uchun pastdagi maydonlar yoki «to‘liq override» dan foydalaning."
                  action={
                    <Button size="small" loading={sysPromptLoading} onClick={loadSysPrompt}>
                      Yangilash
                    </Button>
                  }
                />
                <div style={{
                  marginBottom: 16, maxHeight: 320, overflow: 'auto',
                  background: '#111827', color: '#e5e7eb', borderRadius: 10,
                  padding: 14, fontSize: 12, lineHeight: 1.55, whiteSpace: 'pre-wrap',
                  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                }}>
                  {sysPromptLoading ? 'Yuklanmoqda…' : (sysPrompt || 'Hali yuklanmadi — «Yangilash» ni bosing')}
                </div>

                <Alert
                  type="info" showIcon style={{ marginBottom: 16, borderRadius: 10 }}
                  message="Qisqa eslatma"
                  description={<Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap', fontSize: 13 }}>{PROMPT_HELP}</Paragraph>}
                />
                <Form.Item
                  name="ai_agent_prompt"
                  label="Sizning maxsus ko‘rsatmangiz"
                  extra="Masalan: chegirma, maxsus taom, “har doir mo‘ljal so‘ra”, brend ohangi…"
                >
                  <TextArea
                    rows={5}
                    placeholder="Misol: Bizda 5 turli somsa bor. Diyetik somsa 200 kkal. Penshenerlarga 10% chegirma. Manzilda mo‘ljalni albatta so‘ra."
                  />
                </Form.Item>
                <Form.Item
                  name="farewell_hint"
                  label="Xayrlashish uslubi (ixtiyoriy)"
                  extra="Suhbat oxirida qanday xayrlashishini yozing"
                >
                  <TextArea rows={2} placeholder="Misol: Doim 'Ishtahaingiz ochiq bo‘lsin!' deb xayrlash." />
                </Form.Item>

                <Collapse
                  ghost
                  items={[{
                    key: 'advanced',
                    label: <Text type="secondary">Kengaytirilgan: to‘liq system promptni o‘zingiz yozish</Text>,
                    children: (
                      <>
                        <Alert
                          type="warning" showIcon style={{ marginBottom: 12, borderRadius: 10 }}
                          message="Diqqat"
                          description="Bu maydon to‘ldirilsa, tizimdagi standart suhbat qoidalari o‘rniga shu matn ishlatiladi. Menyu va restoran ma’lumoti oxirida baribir qo‘shiladi. Oddiy holatda bo‘sh qoldiring."
                        />
                        <Form.Item name="system_prompt_override" style={{ marginBottom: 0 }}>
                          <TextArea
                            rows={10}
                            placeholder="Bo‘sh qoldiring — standart prompt ishlaydi. Faqat mutaxassislar uchun."
                          />
                        </Form.Item>
                      </>
                    ),
                  }]}
                />
              </Card>

              {/* 5. Sotuv */}
              <Card style={cardStyle} styles={{ body: cardBody }}>
                <span style={sectionLabel}><ThunderboltOutlined /> 5. Sotuv uslubi</span>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <Text strong style={{ display: 'block' }}>Qo‘shimcha taklif (upsell)</Text>
                    <Text type="secondary" style={{ fontSize: 13 }}>
                      Asosiy taomdan keyin ichimlik/non kabi yumshoq taklif. O‘chirilsa — darhol yetkazishga o‘tadi.
                    </Text>
                  </div>
                  <Form.Item name="upsell_enabled" valuePropName="checked" style={{ marginBottom: 0 }}>
                    <Switch />
                  </Form.Item>
                </div>
              </Card>

              {/* 6. Avto xabarlar */}
              <Card style={cardStyle} styles={{ body: cardBody }}>
                <span style={sectionLabel}><ClockCircleOutlined /> 6. Avtomatik xabarlar</span>
                <Text type="secondary" style={{ display: 'block', marginBottom: 12, fontSize: 13 }}>
                  Bo‘sh qoldirsangiz — standart matn ishlatiladi.
                </Text>
                <Form.Item
                  name="offline_reply"
                  label="Restoran yopiq paytda (ish vaqtidan tashqari)"
                  extra="Faqat «Faqat ish vaqtida» yoqilganda ishlaydi"
                >
                  <TextArea rows={2} placeholder="Kechirasiz, hozir yopiqmiz. Ertalab 09:00 dan ochilamiz…" />
                </Form.Item>
                <Form.Item
                  name="time_limit_reply"
                  label="Suhbat vaqti tugaganda"
                  style={{ marginBottom: 0 }}
                >
                  <TextArea rows={2} placeholder="Kechirasiz, suhbat vaqti tugadi. Qayta qo‘ng‘iroq qiling…" />
                </Form.Item>
              </Card>

              {/* 7. SMS */}
              <Card style={cardStyle} styles={{ body: cardBody }}>
                <span style={sectionLabel}><MessageOutlined /> 7. Yetkazish SMS (xarita pin)</span>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
                  <div>
                    <Text strong style={{ display: 'block' }}>Buyurtmadan keyin SMS yuborish</Text>
                    <Text type="secondary" style={{ fontSize: 13 }}>
                      Mijoz xaritada aniq joyni belgilaydi (Yandex kuryer uchun)
                    </Text>
                  </div>
                  <Form.Item name="sms_location_enabled" valuePropName="checked" style={{ marginBottom: 0 }}>
                    <Switch />
                  </Form.Item>
                </div>
                <Form.Item
                  name="sms_location_template"
                  label="SMS matni (ixtiyoriy)"
                  extra="O‘zgaruvchilar: {order_id} va {link}. Bo‘sh = standart matn."
                  style={{ marginBottom: 0 }}
                >
                  <TextArea
                    rows={2}
                    placeholder="Buyurtmangiz #{order_id} qabul qilindi. Aniq joy: {link}"
                  />
                </Form.Item>
              </Card>

              {/* 8. Limitlar */}
              <Card style={{ ...cardStyle, marginBottom: 24 }} styles={{ body: cardBody }}>
                <span style={sectionLabel}><PhoneOutlined /> 8. Limitlar va operator</span>
                <Row gutter={16}>
                  <Col xs={24}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
                      <div>
                        <Text strong style={{ display: 'block' }}>Faqat ish vaqtida javob berish</Text>
                        <Text type="secondary" style={{ fontSize: 13 }}>
                          Restoran sozlamasidagi ish vaqti ishlatiladi
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
                      extra="Shu vaqtdan oshsa AI suhbatni yakunlaydi"
                    >
                      <InputNumber style={{ width: '100%' }} min={1} max={60} step={1} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item
                      name="ai_agent_fallback_phone"
                      label="Jonli operator telefoni"
                      extra="AI tushunmasa mijozga shu raqamni aytadi"
                    >
                      <Input prefix={<PhoneOutlined />} placeholder="+998901234567" />
                    </Form.Item>
                  </Col>
                </Row>
              </Card>

              <Alert
                type="info" showIcon style={{ marginBottom: 24, borderRadius: 10 }}
                message="LLM / API kalit"
                description="Model va OpenAI kalit platforma (super-admin) tomonidan boshqariladi — bu yerda sozlash shart emas."
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
              Sinab ko‘rish
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

      <Divider />
      <Text type="secondary" style={{ fontSize: 12 }}>
        Tip: o‘zgarishlardan keyin «Sinab ko‘rish» orqali yangi promptni tekshiring. Loglar: Sozlamalar → AI loglar.
      </Text>

      <Modal
        title={<span><ExperimentOutlined /> AI Operatorni sinab ko‘rish</span>}
        open={testOpen}
        onCancel={closeTest}
        width={640}
        footer={null}
      >
        <Alert
          type="info" showIcon style={{ marginBottom: 12 }}
          message="Matnli test"
          description="Saqlangan sozlamalar bilan suhbat. Test buyurtma yaratilishi mumkin — keyin bekor qiling."
        />
        <div style={{
          maxHeight: 360, overflowY: 'auto', padding: 12,
          background: '#fafafa', borderRadius: 8, marginBottom: 12,
          border: '1px solid #f0f0f0',
        }}>
          {testMessages.length === 0 ? (
            <Text type="secondary">Pastdagi maydonga yozing…</Text>
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
                  <Tag color="orange" style={{ marginTop: 6 }}>Catering</Tag>
                )}
                {(m.actions || []).some(a => a.type === 'end_call') && (
                  <Tag style={{ marginTop: 6 }}>Yakunlandi</Tag>
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
