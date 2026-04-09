import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            return undefined
          }
          if (id.includes('@mui/icons-material')) {
            return 'mui-icons'
          }
          if (id.includes('@mui/material') || id.includes('@emotion/')) {
            return 'mui-core'
          }
          if (id.includes('react') || id.includes('scheduler')) {
            return 'react-vendor'
          }
          return 'vendor'
        },
      },
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
