import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Form, Input, Button, Typography, Row, Col,
  message, Spin, Switch, Alert, Select,
} from 'antd'
import {
  ArrowLeftOutlined, SaveOutlined, PhoneOutlined,
} from '@ant-design/icons'
import { getSettings, updateSettings, getMyPlan } from '../../api'
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
              {/* Provider tanlash */}
              <Card style={cardStyle} styles={{ body: cardBody }}>
                <span style={sectionLabel}>Provider</span>
                <Row gutter={16}>
                  <Col xs={24} md={12}>
                    <Form.Item name="ai_agent_provider" label="Voice provayder" extra="Vapi tavsiya etiladi (eng oson integratsiya)">
                      <Select options={[
                        { value: 'vapi', label: 'Vapi (tavsiya)' },
                        { value: 'retell', label: 'Retell AI' },
                        { value: 'openai', label: 'OpenAI Realtime' },
                      ]} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item name="ai_agent_model" label="LLM model">
                      <Select options={[
                        { value: 'gpt-4o-mini', label: 'gpt-4o-mini (tez, arzon)' },
                        { value: 'gpt-4o', label: 'gpt-4o (aniqroq)' },
                      ]} />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item name="ai_agent_api_key" label="API kalit" extra="Bo'sh qoldirilsa platforma kaliti ishlatiladi (qo'shimcha to'lov bo'lishi mumkin)">
                  <Input.Password autoComplete="off" placeholder="sk-... yoki vapi-..." />
                </Form.Item>
              </Card>

              {/* Ovoz */}
              <Card style={cardStyle} styles={{ body: cardBody }}>
                <span style={sectionLabel}>Ovoz</span>
                <Form.Item name="ai_agent_voice" label="Operator ovozi">
                  <Select style={{ maxWidth: 300 }} options={[
                    { value: 'female', label: '👩 Ayol ovozi' },
                    { value: 'male', label: '👨 Erkak ovozi' },
                  ]} />
                </Form.Item>
              </Card>

              {/* System prompt */}
              <Card style={{ ...cardStyle, marginBottom: 24 }} styles={{ body: cardBody }}>
                <span style={sectionLabel}>Maxsus ko'rsatma</span>
                <Text type="secondary" style={{ display: 'block', marginBottom: 12, fontSize: 13 }}>
                  Restoraningizga oid qo'shimcha qoidalar (masalan: "Pishloqsiz somsa ham bor" yoki "Penshenerlar uchun 10% chegirma").
                </Text>
                <Form.Item name="ai_agent_prompt" style={{ marginBottom: 0 }}>
                  <Input.TextArea
                    rows={5}
                    placeholder="Misol: Bizning restoran 5 turli somsa pishiradi. Diyetik (mantili 200 kkal) ham bor. Mijozdan har doim manzilni aniq so'rang."
                  />
                </Form.Item>
              </Card>
            </>
          )}
        </Form.Item>

        <Button
          type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSave}
          size="large" block
          style={{ height: 46, fontWeight: 500, borderRadius: 10, background: '#111827', borderColor: '#111827' }}
        >
          Saqlash
        </Button>
      </Form>
    </div>
  )
}
