import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export const useAuthStore = create(
  persist(
    (set) => ({
      token: null,
      admin: null,
      isAuth: false,
      restaurantId: null,
      setAuth: (token, admin, restaurantId) =>
        set({ token, admin, isAuth: true, restaurantId }),
      logout: () =>
        set({ token: null, admin: null, isAuth: false, restaurantId: null }),
    }),
    { name: 'admin-auth' }
  )
)
