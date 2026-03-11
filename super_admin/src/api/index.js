import axios from 'axios'
import { useAuthStore } from '../store/auth'

const api = axios.create({ baseURL: '/api' })

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
export const getStats = () => api.get('/super/stats')
export const getRestaurants = () => api.get('/super/restaurants')
export const getRestaurant = (id) => api.get(`/super/restaurants/${id}`)
export const createRestaurant = (data) => api.post('/super/restaurants', data)
export const updateRestaurant = (id, data) => api.put(`/super/restaurants/${id}`, data)
export const deleteRestaurant = (id) => api.delete(`/super/restaurants/${id}`)

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
