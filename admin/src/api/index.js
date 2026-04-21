import axios from 'axios'
import { useAuthStore } from '../store/auth'

const API_BASE = import.meta.env.VITE_API_URL || '/api'
const api = axios.create({ baseURL: API_BASE })

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
export const getReviewStats = (params) => api.get('/reviews/stats', { params })

// ── Orders ────────────────────────────────────────────
export const getOrders = (params) => api.get('/admin/orders', { params })
export const updateOrderStatus = (id, status) =>
  api.patch(`/orders/${id}/status`, null, { params: { status } })

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

// ── Profile ──────────────────────────────────────────
export const getProfile = (params) => api.get('/admin/profile', { params })
export const updateProfile = (data, params) => api.put('/admin/profile', data, { params })

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
export const getCateringOrders = (params) => api.get('/admin/orders', { params: { ...params, order_kind: 'catering' } })

// ── Branches ──────────────────────────────────────────
export const getAdminBranches = (params) => api.get('/admin/branches', { params })
export const getBranchSettings = (branchId) => api.get(`/admin/branches/${branchId}/settings`)
export const updateBranchSettings = (branchId, data) => api.put(`/admin/branches/${branchId}/settings`, data)
