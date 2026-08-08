import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Proxy API calls to the FastAPI backend so the browser sees a single
    // origin in development and CORS never comes into play.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
