import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'
import fs from 'node:fs'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
const root = path.dirname(fileURLToPath(import.meta.url))
const desktop = path.resolve(root, '../desktop')
const require = createRequire(path.join(desktop, 'package.json'))
export default defineConfig({
  root,
  cacheDir: path.join(root, '.scratch/vite'),
  publicDir: path.join(desktop, 'public'),
  plugins: [react(), {
    name: 'browser-boundaries',
    // Must precede Tailwind's pre-transform: @source added afterwards is emitted
    // literally and leaves the shared renderer's utility classes undiscovered.
    // Resolve relative imports too: the original renderer remains read-only.
    enforce: 'pre',
    transform(code, id) {
      if (id.split('?')[0] === path.join(desktop, 'src/styles.css')) {
        return { code: `${code}\n@source "${path.join(desktop, 'src').replaceAll('\\', '/')}";\n`, map: null }
      }
    },
    resolveId(source, importer) {
      if (!importer) return
      const resolved = (source.startsWith('.') ? path.resolve(path.dirname(importer), source) : source).replace(/\.(tsx?|jsx?)$/, '')
      if (resolved === path.join(desktop, 'electron/power-save')) return path.join(root, 'src/power-save.ts')
      if (resolved === path.join(desktop, 'src/app/chat/right-rail/preview-pane')) return path.join(root, 'src/preview-pane.tsx')
      if (resolved === path.join(desktop, 'src/contrib/runtime-loader')) return path.join(root, 'src/runtime-loader.ts')
      if (resolved === path.join(desktop, 'src/app/settings/gateway-settings')) return path.join(root, 'src/gateway-settings.tsx')
      if (resolved === path.join(desktop, 'src/store/keep-awake')) return path.join(root, 'src/keep-awake.ts')
    },
    generateBundle() {
      const base = path.dirname(require.resolve('emojibase-data/package.json'))
      for (const file of ['en/data.json', 'en/messages.json', 'en/shortcodes/emojibase.json']) {
        this.emitFile({ type: 'asset', fileName: `emojibase/${file}`, source: fs.readFileSync(path.join(base, file)) })
      }
    }
  }, tailwindcss()],
  css: { postcss: { plugins: [] } },
  resolve: {
    alias: [
      { find: '@/debug/dev-only', replacement: path.join(root, 'src/noop.ts') },
      { find: '@/lib/gateway-ws-url', replacement: path.join(root, 'src/gateway-ws-url.ts') },
      { find: '@/app/chat/right-rail/preview-pane', replacement: path.join(root, 'src/preview-pane.tsx') },
      { find: '@/contrib/runtime-loader', replacement: path.join(root, 'src/runtime-loader.ts') },
      { find: '@/app/settings/gateway-settings', replacement: path.join(root, 'src/gateway-settings.tsx') },
      { find: '@/store/keep-awake', replacement: path.join(root, 'src/keep-awake.ts') },
      { find: '@hermes/plugin-sdk', replacement: path.join(desktop, 'src/sdk/index.ts') },
      { find: '@', replacement: path.join(desktop, 'src') },
      { find: '@hermes/shared/billing', replacement: path.resolve(root, '../shared/src/billing-types.ts') },
      { find: '@hermes/shared', replacement: path.resolve(root, '../shared/src') },
      { find: /^driver\.js\/dist\/driver\.js\.iife\.js(\?raw)?$/, replacement: path.join(path.dirname(require.resolve('driver.js')), 'driver.js.iife.js') + '$1' },
      { find: 'react', replacement: path.dirname(require.resolve('react/package.json')) },
      { find: 'react-dom', replacement: path.dirname(require.resolve('react-dom/package.json')) }
    ],
    dedupe: ['react', 'react-dom', 'react-router', '@tanstack/react-query']
  },
  build: { outDir: path.join(root, 'dist'), emptyOutDir: true, chunkSizeWarningLimit: 25000,
    rolldownOptions: { output: { advancedChunks: { groups: [
      { name: 'vendor-react', test: /node_modules\/(react|react-dom|scheduler|react-router|@tanstack\/react-query)\// },
      { name: 'shiki', test: /node_modules\/(shiki|@shikijs|react-shiki|@streamdown\/code)\// },
      { name: 'mermaid', test: /node_modules\/(mermaid|cytoscape|dagre|@mermaid-js)\// }
    ] } } } },
  server: { host: '127.0.0.1', port: 5175, fs: { allow: [path.resolve(root, '../..')] } }
})
