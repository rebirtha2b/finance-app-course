import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    // FastAPI serves this directory as static files in production.
    outDir: 'dist',
  },
  server: {
    port: 5173,
    proxy: {
      // In dev the SPA runs on :5173 and the API on :8000; proxying keeps the
      // frontend code using same-origin relative URLs in both modes.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
