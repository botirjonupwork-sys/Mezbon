import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_TARGET || 'http://localhost:8000'

  return {
    plugins: [react()],
    // restaurant.tursunboyev.com — alohida domen, root'dan serve qilinadi (/admin/ emas)
    base: '/',
    server: {
      port: 3000,
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
          secure: false,
          // Backend /api prefiksisiz ishlaydi — prod'da nginx tomonidan strip qilinadi
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
        '/static': {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
  }
})
