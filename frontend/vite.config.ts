import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // dev-only: proxies /api to the FastAPI backend so the frontend never
    // needs CORS or an absolute URL. In prod, main.py serves both from one
    // origin (ai-plan.md §10), so the same relative /api path just works.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
