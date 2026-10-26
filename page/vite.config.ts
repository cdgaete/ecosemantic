import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import * as path from 'node:path'
import * as url from 'node:url'

const here = path.dirname(url.fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(here, './src') } },
  base: '/',
  build: {
    outDir: path.resolve(here, '../view/ecosemantic/view/static'),
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          graph: ['@xyflow/react'],
        },
      },
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: process.env.ECOSEMANTIC_VIEW_ORIGIN ?? 'http://127.0.0.1:8765', changeOrigin: true },
    },
  },
})
