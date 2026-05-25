import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Form, Input, InputNumber, Button, Typography, Row, Col,
  message, Spin, Switch, Alert, Collapse, Tooltip
} from 'antd'
import {
  ArrowLeftOutlined, SaveOutlined, CreditCardOutlined,
  DollarOutlined, CopyOutlined, CheckOutlined,
} from '@ant-design/icons'
import { getSettings, updateSettings } from '../../api'
import { useAuthStore } from '../../store/auth'
import { useBranchStore } from '../../store/branch'
import { moneyFormatter, moneyParser } from '../../utils/format'

const { Title, Text } = Typography

const cardStyle = { marginBottom: 12, borderRadius: 14, border: '1px solid #ececec', boxShadow: 'none' }
const cardBody = { padding: 24 }
const sectionLabel = { fontSize: 12, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: 18, display: 'block' }

export default function PaymentsSettings() {
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [copiedField, setCopiedField] = useState(null)

  const { currentRestaurantId: restaurantId } = useAuthStore()
  const selectedBranchId = useBranchStore((s) => s.selectedBranchId)
  const restParams = restaurantId ? { restaurant_id: restaurantId } : {}

  // Generate webhook URLs
  const apiBase = (() => {
    const env = import.meta.env.VITE_API_URL
    if (env) return env.startsWith('http') ? env : window.location.origin + env
    return window.location.origin + '/api'
  })()
  const clickWebhookUrl = `${apiBase.replace(/\/$/, '')}/payments/click/webhook`
  const paymeWebhookUrl = `${apiBase.replace(/\/$/, '')}/payments/payme/webhook`
  const uzumWebhookUrl = `${apiBase.replace(/\/$/, '')}/payments/uzum/webhook`

  useEffect(() => {
    if (!restaurantId) {
      setLoading(false)
      return
    }

    setLoading(true)
    getSettings(restParams)
      .then((res) => {
        form.setFieldsValue(res.data || {})
      })
      .catch(() => message.error("Ma'lumotlarni yuklashda xato"))
      .finally(() => setLoading(false))
  }, [restaurantId])

  const handleSave = async () => {
    setSaving(true)
    try {
      const values = await form.validateFields()
      await updateSettings(values, restParams)
      message.success('Sozlamalar saqlandi')
    } catch (err) {
      if (!err?.errorFields) message.error('Saqlashda xato')
    } finally {
      setSaving(false)
    }
  }

  const copyToClipboard = (text, field) => {
    navigator.clipboard.writeText(text)
    setCopiedField(field)
    message.success('Nusxa olindi')
    setTimeout(() => setCopiedField(null), 2000)
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <Spin size="large" />
      </div>
    )
  }

  if (selectedBranchId) {
    return (
      <div style={{ maxWidth: 800, margin: '0 auto' }}>
        <Button
          type="text"
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/settings')}
          style={{ marginBottom: 16, padding: 0 }}
        >
          Sozlamalar
        </Button>
        <Alert
          type="info"
          showIcon
          message="To'lov sozlamalari faqat asosiy restoran darajasida"
          description="Filial rejimidan chiqib, asosiy restorani tanlang"
        />
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
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
          To'lov sozlamalari
        </Title>
        <Text type="secondary" style={{ fontSize: 14 }}>
          Click, Payme va Telegram Pay integratsiyalari
        </Text>
      </div>

      <Form form={form} layout="vertical" requiredMark={false}>
        {/* Test/Live Mode */}
        <Card style={cardStyle} styles={{ body: cardBody }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <span style={{ ...sectionLabel, marginBottom: 4 }}>To'lov rejimi</span>
              <Text type="secondary" style={{ fontSize: 13 }}>
                Test rejimda haqiqiy pul yechilmaydi
              </Text>
            </div>
            <Form.Item name="payment_test_mode" valuePropName="checked" style={{ marginBottom: 0 }}>
              <Switch checkedChildren="TEST" unCheckedChildren="LIVE" style={{ minWidth: 70 }} />
            </Form.Item>
          </div>
        </Card>

        {/* VAT Settings */}
        <Card style={cardStyle} styles={{ body: cardBody }}>
          <span style={sectionLabel}>QQS (Soliq)</span>

          <Row gutter={16} align="middle">
            <Col xs={24} sm={12}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <Form.Item name="is_vat_payer" valuePropName="checked" style={{ marginBottom: 0 }}>
                  <Switch />
                </Form.Item>
                <Text>QQS to'lovchi</Text>
              </div>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item noStyle shouldUpdate={(p, c) => p.is_vat_payer !== c.is_vat_payer}>
                {({ getFieldValue }) => getFieldValue('is_vat_payer') && (
                  <Form.Item name="vat_percent" label="QQS foizi" style={{ marginBottom: 0 }}>
                    <InputNumber
                      min={0}
                      max={100}
                      step={0.5}
                      style={{ width: '100%' }}
                      addonAfter="%"
                      placeholder="12"
                    />
                  </Form.Item>
                )}
              </Form.Item>
            </Col>
          </Row>
        </Card>

        {/* Webhook URLs */}
        <Card style={cardStyle} styles={{ body: cardBody }}>
          <span style={sectionLabel}>Webhook URL'lar</span>
          <Text type="secondary" style={{ display: 'block', marginBottom: 16, marginTop: -8, fontSize: 13 }}>
            Bu manzillarni Click/Payme merchant kabinetiga kiriting
          </Text>

          <div style={{ marginBottom: 12 }}>
            <Text strong style={{ display: 'block', marginBottom: 4 }}>Click webhook:</Text>
            <Input.Group compact>
              <Input
                value={clickWebhookUrl}
                readOnly
                style={{ width: 'calc(100% - 40px)', background: '#fafafa' }}
              />
              <Tooltip title={copiedField === 'click' ? 'Nusxa olindi!' : 'Nusxa olish'}>
                <Button
                  icon={copiedField === 'click' ? <CheckOutlined /> : <CopyOutlined />}
                  onClick={() => copyToClipboard(clickWebhookUrl, 'click')}
                />
              </Tooltip>
            </Input.Group>
          </div>

          <div style={{ marginBottom: 12 }}>
            <Text strong style={{ display: 'block', marginBottom: 4 }}>Payme webhook:</Text>
            <Input.Group compact>
              <Input
                value={paymeWebhookUrl}
                readOnly
                style={{ width: 'calc(100% - 40px)', background: '#fafafa' }}
              />
              <Tooltip title={copiedField === 'payme' ? 'Nusxa olindi!' : 'Nusxa olish'}>
                <Button
                  icon={copiedField === 'payme' ? <CheckOutlined /> : <CopyOutlined />}
                  onClick={() => copyToClipboard(paymeWebhookUrl, 'payme')}
                />
              </Tooltip>
            </Input.Group>
          </div>

          <div>
            <Text strong style={{ display: 'block', marginBottom: 4 }}>Uzum webhook:</Text>
            <Input.Group compact>
              <Input
                value={uzumWebhookUrl}
                readOnly
                style={{ width: 'calc(100% - 40px)', background: '#fafafa' }}
              />
              <Tooltip title={copiedField === 'uzum' ? 'Nusxa olindi!' : 'Nusxa olish'}>
                <Button
                  icon={copiedField === 'uzum' ? <CheckOutlined /> : <CopyOutlined />}
                  onClick={() => copyToClipboard(uzumWebhookUrl, 'uzum')}
                />
              </Tooltip>
            </Input.Group>
          </div>
        </Card>

        {/* Click */}
        <Card style={cardStyle} styles={{ body: cardBody }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <div>
              <div style={{ fontSize: 16, fontWeight: 600, color: '#111827' }}>Click</div>
              <Text type="secondary" style={{ fontSize: 12 }}>UzCard / Humo · 0.8%   ·   Visa · 2.5%</Text>
            </div>
            <Form.Item name="click_enabled" valuePropName="checked" style={{ marginBottom: 0 }}>
              <Switch />
            </Form.Item>
          </div>

          <Form.Item noStyle shouldUpdate={(p, c) => p.click_enabled !== c.click_enabled}>
            {({ getFieldValue }) => getFieldValue('click_enabled') && (
              <Row gutter={16}>
                <Col xs={24} md={8}>
                  <Form.Item name="click_merchant_id" label="Merchant ID" rules={[{ required: true, message: "To'ldiring" }]}>
                    <Input placeholder="12345" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={8}>
                  <Form.Item name="click_service_id" label="Service ID" rules={[{ required: true, message: "To'ldiring" }]}>
                    <Input placeholder="54321" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={8}>
                  <Form.Item name="click_secret_key" label="Secret Key" rules={[{ required: true, message: "To'ldiring" }]}>
                    <Input.Password autoComplete="off" />
                  </Form.Item>
                </Col>
              </Row>
            )}
          </Form.Item>
        </Card>

        {/* Payme */}
        <Card style={cardStyle} styles={{ body: cardBody }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <div>
              <div style={{ fontSize: 16, fontWeight: 600, color: '#111827' }}>Payme</div>
              <Text type="secondary" style={{ fontSize: 12 }}>UzCard / Humo · 0.8–1.2%</Text>
            </div>
            <Form.Item name="payme_enabled" valuePropName="checked" style={{ marginBottom: 0 }}>
              <Switch />
            </Form.Item>
          </div>

          <Form.Item noStyle shouldUpdate={(p, c) => p.payme_enabled !== c.payme_enabled}>
            {({ getFieldValue }) => getFieldValue('payme_enabled') && (
              <Row gutter={16}>
                <Col xs={24} md={12}>
                  <Form.Item name="payme_merchant_id" label="Cashbox ID" rules={[{ required: true, message: "To'ldiring" }]}>
                    <Input placeholder="5e7c1e..." />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item name="payme_secret_key" label="Merchant Key" rules={[{ required: true, message: "To'ldiring" }]}>
                    <Input.Password autoComplete="off" />
                  </Form.Item>
                </Col>
              </Row>
            )}
          </Form.Item>
        </Card>

        {/* Uzum */}
        <Card style={cardStyle} styles={{ body: cardBody }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <div>
              <div style={{ fontSize: 16, fontWeight: 600, color: '#111827' }}>Uzum Bank</div>
              <Text type="secondary" style={{ fontSize: 12 }}>Uzum kartalari · 0% · boshqalar · 0.4%</Text>
            </div>
            <Form.Item name="uzum_enabled" valuePropName="checked" style={{ marginBottom: 0 }}>
              <Switch />
            </Form.Item>
          </div>

          <Form.Item noStyle shouldUpdate={(p, c) => p.uzum_enabled !== c.uzum_enabled}>
            {({ getFieldValue }) => getFieldValue('uzum_enabled') && (
              <>
                <Form.Item
                  name="uzum_service_id"
                  label="Service ID"
                  extra="merchants.uzumbank.uz dan olinadi"
                  rules={[{ required: true, message: "To'ldiring" }]}
                >
                  <Input placeholder="123422111" />
                </Form.Item>
                <Row gutter={16}>
                  <Col xs={24} md={12}>
                    <Form.Item name="uzum_webhook_user" label="Webhook Basic Auth — login" rules={[{ required: true, message: "To'ldiring" }]}>
                      <Input autoComplete="off" placeholder="uzum_user" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item name="uzum_webhook_pass" label="Webhook Basic Auth — parol" rules={[{ required: true, message: "To'ldiring" }]}>
                      <Input.Password autoComplete="off" />
                    </Form.Item>
                  </Col>
                </Row>
              </>
            )}
          </Form.Item>
        </Card>

        {/* Prepayment Settings */}
        <Card style={{ ...cardStyle, marginBottom: 24 }} styles={{ body: cardBody }}>
          <span style={sectionLabel}>Oldindan to'lov</span>

          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item
                name="prepayment_required_above"
                label="Oldindan to'lov chegarasi"
                extra="Shu summadan oshsa prepayment majburiy"
              >
                <InputNumber
                  style={{ width: '100%' }}
                  min={0}
                  step={50000}
                  formatter={moneyFormatter}
                  parser={moneyParser}
                  addonAfter="so'm"
                  placeholder="200 000"
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item
                name="enforce_prepayment_for_delivery"
                label="Yetkazish uchun majburiy"
                valuePropName="checked"
                extra="Yetkazib berishlarda har doim prepayment"
              >
                <Switch />
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
