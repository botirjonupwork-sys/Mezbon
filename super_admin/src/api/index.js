import axios from 'axios'
import { useAuthStore } from '../store/auth'

// withCredentials=true: HttpOnly cookie auth (XSS himoyasi).
// Backward compat: localStorage'dagi eski token Bearer'da yuboriladi.
const api = axios.create({ baseURL: '/api', withCredentials: true })

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) useAuthStore.getState().logout()
    return Promise.reject(err)
  }
)

export const superLogin = (data) => api.post('/auth/super/login', data)
export const checkAuth = () => api.get('/auth/me')
export const logoutServer = () => api.post('/auth/logout')
export const getStats = () => api.get('/super/stats')
export const getRestaurants = () => api.get('/super/restaurants')
export const getRestaurant = (id) => api.get(`/super-admin/restaurants/${id}`)
export const createRestaurant = (data) => api.post('/super-admin/restaurants', data)
export const updateRestaurant = (id, data) => api.put(`/super-admin/restaurants/${id}/info`, data)
export const deleteRestaurant = (id) => api.delete(`/super-admin/restaurants/${id}`)

// ── Yangi super-admin endpointlari (Faza 5+) ──────────
export const getSuperAdminStats = (params) => api.get('/super-admin/stats', { params })
export const getSuperAdminRestaurants = () => api.get('/super-admin/restaurants')
export const patchSuperAdminRestaurant = (id, data) => api.patch(`/super-admin/restaurants/${id}`, data)
export const setRestaurantCredentials = (id, data) => api.put(`/super-admin/restaurants/${id}/credentials`, data).then(r => r.data)
export const updateRestaurantInfo = (id, data) => api.put(`/super-admin/restaurants/${id}/info`, data).then(r => r.data)
export const createSuperRestaurant = (data) => api.post('/super-admin/restaurants', data).then(r => r.data)
export const softDeleteRestaurant = (id) => api.delete(`/super-admin/restaurants/${id}`).then(r => r.data)
export const getMaintenance = () => api.get('/super-admin/maintenance')
export const setMaintenance = (data) => api.put('/super-admin/maintenance', data)
export const getSuperActions = (params) => api.get('/super-admin/actions', { params })
export const getFinanceSummary = (params) => api.get('/super-admin/finance/summary', { params }).then(r => r.data)
export const getFinanceCsvUrl = (params) => {
  const qs = new URLSearchParams(params || {}).toString()
  return `/api/super-admin/finance/summary.csv${qs ? '?' + qs : ''}`
}
export const getPaymentAnalytics = (params) => api.get('/super-admin/analytics/payments', { params }).then(r => r.data)
export const getWebhookMonitoring = (params) => api.get('/super-admin/monitoring/webhooks', { params }).then(r => r.data)
export const getHealth = () => api.get('/health')
export const getAiAggregateStats = (params) => api.get('/super-admin/ai-stats', { params })

// Profile
export const getSuperProfile = () => api.get('/super/profile')
export const updateSuperProfile = (data) => api.put('/super/profile', data)

// Platform settings
export const getPlatformSettings = () => api.get('/super/platform-settings')
export const updatePlatformSettings = (data) => api.put('/super/platform-settings', data)

// Commission
export const getCommissionSummary = () => api.get('/super/commission/summary')
export const getRestaurantCommission = (id) => api.get(`/super/commission/${id}`)
export const updateCommissionPercent = (id, percent) => api.put(`/super/commission/${id}/percent`, { commission_percent: percent })
export const markCommissionPaid = (id, note) => api.post(`/super/commission/${id}/mark-paid`, { note })
export const getCommissionHistory = (id) => api.get(`/super/commission/${id}/history`)
export const getPendingPayments = () => api.get('/super/commission/pending/all')
export const confirmPayment = (paymentId) => api.put(`/super/commission/payments/${paymentId}/confirm`)
export const rejectPayment = (paymentId) => api.put(`/super/commission/payments/${paymentId}/reject`)

// Bot boshqaruvi
export const getBotsStatus = () => api.get('/super/bots/status')
export const startBots = () => api.post('/super/bots/start')
export const stopBots = () => api.post('/super/bots/stop')
export const restartBots = () => api.post('/super/bots/restart')
export const restartBot = (restaurantId) => api.post(`/super/bots/${restaurantId}/restart`)

// Filiallar (Branches)
export const getBranches = (restaurantId) => api.get(`/super/restaurants/${restaurantId}/branches`)
export const createBranch = (restaurantId, data) => api.post(`/super/restaurants/${restaurantId}/branches`, data)
export const updateBranch = (branchId, data) => api.put(`/super/branches/${branchId}`, data)
export const deleteBranch = (branchId) => api.delete(`/super/branches/${branchId}`)

// Tariflar (Plans) CRUD
export const getPlans = () => api.get('/super/plans')
export const createPlan = (data) => api.post('/super/plans', data)
export const updatePlan = (id, data) => api.put(`/super/plans/${id}`, data)
export const deletePlan = (id) => api.delete(`/super/plans/${id}`)
