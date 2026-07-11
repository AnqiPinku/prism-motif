import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Dev: Vite on 5173 proxies /api to the running gateway (8770).
// Build: emits static assets into ../web, which the gateway serves in production.
// Dev auth: start the gateway and Vite with the same PRISM_SESSION_TOKEN; the proxy
// injects the session header only for the dev page's own requests (token never
// reaches browser JS) and strips the same-origin Origin. Foreign Origins are
// forwarded untouched so the gateway still rejects them.
const devToken = process.env.PRISM_SESSION_TOKEN || ''
const devOrigins = new Set(['http://localhost:5173', 'http://127.0.0.1:5173'])

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: '/',
  build: { outDir: '../web', emptyOutDir: false, assetsDir: 'assets' },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8770',
        changeOrigin: true,
        configure(proxy) {
          proxy.on('proxyReq', (proxyReq, req) => {
            const origin = req.headers.origin
            if (origin && !devOrigins.has(origin)) return
            proxyReq.removeHeader('origin')
            if (devToken) proxyReq.setHeader('X-Prism-Session', devToken)
          })
        },
      },
    },
  },
})
