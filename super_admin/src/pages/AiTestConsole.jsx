import { useEffect, useRef, useState } from 'react'
import {
  Card, Select, Button, Input, Space, Typography, Tag, Empty, message, Tooltip, Switch, Alert, Segmented, Slider,
} from 'antd'
import {
  AudioOutlined, AudioMutedOutlined, SendOutlined, ReloadOutlined,
  RobotOutlined, UserOutlined, SoundOutlined, PhoneOutlined, PhoneFilled,
} from '@ant-design/icons'
import { aiTestText, aiTestVoice, aiTestReset, aiTestCallStart, getPlatformSettings, updatePlatformSettings } from '../api'

const { Text } = Typography

// VAD parametrlari (real-time telefon rejimi uchun)
const SILENCE_MS = 800       // shu qadar jimlikdan keyin "gap tugadi"
const MIN_SPEECH_MS = 300    // bundan qisqa shovqin — e'tiborsiz

// Brauzerdagi audio blob (webm/ogg/opus) → 16kHz mono WAV (Aisha/Whisper uchun universal)
async function blobToWav(blob, targetSr = 16000) {
  const ab = await blob.arrayBuffer()
  const Ctx = window.AudioContext || window.webkitAudioContext
  const ctx = new Ctx()
  const decoded = await ctx.decodeAudioData(ab)
  ctx.close()
  const ch = decoded.numberOfChannels, len = decoded.length
  const mono = new Float32Array(len)
  for (let c = 0; c < ch; c++) {
    const d = decoded.getChannelData(c)
    for (let i = 0; i < len; i++) mono[i] += d[i] / ch
  }
  const ratio = decoded.sampleRate / targetSr
  const outLen = Math.max(1, Math.floor(len / ratio))
  const out = new Float32Array(outLen)
  for (let i = 0; i < outLen; i++) out[i] = mono[Math.floor(i * ratio)] || 0
  const buf = new ArrayBuffer(44 + outLen * 2)
  const view = new DataView(buf)
  const wr = (o, s) => { for (let i = 0; i < s.length; i++) view.setUint8(o + i, s.charCodeAt(i)) }
  wr(0, 'RIFF'); view.setUint32(4, 36 + outLen * 2, true); wr(8, 'WAVE'); wr(12, 'fmt ')
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true)
  view.setUint32(24, targetSr, true); view.setUint32(28, targetSr * 2, true)
  view.setUint16(32, 2, true); view.setUint16(34, 16, true); wr(36, 'data')
  view.setUint32(40, outLen * 2, true)
  let off = 44
  for (let i = 0; i < outLen; i++) {
    const s = Math.max(-1, Math.min(1, out[i]))
    view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7FFF, true); off += 2
  }
  return new Blob([view], { type: 'audio/wav' })
}

const STATUS_LABEL = {
  idle: { text: 'Qo\'ng\'iroq yo\'q', color: 'default' },
  listening: { text: '👂 Tinglayapman...', color: 'blue' },
  recording: { text: '🎤 Gapiryapsiz...', color: 'red' },
  thinking: { text: '💭 O\'ylayapman...', color: 'orange' },
  speaking: { text: '🗣 Javob beryapman...', color: 'green' },
}

export default function AiTestConsole({ restaurants = [] }) {
  const [restaurantId, setRestaurantId] = useState(null)
  const [callId, setCallId] = useState(null)
  const [messages, setMessages] = useState([])
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const [recording, setRecording] = useState(false)   // telegram push-to-talk
  const [browserTts, setBrowserTts] = useState(true)
  const [mode, setMode] = useState('phone')            // 'phone' | 'telegram'
  const [callActive, setCallActive] = useState(false)
  const [status, setStatus] = useState('idle')
  const [sensitivity, setSensitivity] = useState(30)   // 10..60 → RMS thresh

  // LLM / STT / TTS boshqaruvi (platform sozlamalaridan o'qiladi va yoziladi)
  const [providers, setProviders] = useState([])       // ai_providers katalogi
  const [keyStatus, setKeyStatus] = useState({})       // {provider: {set, masked}}
  const [llmProvider, setLlmProvider] = useState(null)
  const [llmModel, setLlmModel] = useState(null)
  const [sttOn, setSttOn] = useState(false)
  const [ttsOn, setTtsOn] = useState(false)
  const [savingCfg, setSavingCfg] = useState(false)
  const [rateLimit, setRateLimit] = useState(null)   // Groq qolgan limit (oxirgi javobdan)
  const sttProvRef = useRef('aisha')                   // STT yoqilganda ishlatiladigan provayder
  const ttsProvRef = useRef('aisha')                   // TTS yoqilganda ishlatiladigan provayder

  // refs (real-time loop)
  const streamRef = useRef(null)
  const audioCtxRef = useRef(null)
  const analyserRef = useRef(null)
  const rafRef = useRef(null)
  const recRef = useRef(null)
  const chunksRef = useRef([])
  const stateRef = useRef('idle')          // loop o'qiydigan status
  const silenceStartRef = useRef(null)
  const speechStartRef = useRef(0)
  const busyRef = useRef(false)            // server bilan band (overlap bo'lmasin)
  const aiAudioRef = useRef(null)          // joriy AI audio (barge-in uchun)
  const callIdRef = useRef(null)
  const restIdRef = useRef(null)
  const scrollRef = useRef(null)

  const list = restaurants.filter(r => r.ai_agent_enabled).length
    ? restaurants.filter(r => r.ai_agent_enabled) : restaurants

  useEffect(() => { callIdRef.current = callId }, [callId])
  useEffect(() => { restIdRef.current = restaurantId }, [restaurantId])
  useEffect(() => { stateRef.current = status }, [status])

  useEffect(() => {
    if (!restaurantId && list.length) setRestaurantId(list[0].id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [restaurants])

  useEffect(() => {
    if (restaurantId && !callId) beginCallSession()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [restaurantId])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  useEffect(() => () => endCall(), [])     // unmount → tozalash

  // Platform sozlamalarini yuklash — LLM/STT/TTS joriy holati
  useEffect(() => {
    (async () => {
      try {
        const { data } = await getPlatformSettings()
        setProviders(data.ai_providers || [])
        setKeyStatus(data.ai_llm_api_keys_status || {})
        setLlmProvider(data.ai_llm_provider || null)
        setLlmModel(data.ai_llm_model || null)
        const off = new Set(['none', 'off', 'disabled', ''])
        const stt = (data.ai_stt_provider || 'none').toLowerCase()
        const tts = (data.ai_tts_provider || 'none').toLowerCase()
        setSttOn(!off.has(stt)); if (!off.has(stt)) sttProvRef.current = stt
        setTtsOn(!off.has(tts)); if (!off.has(tts)) ttsProvRef.current = tts
      } catch { /* sozlama yuklanmadi — jim o'tamiz */ }
    })()
  }, [])

  const changeLlm = async (val) => {
    const idx = val.indexOf('::')
    const prov = val.slice(0, idx), model = val.slice(idx + 2)
    setLlmProvider(prov); setLlmModel(model); setSavingCfg(true)
    try {
      await updatePlatformSettings({ ai_llm_provider: prov, ai_llm_model: model })
      message.success(`LLM: ${prov} / ${model}`)
    } catch { message.error('LLM saqlanmadi') }
    finally { setSavingCfg(false) }
  }

  const toggleStt = async (on) => {
    setSttOn(on)
    try { await updatePlatformSettings({ ai_stt_provider: on ? sttProvRef.current : 'none' }) }
    catch { message.error('STT saqlanmadi'); setSttOn(!on) }
  }

  const toggleTts = async (on) => {
    setTtsOn(on)
    try { await updatePlatformSettings({ ai_tts_provider: on ? ttsProvRef.current : 'none' }) }
    catch { message.error('TTS saqlanmadi'); setTtsOn(!on) }
  }

  // LLM Select uchun guruhlangan optionlar (kalit yo'q provayderlar bloklangan)
  const llmOptions = providers.map(p => ({
    label: `${p.display_name}${keyStatus[p.name]?.set ? '' : ' — kalit yo\'q'}`,
    options: (p.models || []).map(m => ({
      value: `${p.name}::${m.value}`,
      label: `${m.label}${m.free ? ' · bepul' : ''}${m.notes ? ` (${m.notes})` : ''}`,
      disabled: !keyStatus[p.name]?.set,
    })),
  }))
  const llmValue = llmProvider && llmModel ? `${llmProvider}::${llmModel}` : undefined

  const genCallId = () => `test-${Date.now()}-${Math.floor(Math.random() * 1e6)}`

  const beginCallSession = async (id = null, rid = null) => {
    const cid = id || genCallId()
    const restId = rid || restaurantId
    if (!restId) return cid
    if (callId && callId !== cid) {
      try { await aiTestReset(callId) } catch { /* ignore */ }
    }
    setCallId(cid)
    setMessages([])
    try {
      const { data } = await aiTestCallStart({ restaurant_id: restId, call_id: cid })
      const greeting = {
        role: 'ai',
        text: data.reply_text,
        audio: data.reply_audio_b64,
        mime: data.reply_audio_mime,
        greeting: true,
      }
      setMessages([greeting])
      speak(greeting)
    } catch (e) {
      message.error(e.response?.data?.detail || 'Salomlashish xatosi')
    }
    return cid
  }

  const newCall = () => beginCallSession()

  // ── Audio chiqarish (AI javob) ──
  const speak = (m, onDone) => {
    if (m.audio) {
      const a = new Audio(`data:${m.mime || 'audio/wav'};base64,${m.audio}`)
      aiAudioRef.current = a
      a.onended = () => { aiAudioRef.current = null; onDone?.() }
      a.play().catch(() => onDone?.())
    } else if (browserTts && m.text && window.speechSynthesis) {
      const u = new SpeechSynthesisUtterance(m.text)
      u.lang = 'uz-UZ'
      u.onend = () => { aiAudioRef.current = null; onDone?.() }
      aiAudioRef.current = { stop: () => window.speechSynthesis.cancel() }
      window.speechSynthesis.cancel()
      window.speechSynthesis.speak(u)
    } else { onDone?.() }
  }

  const stopAiAudio = () => {
    const a = aiAudioRef.current
    if (a) {
      try { a.pause ? a.pause() : a.stop?.() } catch { /* ignore */ }
      try { window.speechSynthesis?.cancel() } catch { /* ignore */ }
      aiAudioRef.current = null
    }
  }

  const pushMessages = (userText, data) => {
    const aiMsg = {
      role: 'ai',
      text: data.reply_text,
      audio: data.reply_audio_b64,
      mime: data.reply_audio_mime,
      confirmed: data.confirmed,
      ended: data.ended_reason === 'conversation_complete',
      orderId: data.simulated_order_id || data.last_order_id,
      locationLink: data.location_link_preview,
    }
    setMessages(prev => [
      ...prev,
      { role: 'user', text: userText || data.transcript || '(ovoz)' },
      aiMsg,
    ])
    if (data.rate_limit && Object.keys(data.rate_limit).length) setRateLimit(data.rate_limit)
    return aiMsg
  }

  // ── TELEGRAM rejimi: matn ──
  const sendText = async () => {
    const t = text.trim(); if (!t || !restaurantId) return
    setText(''); setLoading(true)
    try {
      const { data } = await aiTestText({ restaurant_id: restaurantId, call_id: callId, text: t, want_audio: ttsOn })
      const aiMsg = pushMessages(t, data)
      speak(aiMsg, () => { if (data.ended_reason === 'conversation_complete') endCall() })
    } catch (e) { message.error(e.response?.data?.detail || 'Xato') }
    finally { setLoading(false) }
  }

  // ── TELEGRAM rejimi: push-to-talk ──
  const startРTT = async () => {
    if (!restaurantId) return
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mime = pickMime()
      const mr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
      chunksRef.current = []
      mr.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data)
      mr.onstop = async () => {
        stream.getTracks().forEach(t => t.stop())
        try {
          const data = await sendVoiceBlob(new Blob(chunksRef.current, { type: mr.mimeType || 'audio/webm' }))
          if (data && (data.reply_text || data.transcript)) {
            const aiMsg = pushMessages(data.transcript, data)
            speak(aiMsg, () => { if (data.ended_reason === 'conversation_complete') endCall() })
          }
        } catch (e) { message.error(e.response?.data?.detail || 'Ovoz xatosi') }
      }
      recRef.current = mr; mr.start(); setRecording(true)
    } catch { message.error('Mikrofonga ruxsat berilmadi') }
  }
  const stopPTT = () => { if (recRef.current && recording) { recRef.current.stop(); setRecording(false) } }

  const pickMime = () =>
    MediaRecorder.isTypeSupported('audio/ogg;codecs=opus') ? 'audio/ogg;codecs=opus'
      : (MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : '')

  const sendVoiceBlob = async (blob, { silent = false } = {}) => {
    if (!silent) setLoading(true)
    try {
      // webm/opus'ni Aisha qabul qilmaydi → brauzerda WAV'ga aylantiramiz (universal)
      let sendBlob = blob, name = 'voice.wav'
      try {
        sendBlob = await blobToWav(blob)
      } catch {
        name = blob.type.includes('ogg') ? 'voice.ogg' : 'voice.webm'  // fallback
      }
      const fd = new FormData()
      fd.append('restaurant_id', restIdRef.current)
      fd.append('call_id', callIdRef.current)
      fd.append('audio', sendBlob, name)
      const { data } = await aiTestVoice(fd)
      return data
    } finally { if (!silent) setLoading(false) }
  }

  // ── TELEFON rejimi: real-time hands-free (VAD + barge-in) ──
  const startCall = async () => {
    if (!restaurantId) return
    if (!messages.length) await beginCallSession()
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
      streamRef.current = stream
      const ctx = new (window.AudioContext || window.webkitAudioContext)()
      audioCtxRef.current = ctx
      const src = ctx.createMediaStreamSource(stream)
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 1024
      src.connect(analyser)
      analyserRef.current = analyser
      setCallActive(true); setStatus('listening')
      loop()
    } catch { message.error('Mikrofonga ruxsat berilmadi') }
  }

  const endCall = () => {
    setCallActive(false); setStatus('idle')
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    stopAiAudio()
    try { recRef.current?.state === 'recording' && recRef.current.stop() } catch { /* ignore */ }
    try { streamRef.current?.getTracks().forEach(t => t.stop()) } catch { /* ignore */ }
    try { audioCtxRef.current?.close() } catch { /* ignore */ }
    streamRef.current = null; audioCtxRef.current = null; analyserRef.current = null
  }

  const beginUtterance = () => {
    const stream = streamRef.current; if (!stream) return
    const mime = pickMime()
    const mr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
    chunksRef.current = []
    mr.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data)
    mr.onstop = () => finishUtterance(mr.mimeType || 'audio/webm')
    recRef.current = mr; mr.start()
    speechStartRef.current = performance.now()
    setStatus('recording')
  }

  const finishUtterance = async (mime) => {
    const dur = performance.now() - speechStartRef.current
    const blob = new Blob(chunksRef.current, { type: mime })
    if (dur < MIN_SPEECH_MS || blob.size < 1200) { setStatus('listening'); return }  // juda qisqa — tashlab
    busyRef.current = true
    setStatus('thinking')
    try {
      const data = await sendVoiceBlob(blob, { silent: true })
      if (data && (data.reply_text || data.transcript)) {
        pushMessages(data.transcript, data)
        setStatus('speaking')
        const lastAi = { text: data.reply_text, audio: data.reply_audio_b64, mime: data.reply_audio_mime }
        speak(lastAi, () => {
          busyRef.current = false
          if (data.ended_reason === 'conversation_complete') {
            endCall()
            return
          }
          if (callActiveRef()) setStatus('listening')
        })
        return
      }
    } catch (e) {
      message.error(e.response?.data?.detail || 'Ovoz xatosi')
    }
    busyRef.current = false
    setStatus('listening')
  }

  const callActiveRef = () => !!streamRef.current

  // RMS o'lchov + holat mashinasi
  const loop = () => {
    const analyser = analyserRef.current
    if (!analyser) return
    const buf = new Uint8Array(analyser.fftSize)
    analyser.getByteTimeDomainData(buf)
    let sum = 0
    for (let i = 0; i < buf.length; i++) { const v = (buf[i] - 128) / 128; sum += v * v }
    const rms = Math.sqrt(sum / buf.length)
    const thresh = sensitivity / 1000   // 30 → 0.03
    const now = performance.now()
    const st = stateRef.current

    if (st === 'speaking') {
      // barge-in: AI gapirayotganda foydalanuvchi gapirsa — to'xtatib, yangi gapni yozamiz
      if (rms > thresh * 1.6) { stopAiAudio(); busyRef.current = false; beginUtterance() }
    } else if (st === 'listening') {
      if (rms > thresh && !busyRef.current) beginUtterance()
    } else if (st === 'recording') {
      if (rms > thresh) { silenceStartRef.current = null }
      else {
        if (silenceStartRef.current == null) silenceStartRef.current = now
        else if (now - silenceStartRef.current > SILENCE_MS) {
          silenceStartRef.current = null
          try { recRef.current?.state === 'recording' && recRef.current.stop() } catch { /* ignore */ }
        }
      }
    }
    rafRef.current = requestAnimationFrame(loop)
  }

  const stInfo = STATUS_LABEL[status] || STATUS_LABEL.idle

  return (
    <Card
      title={<span><RobotOutlined /> AI operator — sinov ({mode === 'phone' ? 'telefon, real-time' : 'Telegram'})</span>}
      extra={
        <Space>
          <Segmented
            value={mode}
            onChange={(v) => { endCall(); setMode(v) }}
            options={[
              { label: 'Telefon', value: 'phone', icon: <PhoneOutlined /> },
              { label: 'Telegram', value: 'telegram', icon: <AudioOutlined /> },
            ]}
          />
          <Tooltip title="Server TTS yo'q bo'lsa, brauzer ovozi bilan o'qiydi (vaqtinchalik)">
            <span><SoundOutlined /> <Switch size="small" checked={browserTts} onChange={setBrowserTts} /></span>
          </Tooltip>
          <Button icon={<ReloadOutlined />} onClick={newCall}>Yangi</Button>
        </Space>
      }
    >
      <Space style={{ marginBottom: 12, width: '100%' }} wrap>
        <Text>Restoran:</Text>
        <Select
          style={{ minWidth: 220 }}
          value={restaurantId}
          onChange={(v) => { endCall(); setRestaurantId(v); setCallId(null) }}
          options={list.map(r => ({ value: r.id, label: `${r.name}${r.ai_agent_enabled ? '' : ' (AI o\'chiq)'}` }))}
          placeholder="Restoran tanlang"
        />
        {mode === 'phone' && (
          <Tag color={stInfo.color} style={{ fontSize: 13, padding: '2px 10px' }}>{stInfo.text}</Tag>
        )}
      </Space>

      {/* LLM tanlash + STT/TTS yoqish-o'chirish */}
      <Space style={{ marginBottom: 12, width: '100%' }} wrap>
        <Text>LLM:</Text>
        <Select
          style={{ minWidth: 340 }}
          value={llmValue}
          onChange={changeLlm}
          loading={savingCfg}
          options={llmOptions}
          placeholder="Model tanlang"
          showSearch
          optionFilterProp="label"
        />
        <Tooltip title="STT (ovoz→matn). O'chirilsa faqat matn yozib sinaladi, mikrofon ishlamaydi.">
          <span><AudioOutlined /> STT <Switch size="small" checked={sttOn} onChange={toggleStt} /></span>
        </Tooltip>
        <Tooltip title="TTS (matn→ovoz). O'chirilsa AI faqat matn qaytaradi (server ovozi yo'q).">
          <span><SoundOutlined /> TTS <Switch size="small" checked={ttsOn} onChange={toggleTts} /></span>
        </Tooltip>
        {rateLimit && (
          <Tooltip title={`Provayder limiti (oxirgi javobdan). So'rov yangilanishi: ${rateLimit.reset_requests || '—'}, token yangilanishi: ${rateLimit.reset_tokens || '—'}`}>
            <Tag color={
              rateLimit.remaining_requests != null && rateLimit.limit_requests
                ? (rateLimit.remaining_requests / rateLimit.limit_requests < 0.1 ? 'red'
                   : rateLimit.remaining_requests / rateLimit.limit_requests < 0.3 ? 'orange' : 'green')
                : 'blue'
            }>
              ⚡ Qolgan limit:&nbsp;
              {rateLimit.remaining_requests != null
                ? `${rateLimit.remaining_requests.toLocaleString()}/${(rateLimit.limit_requests ?? 0).toLocaleString()} so'rov`
                : ''}
              {rateLimit.remaining_tokens != null
                ? ` · ${rateLimit.remaining_tokens.toLocaleString()}/${(rateLimit.limit_tokens ?? 0).toLocaleString()} token`
                : ''}
            </Tag>
          </Tooltip>
        )}
      </Space>

      {mode === 'phone' && !sttOn && (
        <Alert type="warning" showIcon style={{ marginBottom: 12 }}
          message="STT o'chiq — telefon (ovozli) rejim ishlamaydi"
          description="Faqat matn bilan sinash uchun 'Telegram' rejimiga o'ting va pastdagi maydonga yozing. Ovozli sinov uchun STT'ni yoqing." />
      )}

      {mode === 'phone' && sttOn && (
        <Alert
          type="info" showIcon style={{ marginBottom: 12 }}
          message="Real-time telefon rejimi — gapiring, pauza qilsangiz javob beradi"
          description="Tugmani bosishingiz shart emas. Gapirib bo'ling — o'zi eshitadi, javob beradi, keyin yana tinglaydi. AI gapirayotganda gapirsangiz — bo'lib (barge-in) yangi gapingizni oladi. Latency STT+AI+TTS'ga bog'liq (~1.5–3s)."
        />
      )}

      {/* Suhbat */}
      <div ref={scrollRef} style={{ height: 320, overflowY: 'auto', border: '1px solid #f0f0f0', borderRadius: 10, padding: 16, marginBottom: 12, background: '#fafafa' }}>
        {messages.length === 0
          ? <Empty description={mode === 'phone' ? 'Qo\'ng\'iroqni boshlang — operator salomlashadi' : 'Yangi qo\'ng\'iroq yoki yozing'} />
          : messages.map((m, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start', marginBottom: 10 }}>
              <div style={{ maxWidth: '78%', padding: '8px 12px', borderRadius: 12,
                background: m.role === 'user' ? '#722ed1' : '#fff', color: m.role === 'user' ? '#fff' : '#000',
                border: m.role === 'user' ? 'none' : '1px solid #e8e8e8' }}>
                <div style={{ fontSize: 11, opacity: 0.7, marginBottom: 2 }}>
                  {m.role === 'user' ? <><UserOutlined /> Siz</> : <><RobotOutlined /> Operator</>}
                  {m.greeting && <Tag color="blue" style={{ marginLeft: 6 }}>Salomlashish</Tag>}
                </div>
                <div style={{ whiteSpace: 'pre-wrap' }}>{m.text || '…'}</div>
                {m.locationLink && (
                  <div style={{ fontSize: 12, marginTop: 6, color: '#1677ff' }}>📍 {m.locationLink}</div>
                )}
                {m.role === 'ai' && (
                  <Space size={4} style={{ marginTop: 4 }} wrap>
                    <Button size="small" type="text" icon={<SoundOutlined />} onClick={() => speak(m)}>Eshitish</Button>
                    {m.confirmed && <Tag color="green">Buyurtma qabul qilindi{m.orderId ? ` №${m.orderId}` : ''}</Tag>}
                    {m.ended && <Tag color="default">Suhbat tugadi</Tag>}
                  </Space>
                )}
              </div>
            </div>
          ))}
      </div>

      {/* Boshqaruv */}
      {mode === 'phone' ? (
        <Space direction="vertical" style={{ width: '100%' }}>
          {!callActive ? (
            <Button type="primary" size="large" block icon={<PhoneFilled />} onClick={startCall}
              disabled={!restaurantId || !sttOn} style={{ background: '#52c41a', borderColor: '#52c41a' }}>
              Qo'ng'iroqni boshlash
            </Button>
          ) : (
            <Button danger size="large" block icon={<PhoneOutlined />} onClick={endCall}>
              Qo'ng'iroqni tugatish
            </Button>
          )}
          <Space style={{ width: '100%' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>Mikrofon sezgirligi:</Text>
            <Slider min={10} max={60} value={sensitivity} onChange={setSensitivity} style={{ width: 160 }} />
            <Text type="secondary" style={{ fontSize: 12 }}>(shovqinli joyda pasaytiring)</Text>
          </Space>
        </Space>
      ) : (
        <Space.Compact style={{ width: '100%' }}>
          <Tooltip title={recording ? 'Qo\'yib yuboring' : 'Bosib turib gapiring'}>
            <Button type={recording ? 'primary' : 'default'} danger={recording}
              icon={recording ? <AudioMutedOutlined /> : <AudioOutlined />}
              onMouseDown={startРTT} onMouseUp={stopPTT} onTouchStart={startРTT} onTouchEnd={stopPTT}
              loading={loading && !recording} disabled={!restaurantId || !sttOn} style={{ minWidth: 130 }}>
              {recording ? 'Yuborish...' : 'Gapirish'}
            </Button>
          </Tooltip>
          <Input placeholder="Yoki yozing..." value={text} onChange={(e) => setText(e.target.value)}
            onPressEnter={sendText} disabled={!restaurantId} />
          <Button type="primary" icon={<SendOutlined />} onClick={sendText} loading={loading} disabled={!restaurantId}>
            Yuborish
          </Button>
        </Space.Compact>
      )}
    </Card>
  )
}
