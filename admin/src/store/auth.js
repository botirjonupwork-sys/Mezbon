import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export const useAuthStore = create(
  persist(
    (set) => ({
      token: null,
      admin: null,
      isAuth: false,
      setAuth: (token, admin) => set({ token, admin, isAuth: true }),
      logout: () => set({ token: null, admin: null, isAuth: false }),
    }),
    { name: 'admin-auth' }
  )
)
