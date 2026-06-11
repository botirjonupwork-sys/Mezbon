import { useEffect, useState } from 'react'
import {
  Card, Form, Input, Switch, Select, Button, Table, Tag, Typography,
  Divider, Space, message, Spin, Alert, Tooltip, TimePicker,
} from 'antd'
import {
  SafetyOutlined, SendOutlined, SaveOutlined, RobotOutlined,
  ReloadOutlined, BellOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  getAlertConfig, updateAlertConfig, testAlert, getAlertHistory,
} from '../api'

const { Title, Text } = Typography

const SEVERITY_TAG = {
  info: <Tag color="blue">info</Tag>,
  warning: <Tag color="orange">warning</Tag>,
  critical: <Tag color="red">critical</Tag>,
}
const STATUS_TAG = {
  sent: <Tag color="green">yuborildi</Tag>,
  failed: <Tag color="red">xato</Tag>,
  skipped: <Tag color="default">o'tkazildi</Tag>,
}

// Mavjud hodisa kategoriyalari (qoidalar uchun)
const CATEGORIES = [
  { value: '*', label: '★ Barchasi' },
  { value: 'payment', label: '💳 To\'lov' },
  { value: 'auth', label: '🔐 Autentifikatsiya' },
  { value: 'security', label: '🛡 Xavfsizlik' },
  { value: 'database', label: '🗄 Ma\'lumotlar bazasi' },
  { value: 'yandex', label: '🚗 Yandex' },
  { value: 'ai_agent', label: '🤖 AI operator' },
]

export default function SecurityAlerts() {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [tokenSet, setTokenSet] = useState(false)
  const [history, setHistory] = useState([])
  const [historyLoading, setHistoryLoading] = useState(false)

  const loadConfig = async () => {
    setLoading(true)
    try {
      const { data } = await getAlertConfig()
      setTokenSet(data.telegram?.bot_token_set)
      form.setFieldsValue({
        tg_enabled: data.telegram?.enabled ?? false,
        bot_token: '',
        chat_ids: (data.telegram?.chat_ids || []).join(', '),
        security_ai_enabled: data.security_ai_enabled ?? true,
        rules: (data.rules || []).map((r) => ({
          event_category: r.event_category, min_severity: r.min_severity, enabled: r.enabled,
        })),
        quiet_start: data.quiet_hours_start ? dayjs(data.quiet_hours_start, 'HH:mm') : null,
        quiet_end: data.quiet_hours_end ? dayjs(data.quiet_hours_end, 'HH:mm') : null,
      })
    } catch {
      message.error('Sozlamalarni yuklab bo\'lmadi')
    } finally {
      setLoading(false)
    }
  }

  const loadHistory = async () => {
    setHistoryLoading(true)
    try {
      const { data } = await getAlertHistory({ limit: 50 })
      setHistory(data)
    } catch { /* jim */ } finally {
      setHistoryLoading(false)
    }
  }

  useEffect(() => { loadConfig(); loadHistory() }, [])

  const onSave = async (v) => {
    setSaving(true)
    try {
      await updateAlertConfig({
        telegram: {
          enabled: v.tg_enabled,
          bot_token: v.bot_token || '',     // bo'sh bo'lsa backend eski tokenni saqlaydi
          chat_ids: (v.chat_ids || '').split(',').map((s) => s.trim()).filter(Boolean),
        },
        rules: (v.rules || []).map((r) => ({
          event_category: r.event_category || '*',
          min_severity: r.min_severity || 'warning',
          enabled: r.enabled !== false,
        })),
        security_ai_enabled: v.security_ai_enabled,
        quiet_hours_start: v.quiet_start ? v.quiet_start.format('HH:mm') : '',
        quiet_hours_end: v.quiet_end ? v.quiet_end.format('HH:mm') : '',
      })
      message.success('Saqlandi')
      loadConfig()
    } catch (e) {
      message.error(e.response?.data?.detail || 'Saqlab bo\'lmadi')
    } finally {
      setSaving(false)
    }
  }

  const onTest = async () => {
    setTesting(true)
    try {
      await testAlert()
      message.success('Test xabari yuborildi — Telegram\'ni tekshiring')
      loadHistory()
    } catch (e) {
      message.error(e.response?.data?.detail || 'Test yuborilmadi')
    } finally {
      setTesting(false)
    }
  }

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '80px auto' }} />

  const historyCols = [
    { title: 'Vaqt', dataIndex: 'created_at', width: 150,
      render: (v) => (v ? dayjs(v).format('DD.MM HH:mm:ss') : '—') },
    { title: 'Daraja', dataIndex: 'severity', width: 100,
      render: (v) => SEVERITY_TAG[v] || v },
    { title: 'Kategoriya', dataIndex: 'category', width: 110 },
    { title: 'Xulosa', dataIndex: 'summary', ellipsis: true,
      render: (v, r) => <span>{r.ai_used && <RobotOutlined style={{ color: '#722ed1', marginRight: 4 }} />}{v}</span> },
    { title: 'Holat', dataIndex: 'status', width: 110,
      render: (v) => STATUS_TAG[v] || v },
  ]

  return (
    <div style={{ maxWidth: 760 }}>
      <Card>
        <Title level={5}><SafetyOutlined /> Xavfsizlik AI bildirishnoma</Title>
        <Text type="secondary" style={{ display: 'block', marginBottom: 20 }}>
          Muammo yoki muhim hodisa yuzaga kelganda Security AI uni tahlil qilib,
          Telegram orqali xabar yuboradi. Hozir faqat Telegram kanali ishlaydi.
        </Text>

        <Form form={form} layout="vertical" onFinish={onSave}>
          <Divider orientation="left"><BellOutlined /> Telegram kanal</Divider>

          <Form.Item name="tg_enabled" label="Kanal yoqilgan" valuePropName="checked">
            <Switch />
          </Form.Item>

          <Form.Item
            name="bot_token"
            label={<span>Bot tokeni {tokenSet
              ? <Tag color="green">O'rnatilgan</Tag>
              : <Tag color="red">Kiritilmagan</Tag>}</span>}
            extra={tokenSet
              ? "Bo'sh qoldirilsa eski token saqlanadi. Yangi token kiritsangizgina almashtiriladi."
              : "@BotFather'dan olingan alert-bot tokenini kiriting."}
          >
            <Input.Password autoComplete="new-password"
              placeholder={tokenSet ? '••••••••••••' : '123456:ABC-DEF...'} />
          </Form.Item>

          <Form.Item
            name="chat_ids"
            label="Chat ID(lar)"
            extra="Bir nechta bo'lsa vergul bilan: 111222333, @kanal_nomi. Bot shu chat/guruhga qo'shilgan bo'lishi shart."
          >
            <Input placeholder="111222333, @mening_kanalim" />
          </Form.Item>

          <Divider orientation="left"><RobotOutlined /> Security AI</Divider>
          <Form.Item name="security_ai_enabled" label="AI tahlil yoqilgan" valuePropName="checked"
            extra="Yoqilsa: har bildirishnoma LLM bilan tahlil qilinib, o'zbekcha xulosa + tavsiya beriladi. O'chirilsa: oddiy qoidaga asoslangan xabar.">
            <Switch />
          </Form.Item>

          <Divider orientation="left">Qoidalar — qaysi hodisa qaysi darajadan</Divider>
          <Form.List name="rules">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...rest }) => (
                  <Space key={key} align="baseline" style={{ display: 'flex', marginBottom: 8 }}>
                    <Form.Item {...rest} name={[name, 'event_category']} style={{ width: 200, marginBottom: 0 }}>
                      <Select options={CATEGORIES} placeholder="Kategoriya" />
                    </Form.Item>
                    <Form.Item {...rest} name={[name, 'min_severity']} style={{ width: 150, marginBottom: 0 }}>
                      <Select options={[
                        { value: 'info', label: 'info+' },
                        { value: 'warning', label: 'warning+' },
                        { value: 'critical', label: 'faqat critical' },
                      ]} />
                    </Form.Item>
                    <Form.Item {...rest} name={[name, 'enabled']} valuePropName="checked"
                      initialValue style={{ marginBottom: 0 }}>
                      <Switch size="small" />
                    </Form.Item>
                    <Button danger type="text" onClick={() => remove(name)}>O'chirish</Button>
                  </Space>
                ))}
                <Button type="dashed" onClick={() => add({ event_category: '*', min_severity: 'warning', enabled: true })} block>
                  + Qoida qo'shish
                </Button>
                <Text type="secondary" style={{ display: 'block', marginTop: 6, fontSize: 12 }}>
                  Hech qanday qoida bo'lmasa: standart ravishda warning va critical hodisalar yuboriladi.
                </Text>
              </>
            )}
          </Form.List>

          <Divider orientation="left">Tungi sukunat (quiet hours)</Divider>
          <Space>
            <Form.Item name="quiet_start" label="Boshlanishi" style={{ marginBottom: 0 }}>
              <TimePicker format="HH:mm" minuteStep={30} placeholder="22:00" />
            </Form.Item>
            <Form.Item name="quiet_end" label="Tugashi" style={{ marginBottom: 0 }}>
              <TimePicker format="HH:mm" minuteStep={30} placeholder="07:00" />
            </Form.Item>
          </Space>
          <Text type="secondary" style={{ display: 'block', marginTop: 6, fontSize: 12 }}>
            Shu oraliqda faqat <b>critical</b> bildirishnomalar yuboriladi; qolganlar o'tkazib yuboriladi.
          </Text>

          <Divider />
          <Space>
            <Button type="primary" htmlType="submit" loading={saving} icon={<SaveOutlined />}
              style={{ background: '#722ed1', borderColor: '#722ed1' }}>
              Saqlash
            </Button>
            <Tooltip title="Sozlangan Telegram kanaliga sinov xabari yuboradi">
              <Button onClick={onTest} loading={testing} icon={<SendOutlined />}>
                🧪 Test yuborish
              </Button>
            </Tooltip>
          </Space>
        </Form>
      </Card>

      <Card style={{ marginTop: 16 }}
        title={<span><BellOutlined /> Bildirishnoma tarixi</span>}
        extra={<Button size="small" icon={<ReloadOutlined />} onClick={loadHistory}>Yangilash</Button>}>
        <Table
          rowKey="id"
          size="small"
          loading={historyLoading}
          dataSource={history}
          columns={historyCols}
          pagination={{ pageSize: 10 }}
          locale={{ emptyText: 'Hali bildirishnoma yo\'q' }}
        />
      </Card>
    </div>
  )
}
