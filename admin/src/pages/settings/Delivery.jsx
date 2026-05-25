import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Form, Input, Button, Typography, Row, Col,
  message, Spin, Switch, Alert, Radio
} from 'antd'
import {
  ArrowLeftOutlined, SaveOutlined, CarOutlined,
  UserOutlined, ApiOutlined,
} from '@ant-design/icons'
import { getSettings, updateSettings } from '../../api'
import { useAuthStore } from '../../store/auth'
import { useBranchStore } from '../../store/branch'

const { Title, Text } = Typography

const cardStyle = { marginBottom: 12, borderRadius: 14, border: '1px solid #ececec', boxShadow: 'none' }
const cardBody = { padding: 24 }
const sectionLabel = { fontSize: 12, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: 18, display: 'block' }

export default function DeliverySettings() {
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const { currentRestaurantId: restaurantId } = useAuthStore()
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
        if (!d.delivery_provider) d.delivery_provider = 'own'
        if (d.yandex_test_mode === undefined) d.yandex_test_mode = true
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
          message="Yetkazish sozlamalari faqat asosiy restoran darajasida"
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
          Yetkazib berish
        </Title>
        <Text type="secondary" style={{ fontSize: 14 }}>
          Yetkazib berish provayderini va sozlamalarini tanlang
        </Text>
      </div>

      <Form form={form} layout="vertical" requiredMark={false}>
        {/* Provider Selection */}
        <Card style={cardStyle} styles={{ body: cardBody }}>
          <span style={sectionLabel}>Yetkazish turi</span>

          <Form.Item name="delivery_provider" style={{ marginBottom: 0 }}>
            <Radio.Group style={{ width: '100%' }}>
              <Row gutter={16}>
                <Col xs={24} md={12}>
                  <Radio.Button
                    value="own"
                    style={{
                      width: '100%',
                      height: 'auto',
                      padding: 16,
                      borderRadius: 12,
                      textAlign: 'left',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <div style={{
                        width: 44, height: 44, borderRadius: 10,
                        background: '#1890ff15', display: 'flex',
                        alignItems: 'center', justifyContent: 'center'
                      }}>
                        <UserOutlined style={{ fontSize: 20, color: '#1890ff' }} />
                      </div>
                      <div>
                        <Text strong style={{ display: 'block' }}>O'z kuryerlarim</Text>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          Narx kuryer bilan kelishiladi
                        </Text>
                      </div>
                    </div>
                  </Radio.Button>
                </Col>
                <Col xs={24} md={12}>
                  <Radio.Button
                    value="yandex"
                    style={{
                      width: '100%',
                      height: 'auto',
                      padding: 16,
                      borderRadius: 12,
                      textAlign: 'left',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <div style={{
                        width: 44, height: 44, borderRadius: 10,
                        background: '#faad1415', display: 'flex',
                        alignItems: 'center', justifyContent: 'center'
                      }}>
                        <ApiOutlined style={{ fontSize: 20, color: '#faad14' }} />
                      </div>
                      <div>
                        <Text strong style={{ display: 'block' }}>Yandex Delivery</Text>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          Avtomatik narx hisoblash
                        </Text>
                      </div>
                    </div>
                  </Radio.Button>
                </Col>
              </Row>
            </Radio.Group>
          </Form.Item>
        </Card>

        {/* Yandex Settings */}
        <Form.Item noStyle shouldUpdate={(p, c) => p.delivery_provider !== c.delivery_provider}>
          {({ getFieldValue }) => getFieldValue('delivery_provider') === 'yandex' && (
            <Card style={cardStyle} styles={{ body: cardBody }}>
              <span style={sectionLabel}>Yandex Delivery sozlamalari</span>
              <Text type="secondary" style={{ display: 'block', marginBottom: 16, marginTop: -8, fontSize: 13 }}>
                dostavka.yandex.ru → Profil → Integratsiya dan OAuth token oling
              </Text>

              <Alert
                type="info"
                message="Token olish tartibi"
                description={
                  <ol style={{ margin: 0, paddingLeft: 18, lineHeight: 1.8 }}>
                    <li>Yandex Delivery kabinetga kiring (korxona ro'yxatdan o'tgan bo'lishi shart)</li>
                    <li>Profil → Integratsiya → API tokenlar</li>
                    <li>"Создать токен" → nom kiriting → tokenni saqlang</li>
                    <li>Yandex'da test/live alohida tokenlar mavjud emas — bitta token</li>
                  </ol>
                }
                style={{ marginBottom: 16, borderRadius: 8 }}
              />

              <Form.Item
                name="yandex_api_token"
                label="OAuth Token"
                extra="y0_Ag... formatda. Bo'sh qoldirilsa lokal mock rejim (test uchun)"
              >
                <Input.Password
                  autoComplete="off"
                  placeholder="y0_Ag..."
                  size="large"
                />
              </Form.Item>

              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <Form.Item name="yandex_test_mode" valuePropName="checked" style={{ marginBottom: 0 }}>
                  <Switch />
                </Form.Item>
                <div>
                  <Text strong>Lokal mock rejim</Text>
                  <br />
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    Yoqilganda Yandex'ga so'rov yuborilmaydi — claim avtomatik soxta yaratiladi.
                    Yandex'da rasmiy sandbox mavjud emas, faqat token bilan haqiqiy API.
                  </Text>
                </div>
              </div>
            </Card>
          )}
        </Form.Item>

        {/* Info Alert */}
        <Alert
          type="info"
          showIcon
          icon={<CarOutlined />}
          message="Kuryerlar boshqaruvi"
          description={
            <>
              O'z kuryerlaringizni qo'shish va boshqarish uchun{' '}
              <a onClick={() => navigate('/couriers')}>Kuryerlar</a> sahifasiga o'ting.
            </>
          }
          style={{ marginBottom: 24, borderRadius: 8 }}
        />

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
