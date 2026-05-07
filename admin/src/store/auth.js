import { create } from 'zustand'
import { persist } from 'zustand/middleware'

/**
 * Auth store.
 *
 * - `restaurantId` — login paytida olingan rid (super uchun null, immutable).
 * - `currentRestaurantId` — joriy tanlangan rid (super uchun Layout'dan tanlaydi).
 *   Restaurant admin uchun har doim restaurantId'ga teng.
 *   Sahifalar shu qiymatdan foydalanadi (yagona manba).
 */
export const useAuthStore = create(
  persist(
    (set, get) => ({
      token: null,
      admin: null,
      isAuth: false,
      restaurantId: null,
      currentRestaurantId: null,

      setAuth: (token, admin, restaurantId) =>
        set({
          token, admin, isAuth: true, restaurantId,
          currentRestaurantId: restaurantId,
        }),

      // Faqat super-admin (restaurantId == null) bu funksiya orqali rid tanlay oladi
      setCurrentRestaurant: (rid) => {
        const { restaurantId } = get()
        if (restaurantId !== null && rid !== restaurantId) return
        set({ currentRestaurantId: rid })
      },

      logout: () =>
        set({
          token: null, admin: null, isAuth: false,
          restaurantId: null, currentRestaurantId: null,
        }),
    }),
    { name: 'admin-auth' }
  )
)

export const useEffectiveRestaurantId = () =>
  useAuthStore((s) => s.currentRestaurantId)
