import { create } from 'zustand'
import { persist } from 'zustand/middleware'

/**
 * Super-admin auth store. Token endi HttpOnly cookie'da (XSS himoyasi).
 * localStorage'da faqat isAuth flag bor (UI uchun).
 */
export const useAuthStore = create(
  persist(
    (set) => ({
      token: null,       // [LEGACY] eski sessiyalar uchun, yangi sessiyalar bunga yozmaydi
      isAuth: false,
      setAuth: (token) => set({ token: token || null, isAuth: true }),
      logout: () => {
        // HttpOnly cookie'ni serverga aytamiz tozalashga
        try {
          fetch('/api/auth/logout', { method: 'POST', credentials: 'include' }).catch(() => {})
        } catch {}
        set({ token: null, isAuth: false })
      },
    }),
    {
      name: 'super-admin-auth',
      partialize: (state) => ({ isAuth: state.isAuth }),
    }
  )
)
