import { createServer } from 'vite'
import { createService, configuration } from '../server.mjs'
const vite = await createServer({ configFile: new URL('../vite.config.ts', import.meta.url).pathname, configLoader: 'runner', server: { hmr: false } })
await vite.listen()
const config = configuration()
const service = createService(config, { devOrigin: 'http://127.0.0.1:5175' })
service.listen(config.port, config.host, () => console.log(`Hermes Webapp dev: ${config.publicOrigin.origin}`))
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => { service.close(); void vite.close() })
