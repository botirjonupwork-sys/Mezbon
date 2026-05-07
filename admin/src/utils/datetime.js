// Vaqt formatlash — server UTC datetimelarni Tashkent vaqtiga aylantirish.
//
// Backend (FastAPI/SQLAlchemy) `datetime.utcnow()` ishlatadi va naive datetime
// qaytaradi (UTC, lekin "Z" suffix yo'q). JavaScript bunday string'ni LOCAL
// time deb interpretatsiya qiladi → noto'g'ri vaqt.
//
// Yechim: dayjs.utc(v) bilan UTC deb tushunamiz, keyin Tashkent timezone'iga
// aylantiramiz.
import dayjs from 'dayjs'

const TZ = 'Asia/Tashkent'

/** UTC ISO string'ni Tashkent vaqtida formatlaydi. */
export function fmtTashkent(value, format = 'DD.MM.YYYY HH:mm') {
  if (!value) return '—'
  return dayjs.utc(value).tz(TZ).format(format)
}

/** Faqat sana (kunlik). */
export function fmtDateOnly(value, format = 'DD.MM.YYYY') {
  if (!value) return '—'
  return dayjs.utc(value).tz(TZ).format(format)
}

/** Faqat vaqt (HH:mm). */
export function fmtTimeOnly(value, format = 'HH:mm') {
  if (!value) return '—'
  return dayjs.utc(value).tz(TZ).format(format)
}

/** "5 daqiqa oldin" tipidagi nisbiy vaqt (kelajakda — `relativeTime` plugin). */
export function fmtRelative(value) {
  if (!value) return '—'
  const d = dayjs.utc(value).tz(TZ)
  const now = dayjs().tz(TZ)
  const diff = now.diff(d, 'minute')
  if (diff < 1) return 'hozirgina'
  if (diff < 60) return `${diff} daq oldin`
  if (diff < 1440) return `${Math.floor(diff / 60)} soat oldin`
  return d.format('DD.MM HH:mm')
}
