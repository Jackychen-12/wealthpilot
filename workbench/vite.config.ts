import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// 开发时把 /api 和 /health 代理到后端，页面与接口同源，不需要配 CORS。
const backend = process.env.WP_BACKEND || 'http://127.0.0.1:8000'

export default defineConfig({
  // 部署到子路径（如 GitHub Pages 的 /wealthpilot/）时用 WP_BASE 指定
  base: process.env.WP_BASE || '/',
  plugins: [tailwindcss(), react()],
  server: {
    port: Number(process.env.WP_PORT) || 5180,
    strictPort: true,
    proxy: {
      '/api': { target: backend, changeOrigin: true },
      '/health': { target: backend, changeOrigin: true },
    },
  },
})
