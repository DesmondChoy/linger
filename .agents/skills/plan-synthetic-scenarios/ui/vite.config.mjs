import path from 'node:path'
import { fileURLToPath } from 'node:url'

const uiRoot = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(uiRoot, '../../../../')
const frontendModules = path.join(repoRoot, 'apps/frontend/node_modules')

export default {
  root: uiRoot,
  base: './',
  build: {
    outDir: path.join(uiRoot, 'dist'),
    emptyOutDir: true,
  },
  resolve: {
    alias: [
      { find: /^react$/, replacement: path.join(frontendModules, 'react/index.js') },
      { find: /^react\/jsx-runtime$/, replacement: path.join(frontendModules, 'react/jsx-runtime.js') },
      { find: /^react-dom\/client$/, replacement: path.join(frontendModules, 'react-dom/client.js') },
    ],
  },
}
