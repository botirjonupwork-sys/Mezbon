import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export const useAuthStore = create(
  persist(
    (set) => ({
      token: null,
      isAuth: false,
      setAuth: (token) => set({ token, isAuth: true }),
      logout: () => set({ token: null, isAuth: false }),
    }),
    { name: 'super-admin-auth' }
  )
)
