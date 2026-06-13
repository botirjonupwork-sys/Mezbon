import { useEffect, useRef, useCallback } from 'react'
import { Input, Typography } from 'antd'
import { EnvironmentOutlined } from '@ant-design/icons'

const { Text } = Typography

// Yandex xarita orqali joy tanlash + manzilni avtomatik aniqlash (Nominatim).
// onChange({ lat, lon, address }) chaqiriladi. Qo'lda manzil kiritilmaydi.
export default function LocationPicker({ lat, lon, address, onChange, height = 260 }) {
  const mapRef = useRef(null)
  const mapInstance = useRef(null)
  const markerRef = useRef(null)
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange

  const emit = useCallback(async (la, lo) => {
    const r = (v) => Math.round(v * 10000) / 10000
    const rla = r(la), rlo = r(lo)
    let addr = ''
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/reverse?format=json&lat=${rla}&lon=${rlo}&accept-language=uz,ru`
      )
      const d = await res.json()
      addr = (d && d.display_name) || ''
    } catch { /* manzil aniqlanmadi — koordinata baribir saqlanadi */ }
    onChangeRef.current?.({ lat: rla, lon: rlo, address: addr })
  }, [])

  const initMap = useCallback(() => {
    if (!window.ymaps || mapInstance.current || !mapRef.current) return
    window.ymaps.ready(() => {
      if (mapInstance.current || !mapRef.current) return
      const center = [lat || 41.2995, lon || 69.2401]
      const map = new window.ymaps.Map(mapRef.current, {
        center, zoom: 14, controls: ['zoomControl', 'searchControl', 'geolocationControl'],
      })
      const pm = new window.ymaps.Placemark(center, {}, { preset: 'islands#redFoodIcon', draggable: true })
      pm.events.add('dragend', () => {
        const c = pm.geometry.getCoordinates(); emit(c[0], c[1])
      })
      map.events.add('click', (e) => {
        const c = e.get('coords'); pm.geometry.setCoordinates(c); emit(c[0], c[1])
      })
      map.geoObjects.add(pm)
      mapInstance.current = map
      markerRef.current = pm
    })
  }, [lat, lon, emit])

  useEffect(() => {
    if (window.ymaps) { initMap(); return }
    let s = document.querySelector('script[data-ymaps]')
    if (!s) {
      s = document.createElement('script')
      s.src = 'https://api-maps.yandex.ru/2.1/?apikey=&lang=ru_RU'
      s.setAttribute('data-ymaps', '1')
      document.head.appendChild(s)
    }
    s.addEventListener('load', initMap)
    return () => s.removeEventListener('load', initMap)
  }, [initMap])

  useEffect(() => {
    if (markerRef.current && lat && lon) {
      markerRef.current.geometry.setCoordinates([lat, lon])
      mapInstance.current?.setCenter([lat, lon])
    }
  }, [lat, lon])

  return (
    <div>
      <div
        ref={mapRef}
        style={{ width: '100%', height, borderRadius: 12, overflow: 'hidden', border: '1px solid #e8e8e8' }}
      />
      <Input
        style={{ marginTop: 12 }}
        prefix={<EnvironmentOutlined style={{ color: '#bfbfbf' }} />}
        value={address || ''}
        readOnly
        placeholder="Xaritadan joyni tanlang — manzil shu yerda chiqadi"
      />
      <Text type="secondary" style={{ fontSize: 12 }}>
        Manzil xaritadan avtomatik aniqlanadi
      </Text>
    </div>
  )
}
