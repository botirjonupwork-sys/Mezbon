import axios from 'axios'
import { useAuthStore } from '../store/auth'

const API_BASE = import.meta.env.VITE_API_URL || '/api'
// withCredentials=true: brauzer HttpOnly cookie'ni avtomatik yuboradi.
// Auth endi cookie orqali ishlaydi (XSS himoyasi). Backward compat uchun
// localStorage'dagi eski tokenni ham Bearer'da yuboramiz (asta-sekin chiqib ketadi).
const api = axios.create({ baseURL: API_BASE, withCredentials: true })

// Token ni har so'rovga qo'shish (eski sessiyalar uchun)
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 401 — logout
api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) useAuthStore.getState().logout()
    return Promise.reject(err)
  }
)

// ── Auth ──────────────────────────────────────────────
export const login = (data) => api.post('/auth/login', data)
export const logoutServer = () => api.post('/auth/logout')
export const checkAuth = () => api.get('/auth/me')

// ── Dashboard / Stats ─────────────────────────────────
export const getStats = (params) => api.get('/admin/stats', { params })
export const getReviewStats = (params) => api.get('/reviews/stats', { params })

// ── Orders ────────────────────────────────────────────
export const getOrders = (params) => api.get('/admin/orders', { params })
export const updateOrderStatus = (id, status) =>
  api.patch(`/orders/${id}/status`, null, { params: { status } })
export const refundOrder = (orderId, reason = '', amount_tiyin = null, apply_policy = true) =>
  api.post(`/admin/orders/${orderId}/refund`, { order_id: orderId, reason, amount_tiyin, apply_policy }).then(r => r.data)
export const getRefunds = (params) => api.get('/admin/refunds', { params }).then(r => r.data)

// ── Menu ─────────────────────────────────────────────
export const getCategories = (params) => api.get('/admin/categories', { params })
export const getProducts = (params) => api.get('/admin/products', { params })
export const toggleStop = (id, is_stop) =>
  api.patch(`/menu/products/${id}/stop`, null, { params: { is_stop } })
export const createProduct = (data, params) => api.post('/admin/products', data, { params })
export const updateProduct = (id, data, params) => api.put(`/admin/products/${id}`, data, { params })
export const deleteProduct = (id) => api.delete(`/admin/products/${id}`)
export const createCategory = (data, params) => api.post('/admin/categories', data, { params })
export const updateCategory = (id, data) => api.put(`/admin/categories/${id}`, data)
export const deleteCategory = (id) => api.delete(`/admin/categories/${id}`)
export const uploadImage = (file) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/admin/upload-image', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}
export const deleteImage = (url) => api.delete('/admin/upload-image', { params: { url } })

// ── Users ─────────────────────────────────────────────
export const getUsers = (params) => api.get('/admin/users', { params })
export const getUserOrders = (userId) => api.get(`/admin/users/${userId}/orders`)

// ── Reviews ───────────────────────────────────────────
export const getReviews = (params) => api.get('/reviews', { params })

// ── Settings ──────────────────────────────────────────
export const getSettings = (params) => api.get('/admin/settings', { params })
export const updateSettings = (data, params) => api.put('/admin/settings', data, { params })
export const getYandexBalance = (params) => api.get('/admin/yandex-balance', { params })
export const checkYandexBalanceNow = (params) => api.post('/admin/yandex-balance/check-now', null, { params })

// ── Profile ──────────────────────────────────────────
export const getProfile = (params) => api.get('/admin/profile', { params })
export const getMyPlan = (params) => api.get('/admin/me/plan', { params })

// ── Billing ───────────────────────────────────────────
export const getBillingPlans = (params) => api.get('/admin/billing/plans', { params })
export const getBillingPayments = (params) => api.get('/admin/billing/payments', { params })
export const getBillingStatus = (params) => api.get('/admin/billing/status', { params })
export const getSettlement = (params) => api.get('/admin/billing/settlement', { params }).then(r => r.data)
export const getSettlementCsvUrl = (params) => {
  const qs = new URLSearchParams(params || {}).toString()
  return `/api/admin/billing/settlement.csv${qs ? '?' + qs : ''}`
}
export const upgradeBillingPlan = (data, params) => api.post('/admin/billing/upgrade', data, { params })
export const createInvoice = (data, params) => api.post('/payments/create-invoice', data, { params })
export const mockCompletePayment = (merchantTransId, params) =>
  api.post('/payments/mock/complete', null, { params: { ...params, merchant_trans_id: merchantTransId } })
export const updateProfile = (data, params) => api.put('/admin/profile', data, { params })

// ── Autopay (Payme Subscribe) ─────────────────────────
export const getAutopayStatus = (params) => api.get('/admin/autopay/status', { params })
export const bindAutopayCard = (data, params) => api.post('/admin/autopay/card', data, { params })
export const verifyAutopayCard = (data, params) => api.post('/admin/autopay/verify', data, { params })
export const removeAutopayCard = (params) => api.delete('/admin/autopay/card', { params })
export const toggleAutopay = (data, params) => api.post('/admin/autopay/toggle', data, { params })

// ── Couriers ──────────────────────────────────────────
export const getCouriers = (params) => api.get('/couriers/', { params })
export const updateCourierStatus = (id, status) =>
  api.patch(`/couriers/${id}/status`, null, { params: { status } })
export const updateCourier = (id, data) => api.put(`/couriers/${id}`, data)
export const deleteCourier = (id) => api.delete(`/couriers/${id}`)

// ── Admins ────────────────────────────────────────────
export const getAdmins = (params) => api.get('/admin/admins', { params })
export const createAdmin = (data, params) => api.post('/admin/admins', data, { params })
export const deleteAdmin = (id) => api.delete(`/admin/admins/${id}`)

// ── Catering ──────────────────────────────────────────
export const getCateringProducts = (params) => api.get('/catering/products', { params })
export const getCurrencyRate = (params) => api.get('/catering/currency', { params })
export const getCateringOrders = (params) =>
  api.get('/admin/orders', { params: { order_kind: 'catering', limit: 500, ...(params || {}) } }).then(r => r.data)

// ── Branches ──────────────────────────────────────────
export const getAdminBranches = (params) => api.get('/admin/branches', { params })
export const getBranchSettings = (branchId) => api.get(`/admin/branches/${branchId}/settings`)
export const updateBranchSettings = (branchId, data) => api.put(`/admin/branches/${branchId}/settings`, data)
export const createAdminBranch = (data) => api.post('/admin/branches', data).then(r => r.data)

// ── POS / Printer ─────────────────────────────────────
export const getPOSConfig = (params) => api.get('/admin/pos/config', { params })
export const updatePOSConfig = (data, params) => api.put('/admin/pos/config', data, { params })
export const testPOSPrint = (params) => api.post('/admin/pos/test-print', null, { params })

// ── AI Operator ───────────────────────────────────────
export const getAiLogs = (params) => api.get('/ai/logs', { params })
export const getAiLogDetail = (id, params) => api.get(`/ai/logs/${id}`, { params })
export const getAiStats = (params) => api.get('/ai/stats', { params })
export const aiProcessCall = (data, params) => api.post('/ai/process-call', data, { params })

// ── Super Admin ───────────────────────────────────────
export const getSuperStats = (params) => api.get('/super-admin/stats', { params })
// Admin panelda super-admin restoran tanlashi uchun ham ishlatiladi
export const getSuperRestaurants = () => api.get('/super-admin/restaurants').catch(() => ({ data: [] }))
export const patchSuperRestaurant = (id, data) => api.patch(`/super-admin/restaurants/${id}`, data)
export const getMaintenance = () => api.get('/super-admin/maintenance')
export const setMaintenance = (data) => api.put('/super-admin/maintenance', data)
export const getSuperActions = (params) => api.get('/super-admin/actions', { params })
export const getHealth = () => api.get('/health')
