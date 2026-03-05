import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider } from 'antd'
import uzUZ from 'antd/locale/uz_UZ'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ConfigProvider locale={uzUZ} theme={{ token: { colorPrimary: '#fa8c16' } }}>
      <App />
    </ConfigProvider>
  </React.StrictMode>
)
