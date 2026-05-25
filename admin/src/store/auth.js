import { create } from 'zustand'
import { persist } from 'zustand/middleware'

/**
 * Auth store.
 *
 * Token endi HttpOnly cookie'da saqlanadi (XSS himoyasi). localStorage'da
 * faqat UI state'lar bor: admin info, restaurant_id, tanlangan restaurant.
 *
 * Backward compat: agar localStorage'da eski `token` bo'lsa, axios uni Bearer
 * header'da yuboradi. Yangi login'lar cookie orqali ishlaydi va token
 * localStorage'ga yozilmaydi.
 *
 * - `restaurantId` — login paytida olingan rid (super uchun null, immutable).
 * - `currentRestaurantId` — joriy tanlangan rid (super uchun Layout'dan tanlaydi).
 *   Restaurant admin uchun har doim restaurantId'ga teng.
 *   Sahifalar shu qiymatdan foydalanadi (yagona manba).
 */
export const useAuthStore = create(
  persist(
    (set, get) => ({
      token: null,       // [LEGACY] yangi sessiyalar bunga yozmaydi; eski sessiyalar bor
      admin: null,
      isAuth: false,
      restaurantId: null,
      currentRestaurantId: null,

      // Login muvaffaqiyatli bo'lganda chaqiriladi.
      // Token endi cookie'da; UI state'ni o'rnatamiz.
      setAuth: (token, admin, restaurantId) =>
        set({
          // Backward compat: agar backend hali ham token qaytarsa, saqlaymiz.
          // Yangi flow'da token=null bo'ladi (cookie ishlatiladi).
          token: token || null,
          admin,
          isAuth: true,
          restaurantId,
          currentRestaurantId: restaurantId,
        }),

      // Faqat super-admin (restaurantId == null) bu funksiya orqali rid tanlay oladi
      setCurrentRestaurant: (rid) => {
        const { restaurantId } = get()
        if (restaurantId !== null && rid !== restaurantId) return
        set({ currentRestaurantId: rid })
      },

      logout: () => {
        // Cookie'ni serverga aytamiz tozalashga (HttpOnly bo'lgani uchun JS o'zi tozalay olmaydi)
        try {
          fetch((import.meta.env.VITE_API_URL || '/api') + '/auth/logout', {
            method: 'POST',
            credentials: 'include',
          }).catch(() => {})
        } catch {}
        set({
          token: null, admin: null, isAuth: false,
          restaurantId: null, currentRestaurantId: null,
        })
      },
    }),
    {
      name: 'admin-auth',
      // token'ni endi persist qilmaymiz (cookie'da) — XSS himoyasi
      partialize: (state) => ({
        admin: state.admin,
        isAuth: state.isAuth,
        restaurantId: state.restaurantId,
        currentRestaurantId: state.currentRestaurantId,
        // token: state.token,  // qasddan persist qilinmaydi
      }),
    }
  )
)

export const useEffectiveRestaurantId = () =>
  useAuthStore((s) => s.currentRestaurantId)
