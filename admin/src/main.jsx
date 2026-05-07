import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider } from 'antd'
import uzUZ from 'antd/locale/uz_UZ'
import App from './App'
import './index.css'

// Vaqt mintaqasi — server UTC, foydalanuvchi Asia/Tashkent
import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import timezone from 'dayjs/plugin/timezone'
dayjs.extend(utc)
dayjs.extend(timezone)
dayjs.tz.setDefault('Asia/Tashkent')

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ConfigProvider locale={uzUZ} theme={{ token: { colorPrimary: '#fa8c16' } }}>
      <App />
    </ConfigProvider>
  </React.StrictMode>
)
