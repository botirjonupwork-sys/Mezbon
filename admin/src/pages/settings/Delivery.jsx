import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Form, Input, Button, Typography, Row, Col,
  message, Spin, Switch, Alert, Radio, InputNumber, Tag, Space
} from 'antd'
import {
  ArrowLeftOutlined, SaveOutlined, CarOutlined,
  UserOutlined, ApiOutlined, ReloadOutlined, CheckCircleOutlined,
} from '@ant-design/icons'
import { checkYandexBalanceNow, testYandexToken, getSettings, updateSettings } from '../../api'
import { useAuthStore } from '../../store/auth'
import { useBranchStore } from '../../store/branch'
import { fmtTashkent } from '../../utils/datetime'

const { Title, Text } = Typography

const cardStyle = { marginBottom: 12, borderRadius: 14, border: '1px solid #ececec', boxShadow: 'none' }
const cardBody = { padding: 24 }
const sectionLabel = { fontSize: 12, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: 18, display: 'block' }

export default function DeliverySettings() {
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [checkingBalance, setCheckingBalance] = useState(false)
  const [testingToken, setTestingToken] = useState(false)
  const [balanceInfo, setBalanceInfo] = useState(null)

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
        if (d.yandex_balance_currency === undefined) d.yandex_balance_currency = 'UZS'
        if (d.yandex_balance_low_threshold === undefined) d.yandex_balance_low_threshold = 300000
        if (d.yandex_balance_critical_threshold === undefined) d.yandex_balance_critical_threshold = 100000
        form.setFieldsValue(d)
        setBalanceInfo({
          status: d.yandex_balance_status,
          amount: d.yandex_balance_amount,
          currency: d.yandex_balance_currency || 'UZS',
          checked_at: d.yandex_balance_checked_at,
          source: d.yandex_balance_source,
        })
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

  const handleCheckBalance = async () => {
    setCheckingBalance(true)
    try {
      const res = await checkYandexBalanceNow(restParams)
      setBalanceInfo(res.data)
      form.setFieldsValue({
        yandex_balance_amount: res.data.amount,
        yandex_balance_currency: res.data.currency || 'UZS',
      })
      message.success('Balans tekshirildi')
    } catch {
      message.error('Balansni tekshirishda xato')
    } finally {
      setCheckingBalance(false)
    }
  }

  const handleTestToken = async () => {
    const token = form.getFieldValue('yandex_api_token')
    if (!token) {
      message.warning('Iltimos, avval OAuth tokenni kiriting')
      return
    }
    setTestingToken(true)
    try {
      const res = await testYandexToken({ token }, restParams)
      if (res.data?.ok) {
        message.success(res.data.message || "Token to'g'ri! Yandex Delivery faol.")
      } else {
        message.error(res.data?.message || 'Token tekshirishda xatolik yuz berdi')
      }
    } catch (e) {
      const msg = e.response?.data?.detail || e.message || 'Xatolik yuz berdi'
      message.error(`Xatolik: ${msg}`)
    } finally {
      setTestingToken(false)
    }
  }

  const statusTag = (status) => {
    const map = {
      ok: ['green', 'Yetarli'],
      low: ['orange', 'Kam'],
      critical: ['red', 'Kritik'],
      unknown: ['default', "Noma'lum"],
      disabled: ['default', "O'chiq"],
    }
    const [color, label] = map[status || 'unknown'] || map.unknown
    return <Tag color={color}>{label}</Tag>
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

              <div style={{ marginBottom: 20 }}>
                <Button
                  icon={<CheckCircleOutlined />}
                  loading={testingToken}
                  onClick={handleTestToken}
                >
                  Tokenni tekshirish (Test Connection)
                </Button>
              </div>

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

              <div style={{ height: 1, background: '#f0f0f0', margin: '20px 0' }} />

              <span style={sectionLabel}>Balans monitoringi</span>
              <Alert
                type="warning"
                showIcon
                message="Yandex Express API'da balans endpointi tasdiqlanmagan"
                description="Hozir balans qiymati manual/mock yuritiladi. Real endpoint berilganda shu monitoring avtomatik source'ga o'tkaziladi."
                style={{ marginBottom: 16, borderRadius: 8 }}
              />

              <Row gutter={16}>
                <Col xs={24} md={12}>
                  <Form.Item name="yandex_balance_monitor_enabled" valuePropName="checked" label="Monitoring">
                    <Switch checkedChildren="Yoqilgan" unCheckedChildren="O'chiq" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item name="yandex_balance_block_on_critical" valuePropName="checked" label="Kritik holatda Yandex claim">
                    <Switch checkedChildren="Bloklash" unCheckedChildren="Faqat alert" />
                  </Form.Item>
                </Col>
              </Row>

              <Row gutter={16}>
                <Col xs={24} md={12}>
                  <Form.Item name="yandex_balance_amount" label="Joriy balans">
                    <InputNumber
                      min={0}
                      step={10000}
                      style={{ width: '100%' }}
                      size="large"
                      addonAfter="UZS"
                      formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ' ')}
                      parser={(v) => v?.replace(/\s/g, '')}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item name="yandex_balance_currency" label="Valyuta">
                    <Input size="large" placeholder="UZS" />
                  </Form.Item>
                </Col>
              </Row>

              <Row gutter={16}>
                <Col xs={24} md={12}>
                  <Form.Item name="yandex_balance_low_threshold" label="Ogohlantirish chegarasi">
                    <InputNumber min={0} step={10000} style={{ width: '100%' }} size="large" addonAfter="UZS" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item name="yandex_balance_critical_threshold" label="Kritik chegara">
                    <InputNumber min={0} step={10000} style={{ width: '100%' }} size="large" addonAfter="UZS" />
                  </Form.Item>
                </Col>
              </Row>

              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', padding: 12, border: '1px solid #f0f0f0', borderRadius: 8 }}>
                <Space direction="vertical" size={2}>
                  <Space>
                    <Text strong>Balans holati:</Text>
                    {statusTag(balanceInfo?.status)}
                  </Space>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {balanceInfo?.checked_at
                      ? `Oxirgi tekshiruv: ${fmtTashkent(balanceInfo.checked_at, 'DD.MM.YYYY HH:mm:ss')}`
                      : 'Hali tekshirilmagan'}
                  </Text>
                </Space>
                <Button icon={<ReloadOutlined />} loading={checkingBalance} onClick={handleCheckBalance}>
                  Balansni tekshirish
                </Button>
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
