import { mergeConfig, defineConfig } from 'vitest/config'
import vite from './vite.config.ts'
export default mergeConfig(vite, defineConfig({ test: {
  include: ['tests/*.test.ts'], environment: 'jsdom',
  environmentOptions: { jsdom: { url: 'http://hermes-webapp.localhost:8080/' } },
  testTimeout: 60000, setupFiles: ['./tests/setup.ts'],
  server: { deps: { inline: ['@nous-research/ui'] } }
} }))
