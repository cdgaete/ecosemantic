import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import * as path from 'node:path'
import * as url from 'node:url'

const here = path.dirname(url.fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(here, './src') } },
  test: { environment: 'jsdom', globals: true, include: ['tests/**/*.test.{ts,tsx}'], setupFiles: ['tests/setup.ts'] },
})
