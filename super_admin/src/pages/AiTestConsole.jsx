import { useEffect, useRef, useState } from 'react'
import {
  Card, Select, Button, Input, Space, Typography, Tag, Empty, message, Tooltip, Switch, Alert,
} from 'antd'
import {
  AudioOutlined, AudioMutedOutlined, SendOutlined, ReloadOutlined,
  RobotOutlined, UserOutlined, SoundOutlined,
} from '@ant-design/icons'
import { aiTestText, aiTestVoice, aiTestReset } from '../api'

const { Text } = Typography

// Telefonsiz AI operator sinov konsoli. Pipeline real telefon bilan 1:1.
export default function AiTestConsole({ restaurants = [] }) {
  const [restaurantId, setRestaurantId] = useState(null)
  const [callId, setCallId] = useState(null)
  const [messages, setMessages] = useState([])     // {role:'user'|'ai', text, audio}
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const [recording, setRecording] = useState(false)
  const [browserTts, setBrowserTts] = useState(true)
  const mediaRef = useRef(null)
  const chunksRef = useRef([])
  const scrollRef = useRef(null)

  const aiRestaurants = restaurants.filter(r => r.ai_agent_enabled)
  const list = aiRestaurants.length ? aiRestaurants : restaurants

  useEffect(() => {
    if (!restaurantId && list.length) setRestaurantId(list[0].id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [restaurants])

  useEffect(() => {
    if (restaurantId && !callId) newCall(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [restaurantId])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  const genCallId = () => `test-${Date.now()}-${Math.floor(Math.random() * 1e6)}`

  const newCall = async (notify = true) => {
    if (callId) { try { await aiTestReset(callId) } catch { /* ignore */ } }
    setCallId(genCallId())
    setMessages([])
    if (notify) message.success('Yangi sinov qo\'ng\'irog\'i')
  }

  const playAudio = (m) => {
    if (m.audio) {
      try { new Audio(`data:audio/mpeg;base64,${m.audio}`).play() } catch { /* ignore */ }
    } else if (browserTts && m.text && window.speechSynthesis) {
      const u = new SpeechSynthesisUtterance(m.text)
      u.lang = 'uz-UZ'
      window.speechSynthesis.cancel()
      window.speechSynthesis.speak(u)
    }
  }

  const handleResult = (userText, data) => {
    setMessages(prev => [
      ...prev,
      { role: 'user', text: userText || data.transcript || '(ovoz)' },
      {
        role: 'ai', text: data.reply_text, audio: data.reply_audio_b64,
        confirmed: data.confirmed, cart: data.cart, ended: data.ended_reason,
      },
    ])
    // javobni darhol ovozli o'qish
    playAudio({ text: data.reply_text, audio: data.reply_audio_b64 })
  }

  const sendText = async () => {
    const t = text.trim()
    if (!t || !restaurantId) return
    setText('')
    setLoading(true)
    try {
      const { data } = await aiTestText({ restaurant_id: restaurantId, call_id: callId, text: t, want_audio: false })
      handleResult(t, data)
    } catch (e) {
      message.error(e.response?.data?.detail || 'Xato')
    } finally { setLoading(false) }
  }

  // ── Mikrofon (push-to-talk) ──
  const startRec = async () => {
    if (!restaurantId) return
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mime = MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')
        ? 'audio/ogg;codecs=opus'
        : (MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : '')
      const mr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
      chunksRef.current = []
      mr.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data)
      mr.onstop = async () => {
        stream.getTracks().forEach(t => t.stop())
        const blob = new Blob(chunksRef.current, { type: mr.mimeType || 'audio/webm' })
        await sendVoice(blob)
      }
      mediaRef.current = mr
      mr.start()
      setRecording(true)
    } catch {
      message.error('Mikrofonga ruxsat berilmadi')
    }
  }

  const stopRec = () => {
    if (mediaRef.current && recording) {
      mediaRef.current.stop()
      setRecording(false)
    }
  }

  const sendVoice = async (blob) => {
    setLoading(true)
    try {
      const ext = blob.type.includes('ogg') ? 'ogg' : 'webm'
      const fd = new FormData()
      fd.append('restaurant_id', restaurantId)
      fd.append('call_id', callId)
      fd.append('audio', blob, `voice.${ext}`)
      const { data } = await aiTestVoice(fd)
      handleResult(data.transcript, data)
    } catch (e) {
      message.error(e.response?.data?.detail || 'Ovoz yuborishda xato')
    } finally { setLoading(false) }
  }

  return (
    <Card
      title={<span><RobotOutlined /> AI operator — sinov qo'ng'irog'i (telefonsiz)</span>}
      extra={
        <Space>
          <Tooltip title="Server TTS yo'q bo'lsa, brauzer ovozi bilan o'qiydi (vaqtinchalik)">
            <span><SoundOutlined /> Brauzer ovozi <Switch size="small" checked={browserTts} onChange={setBrowserTts} /></span>
          </Tooltip>
          <Button icon={<ReloadOutlined />} onClick={() => newCall(true)}>Yangi qo'ng'iroq</Button>
        </Space>
      }
    >
      <Space style={{ marginBottom: 12, width: '100%' }} wrap>
        <Text>Restoran:</Text>
        <Select
          style={{ minWidth: 240 }}
          value={restaurantId}
          onChange={(v) => { setRestaurantId(v); setCallId(null) }}
          options={list.map(r => ({
            value: r.id,
            label: `${r.name}${r.ai_agent_enabled ? '' : ' (AI o\'chiq)'}`,
          }))}
          placeholder="Restoran tanlang"
        />
        {restaurantId && list.find(r => r.id === restaurantId && !r.ai_agent_enabled) && (
          <Tag color="orange">Bu restoranda AI o'chiq — javob bermasligi mumkin</Tag>
        )}
      </Space>

      <Alert
        type="info" showIcon style={{ marginBottom: 12 }}
        message="Sinov rejimi — real buyurtma yaratilmaydi"
        description="Telefon bilan bir xil oqim (STT → AI → TTS). Mikrofonni bosib gapiring yoki matn yozing. Telefon ulanganda aynan shu AI ishlaydi."
      />

      {/* Suhbat */}
      <div
        ref={scrollRef}
        style={{ height: 360, overflowY: 'auto', border: '1px solid #f0f0f0', borderRadius: 10, padding: 16, marginBottom: 12, background: '#fafafa' }}
      >
        {messages.length === 0
          ? <Empty description="Gapiring yoki yozing — masalan: «Salom, 5 ta somsa buyurtma qilmoqchiman»" />
          : messages.map((m, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start', marginBottom: 10 }}>
              <div style={{
                maxWidth: '78%', padding: '8px 12px', borderRadius: 12,
                background: m.role === 'user' ? '#722ed1' : '#fff',
                color: m.role === 'user' ? '#fff' : '#000',
                border: m.role === 'user' ? 'none' : '1px solid #e8e8e8',
              }}>
                <div style={{ fontSize: 11, opacity: 0.7, marginBottom: 2 }}>
                  {m.role === 'user' ? <><UserOutlined /> Siz</> : <><RobotOutlined /> AI</>}
                </div>
                <div style={{ whiteSpace: 'pre-wrap' }}>{m.text || '…'}</div>
                {m.role === 'ai' && (
                  <Space size={4} style={{ marginTop: 4 }}>
                    <Button size="small" type="text" icon={<SoundOutlined />} onClick={() => playAudio(m)}>Eshitish</Button>
                    {m.confirmed && <Tag color="green">Tasdiqlandi</Tag>}
                    {m.ended && <Tag>{m.ended}</Tag>}
                  </Space>
                )}
              </div>
            </div>
          ))}
      </div>

      {/* Kiritish */}
      <Space.Compact style={{ width: '100%' }}>
        <Tooltip title={recording ? 'Qo\'yib yuboring — yuboriladi' : 'Bosib turib gapiring'}>
          <Button
            type={recording ? 'primary' : 'default'}
            danger={recording}
            icon={recording ? <AudioMutedOutlined /> : <AudioOutlined />}
            onMouseDown={startRec} onMouseUp={stopRec}
            onTouchStart={startRec} onTouchEnd={stopRec}
            loading={loading && !recording}
            disabled={!restaurantId}
            style={{ minWidth: 130 }}
          >
            {recording ? 'Yuborish...' : 'Gapirish'}
          </Button>
        </Tooltip>
        <Input
          placeholder="Yoki shu yerga yozing..."
          value={text}
          onChange={(e) => setText(e.target.value)}
          onPressEnter={sendText}
          disabled={!restaurantId}
        />
        <Button type="primary" icon={<SendOutlined />} onClick={sendText} loading={loading} disabled={!restaurantId}>
          Yuborish
        </Button>
      </Space.Compact>
    </Card>
  )
}
