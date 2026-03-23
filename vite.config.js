import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { writeFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { join, dirname } from 'path'

const __dirname = dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'sync-endpoint',
      configureServer(server) {
        server.middlewares.use('/sync', (req, res) => {
          res.setHeader('Access-Control-Allow-Origin', '*')
          if (req.method === 'OPTIONS') { res.writeHead(200); res.end(); return }
          if (req.method !== 'POST') { res.writeHead(405); res.end(); return }
          let body = ''
          req.on('data', chunk => { body += chunk })
          req.on('end', () => {
            try {
              JSON.parse(body)
              writeFileSync(join(__dirname, 'sync-data.json'), body, 'utf8')
              res.writeHead(200, { 'Content-Type': 'text/plain' })
              res.end('ok')
            } catch { res.writeHead(400); res.end('error') }
          })
        })
      }
    }
  ],
})
