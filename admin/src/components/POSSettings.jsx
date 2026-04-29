import { useEffect, useState } from 'react'
import {
  Card, Form, Input, Select, Button, Alert, Space, Tag, Spin,
  Typography, Row, Col, message, Divider,
} from 'antd'
import {
  PrinterOutlined, ApiOutlined, WifiOutlined,
  TabletOutlined, SearchOutlined, ExperimentOutlined,
} from '@ant-design/icons'
import { getPOSConfig, updatePOSConfig, testPOSPrint } from '../api'

const { Text, Paragraph } = Typography

const POS_OPTIONS = [
  {
    value: 'NONE',
    label: '— POS yo\'q (chek bosilmaydi)',
    description: 'Buyurtma tasdiqlanganda hech narsa yuborilmaydi.',
  },
  {
    value: 'NEONALISA',
    label: '🟢 NeonAlisa Cloud (fiskallashtirish)',
    description: 'NeonAlisa hisobingizdagi API kalit orqali fiskal chek yaratiladi.',
  },
  {
    value: 'GENERIC_ANDROID',
    label: '📱 Universal Android terminal',
    description: 'Restoraningizdagi Android tablet/POS WebSocket orqali ulanadi va buyurtmani real-time oladi.',
  },
  {
    value: 'BLUETOOTH_PRINTER',
    label: '🖨 Bluetooth chek printeri',
    description: 'ESC/POS bytes ham generatsiya qilinib, agent ilova orqali Bluetooth printerga yuboriladi.',
  },
]

export default function POSSettings({ restaurantId }) {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [posType, setPosType] = useState('NONE')
  const [connected, setConnected] = useState(0)
  const [lastResult, setLastResult] = useState(null)
  const restParams = restaurantId ? { restaurant_id: restaurantId } : {}

  const load = async () => {
    if (!restaurantId) { setLoading(false); return }
    setLoading(true)
    try {
      const r = await getPOSConfig(restParams)
      const cfg = r.data?.pos_config || {}
      setPosType(r.data?.pos_system_type || 'NONE')
      setConnected(r.data?.connected_terminals || 0)
      form.setFieldsValue({
        pos_system_type: r.data?.pos_system_type || 'NONE',
        api_key: cfg.api_key || '',
        merchant_id: cfg.merchant_id || '',
        base_url: cfg.base_url || '',
        terminal_ip: cfg.terminal_ip || '',
        printer_mac: cfg.printer_mac || '',
        printer_name: cfg.printer_name || '',
      })
    } catch (e) {
      message.error("POS sozlamalarini yuklashda xato")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [restaurantId])

  const onSave = async () => {
    setSaving(true)
    try {
      const v = await form.validateFields()
      // Faqat tegishli kalit'larni yuboramiz
      const cfg = {}
      if (v.pos_system_type === 'NEONALISA') {
        cfg.api_key = v.api_key
        cfg.merchant_id = v.merchant_id
        if (v.base_url) cfg.base_url = v.base_url
      } else if (v.pos_system_type === 'GENERIC_ANDROID') {
        if (v.terminal_ip) cfg.terminal_ip = v.terminal_ip
      } else if (v.pos_system_type === 'BLUETOOTH_PRINTER') {
        cfg.printer_mac = v.printer_mac
        cfg.printer_name = v.printer_name
      }
      await updatePOSConfig({ pos_system_type: v.pos_system_type, pos_config: cfg }, restParams)
      message.success('POS sozlamalari saqlandi')
      await load()
    } catch (e) {
      if (!e?.errorFields) message.error(e?.response?.data?.detail || 'Saqlashda xato')
    } finally {
      setSaving(false)
    }
  }

  const onTestPrint = async () => {
    setTesting(true)
    setLastResult(null)
    try {
      const r = await testPOSPrint(restParams)
      setLastResult(r.data)
      if (r.data?.ok) message.success("Test chek yuborildi ✓")
      else message.warning('Test bajarildi, lekin natija muvaffaqiyatsiz — pastdagi natijani ko\'ring')
    } catch (e) {
      setLastResult({ ok: false, error: e?.response?.data?.detail || e.message })
      message.error('Test print xato')
    } finally {
      setTesting(false)
    }
  }

  if (!restaurantId) {
    return <Alert type="info" message="POS sozlamalari faqat asosiy restoran darajasida." />
  }
  if (loading) return <Spin size="large" style={{ display: 'block', margin: 60 }} />

  const currentOpt = POS_OPTIONS.find((o) => o.value === posType)

  return (
    <Form form={form} layout="vertical" requiredMark="optional" onValuesChange={(c) => {
      if (c.pos_system_type) setPosType(c.pos_system_type)
    }}>
      <Card title={<><PrinterOutlined /> Terminal va Printer</>} size="small" style={{ marginBottom: 16 }}>
        <Paragraph type="secondary">
          Buyurtma <Text code>confirmed</Text> holatiga o'tganda chek avtomatik tegishli
          drayverga yuboriladi. Tashqi POS yiqilsa ham buyurtma oqimi davom etadi
          (xato logga yoziladi va Telegram alert ketadi).
        </Paragraph>

        <Form.Item
          name="pos_system_type"
          label="Qurilma turi"
          rules={[{ required: true }]}
        >
          <Select options={POS_OPTIONS.map((o) => ({ value: o.value, label: o.label }))} />
        </Form.Item>

        {currentOpt?.description && (
          <Alert type="info" showIcon style={{ marginBottom: 16 }} message={currentOpt.description} />
        )}

        {/* Hybrid Setup Wizard — qurilma turiga qarab maydonlar */}
        {posType === 'NEONALISA' && (
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item name="api_key" label="API Key"
                rules={[{ required: true, message: 'API kalit kiriting' }]}>
                <Input.Password prefix={<ApiOutlined />} placeholder="neon_..." autoComplete="off" />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="merchant_id" label="Merchant ID"
                rules={[{ required: true, message: 'Merchant ID kiriting' }]}>
                <Input placeholder="MID-12345" />
              </Form.Item>
            </Col>
            <Col xs={24}>
              <Form.Item name="base_url" label="Base URL (ixtiyoriy)"
                extra="Bo'sh qoldirilsa default https://api.neonalisa.uz/v1 ishlatiladi">
                <Input placeholder="https://api.neonalisa.uz/v1" />
              </Form.Item>
            </Col>
          </Row>
        )}

        {posType === 'GENERIC_ANDROID' && (
          <>
            <Alert
              type="warning" showIcon style={{ marginBottom: 16 }}
              message="Android terminal qanday ulanadi"
              description={
                <div>
                  Restorandagi tablet WebSocket orqali shu manzilga ulanadi:<br/>
                  <Text code>{`ws://${window.location.host.replace('3000','8000')}/pos/bridge/${restaurantId}?token=<RESTAURANT_TOKEN>`}</Text><br/>
                  <Text type="secondary">Ulangan terminallar: <Tag color={connected > 0 ? 'green' : 'default'}>{connected}</Tag></Text>
                </div>
              }
            />
            <Form.Item name="terminal_ip" label="Terminal IP (ixtiyoriy, log uchun)">
              <Input prefix={<TabletOutlined />} placeholder="192.168.1.10" />
            </Form.Item>
          </>
        )}

        {posType === 'BLUETOOTH_PRINTER' && (
          <>
            <Alert
              type="info" showIcon style={{ marginBottom: 16 }}
              message="Bluetooth printer qanday ishlaydi"
              description="Server bytes generatsiya qiladi va WebSocket orqali agent ilovaga yuboradi.
                          Agent ilova bayblar oqimini Bluetooth orqali printerga uzatadi."
            />
            <Row gutter={16}>
              <Col xs={24} md={12}>
                <Form.Item name="printer_mac" label="Printer MAC manzili"
                  rules={[{ required: true, message: 'MAC manzil kiriting' }]}
                  extra="Agent ilovadan 'Qurilmani qidirish' tugmasi orqali avtomatik to'ldiring">
                  <Input prefix={<WifiOutlined />} placeholder="00:11:22:33:44:55" />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item name="printer_name" label="Printer nomi (agent uchun)">
                  <Input placeholder="Xprinter XP-58 / RPP02N" />
                </Form.Item>
              </Col>
            </Row>
            <Button block icon={<SearchOutlined />} disabled
              title="Agent ilovada ochiladi — bu joyda placeholder">
              Bluetooth qurilmalarini qidirish (agent ilovadan)
            </Button>
          </>
        )}

        <Divider />

        <Space>
          <Button type="primary" loading={saving} onClick={onSave}
            style={{ background: '#fa8c16', borderColor: '#fa8c16' }}>
            Sozlamalarni saqlash
          </Button>
          <Button icon={<ExperimentOutlined />} loading={testing} onClick={onTestPrint}
            disabled={posType === 'NONE'}>
            Test Print ("Salom Dunyo")
          </Button>
        </Space>

        {lastResult && (
          <Alert
            style={{ marginTop: 16 }}
            type={lastResult.ok ? 'success' : 'error'}
            showIcon
            message={lastResult.ok ? 'Test muvaffaqiyatli' : 'Test muvaffaqiyatsiz'}
            description={
              <pre style={{ margin: 0, fontSize: 12, whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(lastResult.result || lastResult, null, 2)}
              </pre>
            }
          />
        )}
      </Card>
    </Form>
  )
}
