import { useEffect, useRef, useCallback, useState } from 'react'
import { Input, Typography, Button, Space, message } from 'antd'
import { EnvironmentOutlined, CompassOutlined } from '@ant-design/icons'

const { Text } = Typography

/**
 * Yandex xarita orqali joy tanlash + manzilni avtomatik aniqlash (Nominatim).
 * Standart Yandex Maps 2.1 API asosida ishlaydi.
 *
 * Props:
 *  - lat, lon: joriy koordinatalar
 *  - address: manzil matni
 *  - onChange({ lat, lon, address }): qiymat o'zgarganda chaqiriladi
 *  - height: xarita balandligi (px)
 */
export default function LocationPicker({ lat, lon, address, onChange, height = 240 }) {
  const mapRef = useRef(null)
  const mapInstance = useRef(null)
  const markerRef = useRef(null)
  const [locating, setLocating] = useState(false)
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange

  const emit = useCallback(async (la, lo) => {
    const r = (v) => Math.round(v * 1000000) / 1000000
    const rla = r(la), rlo = r(lo)
    let addr = ''
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/reverse?format=json&lat=${rla}&lon=${rlo}&accept-language=uz,ru`
      )
      const d = await res.json()
      addr = (d && d.display_name) || ''
    } catch {
      /* manzil aniqlanmadi — koordinata baribir saqlanadi */
    }
    onChangeRef.current?.({ lat: rla, lon: rlo, address: addr })
  }, [])

  const initMap = useCallback(() => {
    if (!window.ymaps || mapInstance.current || !mapRef.current) return
    window.ymaps.ready(() => {
      if (mapInstance.current || !mapRef.current) return
      const center = [lat || 41.2995, lon || 69.2401]
      const map = new window.ymaps.Map(mapRef.current, {
        center,
        zoom: 14,
        controls: ['zoomControl', 'searchControl', 'geolocationControl'],
      })
      const pm = new window.ymaps.Placemark(
        center,
        {},
        { preset: 'islands#redFoodIcon', draggable: true }
      )
      pm.events.add('dragend', () => {
        const c = pm.geometry.getCoordinates()
        emit(c[0], c[1])
      })
      map.events.add('click', (e) => {
        const c = e.get('coords')
        pm.geometry.setCoordinates(c)
        emit(c[0], c[1])
      })
      map.geoObjects.add(pm)
      mapInstance.current = map
      markerRef.current = pm
    })
  }, [lat, lon, emit])

  useEffect(() => {
    if (window.ymaps) {
      initMap()
      return
    }
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

  // Joriy joylashuvni olish
  const handleCurrentLocation = () => {
    if (!navigator.geolocation) {
      message.warning("Brauzeringiz geolokatsiyani qo'llab-quvvatlamaydi")
      return
    }
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false)
        const curLat = Math.round(pos.coords.latitude * 1000000) / 1000000
        const curLon = Math.round(pos.coords.longitude * 1000000) / 1000000
        if (markerRef.current) {
          markerRef.current.geometry.setCoordinates([curLat, curLon])
        }
        if (mapInstance.current) {
          mapInstance.current.setCenter([curLat, curLon], 16)
        }
        emit(curLat, curLon)
        message.success(`Joylashuv aniqlandi: ${curLat}, ${curLon}`)
      },
      (err) => {
        setLocating(false)
        message.error("Joylashuvni aniqlab bo'lmadi: " + err.message)
      },
      { enableHighAccuracy: true, timeout: 10000 }
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <Text strong style={{ fontSize: 13 }}>
          <EnvironmentOutlined style={{ color: '#ff4d4f', marginRight: 4 }} />
          Xaritadan joyni belgilang (Markerni siljiting):
        </Text>
        <Button
          size="small"
          type="primary"
          ghost
          icon={<CompassOutlined />}
          loading={locating}
          onClick={handleCurrentLocation}
          style={{ borderRadius: 6 }}
        >
          Joriy joylashuv
        </Button>
      </div>

      <div
        ref={mapRef}
        style={{
          width: '100%',
          height,
          borderRadius: 8,
          overflow: 'hidden',
          border: '1px solid #d9d9d9',
        }}
      />

      <Input
        style={{ marginTop: 8 }}
        prefix={<EnvironmentOutlined style={{ color: '#bfbfbf' }} />}
        value={address || ''}
        readOnly
        placeholder="Xaritada nuqta tanlansa manzil avtomatik aniqlanadi"
      />
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {lat && lon ? `Koordinatalar: ${lat}, ${lon}` : "Koordinata tanlanmagan"}
        </Text>
        <Text type="secondary" style={{ fontSize: 11 }}>
          Yandex Maps 2.1
        </Text>
      </div>
    </div>
  )
}

