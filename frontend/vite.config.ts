import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Dev: Vite on 5173 proxies /api to the running gateway (8770).
// Build: emits static assets into ../web, which the gateway serves in production.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: '/',
  build: { outDir: '../web', emptyOutDir: false, assetsDir: 'assets' },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8770', changeOrigin: true },
    },
  },
})
