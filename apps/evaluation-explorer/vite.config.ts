import { fileURLToPath, URL } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const app = fileURLToPath(new URL('.', import.meta.url))
const architectureMap = fileURLToPath(new URL('../../packages/architecture-map', import.meta.url))

export default defineConfig({
  plugins: [react()],
  base: './',
  resolve: {
    // The shared map has no node_modules of its own, so React has to resolve
    // from this app. Subpaths are listed before the bare name because Vite
    // matches string aliases by prefix.
    alias: {
      '@linger/architecture-map/src': `${architectureMap}/src`,
      '@linger/architecture-map': `${architectureMap}/src/index.ts`,
      'react/jsx-dev-runtime': `${app}node_modules/react/jsx-dev-runtime`,
      'react/jsx-runtime': `${app}node_modules/react/jsx-runtime`,
      'react-dom/client': `${app}node_modules/react-dom/client`,
      'react-dom': `${app}node_modules/react-dom`,
      react: `${app}node_modules/react`,
    },
  },
  // The shared map lives outside this app's root, so the dev server has to be
  // allowed to read it and Vitest has to be told where its tests are.
  server: { fs: { allow: [app, architectureMap] } },
  test: {
    include: ['src/**/*.test.{ts,tsx}', '../../packages/architecture-map/src/**/*.test.{ts,tsx}'],
  },
})
