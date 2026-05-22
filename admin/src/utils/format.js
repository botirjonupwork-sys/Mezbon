// Raqamlarni 3 xonali ajratib ko'rsatish — "200000" → "200 000"
// InputNumber komponentida formatter/parser sifatida ishlatiladi
export const moneyFormatter = (v) => {
  if (v === null || v === undefined || v === '') return ''
  return `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ' ')
}

export const moneyParser = (v) => (v || '').replace(/[\s,]/g, '')

// Display only (chiplar, tag, badge uchun)
export const fmtMoney = (n) => {
  if (n === null || n === undefined || n === '') return '—'
  return Number(n).toLocaleString('ru-RU').replace(/,/g, ' ')
}
