import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  build: {
    emptyOutDir: true,
    outDir: process.env.JIEJIAN_FRONTEND_OUT_DIR || 'dist',
  },
  plugins: [react()],
  cacheDir: process.env.JIEJIAN_FRONTEND_CACHE_DIR || '.vite',
  server: { port: 5173, strictPort: true },
  test: { environment: 'jsdom', setupFiles: './src/test-setup.ts' },
})
