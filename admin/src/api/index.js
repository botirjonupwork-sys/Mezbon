import axios from 'axios'
import { useAuthStore } from '../store/auth'

const api = axios.create({ baseURL: '/api' })

// Token ni har so'rovga qo'shish
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

// ── Dashboard / Stats ─────────────────────────────────
export const getStats = (params) => api.get('/admin/stats', { params })
export const getReviewStats = () => api.get('/reviews/stats')

// ── Orders ────────────────────────────────────────────
export const getOrders = (params) => api.get('/admin/orders', { params })
export const updateOrderStatus = (id, status) =>
  api.patch(`/orders/${id}/status`, null, { params: { status } })

// ── Menu ─────────────────────────────────────────────
export const getCategories = () => api.get('/admin/categories')
export const getProducts = () => api.get('/admin/products')
export const toggleStop = (id, is_stop) =>
  api.patch(`/menu/products/${id}/stop`, null, { params: { is_stop } })
export const createProduct = (data) => api.post('/admin/products', data)
export const updateProduct = (id, data) => api.put(`/admin/products/${id}`, data)
export const deleteProduct = (id) => api.delete(`/admin/products/${id}`)
export const createCategory = (data) => api.post('/admin/categories', data)
export const uploadImage = (file) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/admin/upload-image', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

// ── Users ─────────────────────────────────────────────
export const getUsers = () => api.get('/admin/users')
export const getUserOrders = (userId) => api.get(`/admin/users/${userId}/orders`)

// ── Reviews ───────────────────────────────────────────
export const getReviews = () => api.get('/reviews')

// ── Settings ──────────────────────────────────────────
export const getSettings = () => api.get('/admin/settings')
export const updateSettings = (data) => api.put('/admin/settings', data)

// ── Profile ──────────────────────────────────────────
export const getProfile = () => api.get('/admin/profile')
export const updateProfile = (data) => api.put('/admin/profile', data)

// ── Couriers ──────────────────────────────────────────
export const getCouriers = () => api.get('/couriers/')
export const updateCourierStatus = (id, status) =>
  api.patch(`/couriers/${id}/status`, null, { params: { status } })

// ── Admins ────────────────────────────────────────────
export const getAdmins = () => api.get('/admin/admins')
export const createAdmin = (data) => api.post('/admin/admins', data)
export const deleteAdmin = (id) => api.delete(`/admin/admins/${id}`)
