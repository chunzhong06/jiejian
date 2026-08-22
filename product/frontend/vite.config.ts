import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  cacheDir: '../../var/cache/vite',
  server: { port: 5173, strictPort: true },
  test: { environment: 'jsdom', setupFiles: './src/test-setup.ts' },
})
