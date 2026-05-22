import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store/auth'
import AdminLayout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Orders from './pages/Orders'
import Menu from './pages/Menu'
import Users from './pages/Users'
import Reviews from './pages/Reviews'
import Admins from './pages/Admins'
import Couriers from './pages/Couriers'
import Billing from './pages/Billing'
import Settlement from './pages/Settlement'
import Catering from './pages/Catering'
import Branches from './pages/Branches'

// Settings pages
import SettingsIndex from './pages/settings/index'
import SettingsRestaurant from './pages/settings/Restaurant'
import SettingsPayments from './pages/settings/Payments'
import SettingsDelivery from './pages/settings/Delivery'
import SettingsBots from './pages/settings/Bots'
import SettingsCatering from './pages/settings/Catering'
import SettingsProfile from './pages/settings/Profile'

function PrivateRoute({ children }) {
  const isAuth = useAuthStore((s) => s.isAuth)
  return isAuth ? children : <Navigate to="/login" />
}

export default function App() {
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={
            <PrivateRoute>
              <AdminLayout />
            </PrivateRoute>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="orders" element={<Orders />} />
          <Route path="catering" element={<Catering />} />
          <Route path="branches" element={<Branches />} />
          <Route path="menu" element={<Menu />} />
          <Route path="users" element={<Users />} />
          <Route path="reviews" element={<Reviews />} />
          <Route path="settings" element={<SettingsIndex />} />
          <Route path="settings/restaurant" element={<SettingsRestaurant />} />
          <Route path="settings/payments" element={<SettingsPayments />} />
          <Route path="settings/delivery" element={<SettingsDelivery />} />
          <Route path="settings/bots" element={<SettingsBots />} />
          <Route path="settings/catering" element={<SettingsCatering />} />
          <Route path="settings/profile" element={<SettingsProfile />} />
          <Route path="couriers" element={<Couriers />} />
          <Route path="admins" element={<Admins />} />
          <Route path="billing" element={<Billing />} />
          <Route path="settlement" element={<Settlement />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
