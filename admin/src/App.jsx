import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store/auth'
import AdminLayout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Orders from './pages/Orders'
import Menu from './pages/Menu'
import Users from './pages/Users'
import Reviews from './pages/Reviews'
import Settings from './pages/Settings'
import Admins from './pages/Admins'
import Couriers from './pages/Couriers'

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
          <Route path="menu" element={<Menu />} />
          <Route path="users" element={<Users />} />
          <Route path="reviews" element={<Reviews />} />
          <Route path="settings" element={<Settings />} />
          <Route path="couriers" element={<Couriers />} />
          <Route path="admins" element={<Admins />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
