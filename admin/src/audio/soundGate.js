// Umumiy Web Audio engine — buyurtma ovozi va "ovoz darvozasi" uchun.
//
// Muammo: brauzer AudioContext'ni foydalanuvchi gesture (klik) bo'lmaguncha
// "suspended" holatda ushlaydi — shu sabab har safar yangi AudioContext yaratib
// ovoz chalish jimgina muvaffaqiyatsiz bo'ladi. Yechim: BITTA umumiy, bir marta
// (foydalanuvchi klik bilan) ochilgan AudioContext'ni butun ilova davomida ushlab
// turamiz va uning holatini ('running' yoki yo'q) yagona haqiqat manbai sifatida
// ishlatamiz. SoundGate modal aynan shu holatga qarab bloklaydi/ochadi.

let ctx = null
const listeners = new Set()

export function isSupported() {
  return !!(window.AudioContext || window.webkitAudioContext)
}

function emit() {
  const ready = isReady()
  listeners.forEach((fn) => {
    try { fn(ready) } catch { /* listener xatosi engine'ni buzmasin */ }
  })
}

function getCtx() {
  if (ctx) return ctx
  const AC = window.AudioContext || window.webkitAudioContext
  if (!AC) return null
  ctx = new AC()
  // Holat o'zgarsa (suspended ↔ running, masalan tab fon rejimga o'tsa) — xabar beramiz
  if (typeof ctx.addEventListener === 'function') {
    ctx.addEventListener('statechange', emit)
  }
  return ctx
}

// Ovoz hozir chalishga TAYYORmi (kontekst mavjud va 'running').
export function isReady() {
  return !!ctx && ctx.state === 'running'
}

// Tayyorlik holati o'zgarishini kuzatish. Tozalash funksiyasini qaytaradi.
export function subscribe(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

// Kontekstni ochish — FAQAT foydalanuvchi gesture (klik) ichida chaqirilishi shart.
export async function unlock() {
  const c = getCtx()
  if (!c) return false
  try {
    if (c.state !== 'running') await c.resume()
  } catch { /* resume rad etilishi mumkin — quyida holatga qaraymiz */ }
  emit()
  return isReady()
}

function beep(c, freq, startOffset, duration, volume = 0.3) {
  const osc = c.createOscillator()
  const gain = c.createGain()
  osc.connect(gain)
  gain.connect(c.destination)
  osc.type = 'sine'
  const t0 = c.currentTime + startOffset
  osc.frequency.setValueAtTime(freq, t0)
  gain.gain.setValueAtTime(volume, t0)
  gain.gain.exponentialRampToValueAtTime(0.01, t0 + duration)
  osc.start(t0)
  osc.stop(t0 + duration)
}

// Tekshirish uchun eshitiladigan qisqa signal. Klik ichida chaqiriladi.
// Kontekst 'running' bo'lsa true qaytaradi (ya'ni texnik jihatdan ovoz chiqdi).
export async function playTest() {
  const c = getCtx()
  if (!c) return false
  try {
    if (c.state !== 'running') await c.resume()
  } catch { /* pastda holatni tekshiramiz */ }
  if (c.state !== 'running') { emit(); return false }
  beep(c, 880, 0, 0.25, 0.35)
  beep(c, 1175, 0.3, 0.4, 0.35)
  emit()
  return true
}

// Yangi buyurtma bildirishnoma ovozi (Orders poll'idan chaqiriladi).
// Umumiy, ochilgan kontekstni ishlatadi — kontekst tayyor bo'lmasa jim qoladi.
export function playNotification() {
  const c = getCtx()
  if (!c || c.state !== 'running') return false
  beep(c, 880, 0, 0.3)
  beep(c, 660, 0.35, 0.3)
  beep(c, 880, 0.7, 0.4)
  beep(c, 988, 1.2, 0.3)
  beep(c, 784, 1.55, 0.3)
  beep(c, 988, 1.9, 0.5)
  return true
}
