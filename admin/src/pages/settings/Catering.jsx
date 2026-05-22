import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Form, Input, InputNumber, Button, Typography, Row, Col,
  message, Spin, Switch, Alert
} from 'antd'
import {
  ArrowLeftOutlined, SaveOutlined, GiftOutlined,
  DollarOutlined, BellOutlined, SendOutlined,
} from '@ant-design/icons'
import { getSettings, updateSettings } from '../../api'
import { useAuthStore } from '../../store/auth'
import { useBranchStore } from '../../store/branch'
import { moneyFormatter, moneyParser } from '../../utils/format'

const { Title, Text } = Typography

const cardStyle = { marginBottom: 12, borderRadius: 14, border: '1px solid #ececec', boxShadow: 'none' }
const cardBody = { padding: 24 }
const sectionLabel = { fontSize: 12, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: 18, display: 'block' }

export default function CateringSettings() {
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)

  const { currentRestaurantId: restaurantId, token } = useAuthStore()
  const selectedBranchId = useBranchStore((s) => s.selectedBranchId)
  const restParams = restaurantId ? { restaurant_id: restaurantId } : {}

  useEffect(() => {
    if (!restaurantId) {
      setLoading(false)
      return
    }

    setLoading(true)
    getSettings(restParams)
      .then((res) => {
        const d = res.data || {}
        if (d.currency_auto === undefined) d.currency_auto = true
        form.setFieldsValue(d)
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

  const testNotifier = async () => {
    setTesting(true)
    try {
      const r = await fetch('/api/admin/catering-notifier/test', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      const d = await r.json()
      if (r.ok) {
        message.success(`Yuborildi: ${d.orders_count} ta buyurtma`)
      } else {
        message.error(d.detail || 'Xato')
      }
    } catch (e) {
      message.error("Yuborib bo'lmadi")
    } finally {
      setTesting(false)
    }
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
          message="Catering sozlamalari faqat asosiy restoran darajasida"
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
          Catering sozlamalari
        </Title>
        <Text type="secondary" style={{ fontSize: 14 }}>
          Miqdor, narx va bildirishnoma sozlamalari
        </Text>
      </div>

      <Form form={form} layout="vertical" requiredMark="optional">
        {/* Currency Settings */}
        <Card style={cardStyle} styles={{ body: cardBody }}>
          <span style={sectionLabel}>Valyuta kursi (USD → UZS)</span>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
            <Form.Item name="currency_auto" valuePropName="checked" style={{ marginBottom: 0 }}>
              <Switch />
            </Form.Item>
            <div>
              <Text strong>Avtomatik kurs (CBU)</Text>
              <br />
              <Text type="secondary" style={{ fontSize: 12 }}>
                Markaziy Bank kursi har soatda yangilanadi
              </Text>
            </div>
          </div>

          <Form.Item noStyle shouldUpdate={(p, c) => p.currency_auto !== c.currency_auto}>
            {({ getFieldValue }) => !getFieldValue('currency_auto') && (
              <Form.Item
                name="currency_rate_manual"
                label="Qo'lda kurs (1 USD = ? so'm)"
                rules={[{ required: true, message: 'Kurs kiriting' }]}
                style={{ marginBottom: 0 }}
              >
                <InputNumber
                  min={0}
                  style={{ width: '100%', maxWidth: 300 }}
                  step={100}
                  size="large"
                  formatter={moneyFormatter}
                  parser={moneyParser}
                  addonAfter="so'm"
                  placeholder="12 500"
                />
              </Form.Item>
            )}
          </Form.Item>
        </Card>

        {/* Quantity Settings */}
        <Card style={cardStyle} styles={{ body: cardBody }}>
          <span style={sectionLabel}>Miqdor sozlamalari</span>

          <Row gutter={[16, 16]}>
            <Col xs={12} md={6}>
              <Form.Item name="catering_somsa_min" label="Somsa min" extra="dona">
                <InputNumber min={1} style={{ width: '100%' }} formatter={moneyFormatter} parser={moneyParser} placeholder="100" />
              </Form.Item>
            </Col>
            <Col xs={12} md={6}>
              <Form.Item name="catering_somsa_step" label="Somsa qadam" extra="dona">
                <InputNumber min={1} style={{ width: '100%' }} placeholder="1" />
              </Form.Item>
            </Col>
            <Col xs={12} md={6}>
              <Form.Item name="catering_nan_min" label="Non min" extra="dona">
                <InputNumber min={1} style={{ width: '100%' }} placeholder="40" />
              </Form.Item>
            </Col>
            <Col xs={12} md={6}>
              <Form.Item name="catering_nan_step" label="Non qadam" extra="dona">
                <InputNumber min={1} style={{ width: '100%' }} placeholder="40" />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item
            name="catering_delivery_per_km_uzs"
            label="Yetkazish narxi (1 km)"
            extra="Yandex ulanmaganda ishlatiladi"
            style={{ maxWidth: 300, marginBottom: 0 }}
          >
            <InputNumber
              min={0}
              style={{ width: '100%' }}
              step={1000}
              formatter={moneyFormatter}
              parser={moneyParser}
              addonAfter="so'm"
              placeholder="5 000"
            />
          </Form.Item>
        </Card>

        {/* Service Fee */}
        <Card style={cardStyle} styles={{ body: cardBody }}>
          <span style={sectionLabel}>Xizmat haqi</span>

          <Form.Item
            name="catering_service_fee"
            label="Borib xizmat ko'rsatish haqi"
            extra="Mijoz onsite catering tanlasa, asosiy chekka qo'shiladi"
            style={{ maxWidth: 300, marginBottom: 0 }}
          >
            <InputNumber
              min={0}
              style={{ width: '100%' }}
              step={10000}
              formatter={moneyFormatter}
              parser={moneyParser}
              addonAfter="so'm"
              placeholder="50 000"
            />
          </Form.Item>
        </Card>

        {/* Manual Payment Card */}
        <Card style={cardStyle} styles={{ body: cardBody }}>
          <span style={sectionLabel}>Manual to'lov kartasi</span>
          <Text type="secondary" style={{ display: 'block', marginBottom: 16, marginTop: -8, fontSize: 13 }}>
            Click/Payme ulanmaguncha mijozga ko'rsatiladigan karta
          </Text>

          <Row gutter={16}>
            <Col xs={24} md={14}>
              <Form.Item name="catering_payment_card" label="Karta raqami">
                <Input placeholder="8600 1234 5678 9012" maxLength={19} size="large" />
              </Form.Item>
            </Col>
            <Col xs={24} md={10}>
              <Form.Item name="catering_payment_owner" label="Karta egasi">
                <Input placeholder="TURSUNBOYEV B." size="large" />
              </Form.Item>
            </Col>
          </Row>
        </Card>

        {/* Notifier Settings */}
        <Card style={{ ...cardStyle, marginBottom: 24 }} styles={{ body: cardBody }}>
          <span style={sectionLabel}>Bildirishnoma kanali</span>
          <Text type="secondary" style={{ display: 'block', marginBottom: 16, marginTop: -8, fontSize: 13 }}>
            Har kuni 20:00 da ertangi catering ro'yxati yuboriladi
          </Text>

          <Form.Item
            name="catering_notifier_chat_id"
            label="Telegram Chat ID"
            extra="Kanal yoki guruh. Misol: -1001234567890 yoki @my_channel"
          >
            <Input placeholder="@my_channel yoki -1001234567890" size="large" />
          </Form.Item>

          <Button
            onClick={testNotifier}
            loading={testing}
            icon={<SendOutlined />}
          >
            Hozir sinab ko'rish
          </Button>
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
