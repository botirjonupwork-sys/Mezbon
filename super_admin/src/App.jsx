import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import { useAuthStore } from './store/auth'
import Login from './pages/Login'
import SuperLayout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Restaurants from './pages/Restaurants'
import RestaurantForm from './pages/RestaurantForm'
import Settings from './pages/Settings'
import Bots from './pages/Bots'
import Tariffs from './pages/Tariffs'
import Finance from './pages/Finance'
import Analytics from './pages/Analytics'
import GlobalSettings from './pages/GlobalSettings'

function PrivateRoute({ children }) {
  const isAuth = useAuthStore((s) => s.isAuth)
  return isAuth ? children : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <ConfigProvider theme={{ token: { colorPrimary: '#722ed1' } }}>
      <BrowserRouter basename={import.meta.env.BASE_URL}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <PrivateRoute>
                <SuperLayout />
              </PrivateRoute>
            }
          >
            <Route index element={<Dashboard />} />
            <Route path="restaurants" element={<Restaurants />} />
            <Route path="restaurants/new" element={<RestaurantForm />} />
            <Route path="restaurants/:id/edit" element={<RestaurantForm />} />
            <Route path="settings" element={<Settings />} />
            <Route path="bots" element={<Bots />} />
            <Route path="tariffs" element={<Tariffs />} />
            <Route path="global" element={<GlobalSettings />} />
            <Route path="finance" element={<Finance />} />
            <Route path="analytics" element={<Analytics />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  )
}
