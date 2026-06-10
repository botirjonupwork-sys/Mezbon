import { useEffect, useState } from 'react'
import {
  Card, Button, Input, Switch, message, Alert, Typography, Space, Tag, Popconfirm,
} from 'antd'
import { CreditCardOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import {
  getAutopayStatus, bindAutopayCard, verifyAutopayCard,
  removeAutopayCard, toggleAutopay,
} from '../api'

const { Text } = Typography

const cardStyle = { marginBottom: 12, borderRadius: 14, border: '1px solid #ececec', boxShadow: 'none' }
const cardBody = { padding: 24 }

/**
 * Avtomatik obuna to'lovi (Payme Subscribe) — karta bog'lash + autopay toggle.
 * Karta tokeni serverda shifrlangan; bu yerda faqat oxirgi 4 raqam ko'rinadi.
 */
export default function AutopayCard({ restaurantId }) {
  const restParams = restaurantId ? { restaurant_id: restaurantId } : {}
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState(null)
  const [step, setStep] = useState('idle')   // idle | entering | otp
  const [busy, setBusy] = useState(false)

  // Karta kiritish
  const [cardNumber, setCardNumber] = useState('')
  const [expire, setExpire] = useState('')
  // OTP
  const [pendingCardId, setPendingCardId] = useState(null)
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')

  const load = () => {
    if (!restaurantId) { setLoading(false); return }
    setLoading(true)
    getAutopayStatus(restParams)
      .then((r) => setStatus(r.data))
      .catch(() => message.error('Holatni yuklab bo\'lmadi'))
      .finally(() => setLoading(false))
  }
  useEffect(load, [restaurantId])

  const handleBind = async () => {
    setBusy(true)
    try {
      const r = await bindAutopayCard({ card_number: cardNumber, expire }, restParams)
      setPendingCardId(r.data.card_id)
      setPhone(r.data.phone || '')
      setCardNumber(''); setExpire('')
      setStep('otp')
      message.success('SMS kod yuborildi')
    } catch (e) {
      message.error(e.response?.data?.detail || 'Karta qo\'shishda xato')
    } finally { setBusy(false) }
  }

  const handleVerify = async () => {
    setBusy(true)
    try {
      await verifyAutopayCard({ card_id: pendingCardId, code }, restParams)
      message.success('Karta tasdiqlandi — avtomatik to\'lov yoqildi')
      setStep('idle'); setCode(''); setPendingCardId(null)
      load()
    } catch (e) {
      message.error(e.response?.data?.detail || 'Tasdiqlashda xato')
    } finally { setBusy(false) }
  }

  const handleRemove = async () => {
    try {
      await removeAutopayCard(restParams)
      message.success('Karta o\'chirildi')
      load()
    } catch (e) {
      message.error(e.response?.data?.detail || 'O\'chirishda xato')
    }
  }

  const handleToggle = async (enabled) => {
    try {
      await toggleAutopay({ enabled }, restParams)
      load()
    } catch (e) {
      message.error(e.response?.data?.detail || 'O\'zgartirishda xato')
    }
  }

  const header = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
      <CreditCardOutlined style={{ fontSize: 18, color: '#111827' }} />
      <span style={{ fontSize: 16, fontWeight: 600, color: '#111827' }}>Avtomatik to'lov</span>
    </div>
  )

  if (loading) {
    return <Card style={cardStyle} styles={{ body: cardBody }} loading />
  }

  return (
    <Card style={cardStyle} styles={{ body: cardBody }}>
      {header}
      <Text type="secondary" style={{ fontSize: 13, display: 'block', marginBottom: 16 }}>
        Kartangizni bir marta bog'lang — obuna har oy avtomatik to'lanadi. Karta ma'lumotlari
        Payme tomonida saqlanadi, bizda faqat oxirgi 4 raqam ko'rinadi.
      </Text>

      {status && !status.platform_configured && (
        <Alert
          type="warning" showIcon style={{ borderRadius: 10 }}
          message="Avtomatik to'lov hozircha mavjud emas"
          description="Platforma to'lov tizimi hali ulanmagan. Tez orada faollashtiriladi."
        />
      )}

      {status && status.platform_configured && (
        <>
          {/* Bog'langan karta bor */}
          {status.has_card && step === 'idle' && (
            <Space direction="vertical" size={16} style={{ width: '100%' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Space>
                  <SafetyCertificateOutlined style={{ color: '#16a34a' }} />
                  <Text strong>•••• {status.card_last4}</Text>
                  {status.card_expire && <Text type="secondary">{status.card_expire}</Text>}
                  {status.card_verified
                    ? <Tag color="green">Tasdiqlangan</Tag>
                    : <Tag color="orange">Tasdiqlanmagan</Tag>}
                </Space>
                <Popconfirm title="Kartani o'chirasizmi?" onConfirm={handleRemove} okText="Ha" cancelText="Yo'q">
                  <Button danger size="small">O'chirish</Button>
                </Popconfirm>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <Switch
                  checked={!!status.autopay_enabled}
                  disabled={!status.card_verified}
                  onChange={handleToggle}
                />
                <Text>Har oy avtomatik to'lash</Text>
              </div>
            </Space>
          )}

          {/* Karta yo'q — qo'shish tugmasi */}
          {!status.has_card && step === 'idle' && (
            <Button type="primary" icon={<CreditCardOutlined />} onClick={() => setStep('entering')}
              style={{ background: '#111827', borderColor: '#111827', borderRadius: 10 }}>
              Karta qo'shish
            </Button>
          )}

          {/* Karta kiritish formasi */}
          {step === 'entering' && (
            <Space direction="vertical" size={12} style={{ width: '100%', maxWidth: 360 }}>
              <Input
                placeholder="Karta raqami" maxLength={19} inputMode="numeric"
                value={cardNumber} onChange={(e) => setCardNumber(e.target.value)}
              />
              <Input
                placeholder="Amal muddati (MM/YY)" maxLength={5} inputMode="numeric"
                value={expire} onChange={(e) => setExpire(e.target.value)}
              />
              <Space>
                <Button type="primary" loading={busy} onClick={handleBind}
                  style={{ background: '#111827', borderColor: '#111827' }}>
                  Davom etish
                </Button>
                <Button onClick={() => { setStep('idle'); setCardNumber(''); setExpire('') }}>Bekor</Button>
              </Space>
            </Space>
          )}

          {/* SMS kod */}
          {step === 'otp' && (
            <Space direction="vertical" size={12} style={{ width: '100%', maxWidth: 360 }}>
              <Text type="secondary">
                {phone ? `${phone} raqamiga ` : ''}yuborilgan SMS kodni kiriting
              </Text>
              <Input
                placeholder="SMS kod" maxLength={6} inputMode="numeric"
                value={code} onChange={(e) => setCode(e.target.value)}
              />
              <Space>
                <Button type="primary" loading={busy} onClick={handleVerify}
                  style={{ background: '#111827', borderColor: '#111827' }}>
                  Tasdiqlash
                </Button>
                <Button onClick={() => { setStep('idle'); setCode('') }}>Bekor</Button>
              </Space>
            </Space>
          )}
        </>
      )}
    </Card>
  )
}
