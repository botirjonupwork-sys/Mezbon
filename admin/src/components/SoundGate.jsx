// Ovoz darvozasi — operator paneli ovozsiz ishlamasligi uchun bloklovchi modal.
//
// Talab: panel ovoz bilan ishlashi shart (yangi buyurtma kelganda ovoz chalinadi).
// Brauzer foydalanuvchi klik qilmaguncha ovozni bloklaydi, shuning uchun:
//   1. Panel ochilganda (yoki ovoz "running" emasligi aniqlanganda) — CRITICAL modal
//      ochiladi va butun ilovani bloklaydi.
//   2. Operator "Tekshirish" bosadi → eshitiladigan signal chalinadi.
//   3. Operator "Ha, eshitdim" bilan tasdiqlaydi → daravoza ochiladi, panel tayyor.
//   4. Keyinchalik kontekst yana to'xtab qolsa (tab fonga o'tsa, qurilma o'zgarsa) —
//      darvoza qayta bloklaydi. Yagona haqiqat manbai: AudioContext 'running' holati.
import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { Alert, Button, Modal, Space, Typography } from 'antd'
import { SoundOutlined, CheckCircleOutlined } from '@ant-design/icons'
import * as soundGate from '../audio/soundGate'

const { Title, Paragraph, Text } = Typography

const SoundGateContext = createContext({ ready: false })
export const useSoundGate = () => useContext(SoundGateContext)

const RECHECK_MS = 4000

export default function SoundGate({ children }) {
  const supported = soundGate.isSupported()
  const [ready, setReady] = useState(() => soundGate.isReady())
  // idle | testing | confirm | failed
  const [phase, setPhase] = useState('idle')

  // Yagona haqiqat manbai: kontekst 'running' bo'lmasa — bloklaymiz.
  useEffect(() => {
    const unsub = soundGate.subscribe((r) => {
      if (!r) { setReady(false); setPhase((p) => (p === 'confirm' ? 'idle' : p)) }
    })
    return unsub
  }, [])

  // Davriy va fokus qaytganda qayta tekshirish (tab fonga o'tib qaytishi mumkin).
  useEffect(() => {
    const check = () => { if (!soundGate.isReady()) setReady(false) }
    const id = setInterval(check, RECHECK_MS)
    document.addEventListener('visibilitychange', check)
    window.addEventListener('focus', check)
    return () => {
      clearInterval(id)
      document.removeEventListener('visibilitychange', check)
      window.removeEventListener('focus', check)
    }
  }, [])

  const runTest = useCallback(async () => {
    setPhase('testing')
    const ok = await soundGate.playTest()
    setPhase(ok ? 'confirm' : 'failed')
  }, [])

  const replayTest = useCallback(async () => {
    await soundGate.playTest()
  }, [])

  const confirmHeard = useCallback(() => {
    // Tasdiq paytida kontekst haqiqatan 'running' ekanini ham tekshiramiz —
    // aks holda (masalan, shu orada to'xtab qolgan bo'lsa) darvoza ochilmaydi.
    if (!soundGate.isReady()) {
      setPhase('failed')
      return
    }
    setReady(true)
    setPhase('idle')
  }, [])

  const blocked = !ready

  return (
    <SoundGateContext.Provider value={{ ready }}>
      {children}
      <Modal
        open={blocked}
        closable={false}
        maskClosable={false}
        keyboard={false}
        footer={null}
        centered
        width={460}
        zIndex={2000}
        title={<span><SoundOutlined style={{ color: '#fa8c16' }} /> Ovoz sozlamasi talab qilinadi</span>}
      >
        {!supported && (
          <Alert
            type="error"
            showIcon
            message="Brauzer ovozni qo'llab-quvvatlamaydi"
            description="Bu brauzerda Web Audio mavjud emas. Iltimos, Chrome yoki Edge brauzeridan foydalaning."
          />
        )}

        {supported && (phase === 'idle' || phase === 'testing') && (
          <>
            <Paragraph>
              Panel <Text strong>ovoz bilan</Text> ishlaydi — yangi buyurtma kelganda
              signal chalinadi. Ishlashni boshlashdan oldin qurilma ovozini tekshirib,
              yoqib qo'yish shart.
            </Paragraph>
            <Paragraph type="secondary" style={{ fontSize: 13 }}>
              Qurilma karnayi yoqilganini va ovoz balandligi yetarli ekanini tekshiring,
              so'ng quyidagi tugmani bosing.
            </Paragraph>
            <Button
              type="primary"
              size="large"
              block
              icon={<SoundOutlined />}
              loading={phase === 'testing'}
              onClick={runTest}
              style={{ background: '#fa8c16', borderColor: '#fa8c16' }}
            >
              🔊 Ovozni tekshirish va yoqish
            </Button>
          </>
        )}

        {supported && phase === 'confirm' && (
          <>
            <Alert
              type="info"
              showIcon
              message="Signal chalindi"
              description="Test signalini eshitdingizmi? Eshitmasangiz, qurilma ovozini oshiring va qaytadan chaling."
              style={{ marginBottom: 16 }}
            />
            <Space direction="vertical" style={{ width: '100%' }} size={8}>
              <Button
                type="primary"
                size="large"
                block
                icon={<CheckCircleOutlined />}
                onClick={confirmHeard}
              >
                Ha, eshitdim — ishlashni boshlash
              </Button>
              <Button block onClick={replayTest}>Qaytadan chalish</Button>
              <Button type="text" danger block onClick={() => setPhase('failed')}>
                Yo'q, eshitmadim
              </Button>
            </Space>
          </>
        )}

        {supported && phase === 'failed' && (
          <>
            <Alert
              type="warning"
              showIcon
              message="Ovoz eshitilmadi"
              description={
                <ul style={{ margin: '8px 0 0', paddingLeft: 18 }}>
                  <li>Qurilma ovozi (volume) yoqilganini tekshiring</li>
                  <li>Karnay/naushnik ulanganini tekshiring</li>
                  <li>Brauzer yorlig'idagi ovoz belgisi o'chirilmaganini ko'ring</li>
                  <li>Boshqa ilova ovozni band qilmaganiga ishonch hosil qiling</li>
                </ul>
              }
              style={{ marginBottom: 16 }}
            />
            <Button
              type="primary"
              size="large"
              block
              icon={<SoundOutlined />}
              onClick={runTest}
              style={{ background: '#fa8c16', borderColor: '#fa8c16' }}
            >
              Qayta urinish
            </Button>
          </>
        )}
      </Modal>
    </SoundGateContext.Provider>
  )
}
