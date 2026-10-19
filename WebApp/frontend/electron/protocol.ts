import { net, protocol } from 'electron'
import { join, sep } from 'path'
import { pathToFileURL } from 'url'
import { KanatConfig } from './config'

// Production pages are served from app://kanat/ rather than file://. A file://
// page's origin is "null", and MediaMTX refuses cross-site requests from a
// "null" origin, so WHEP would answer 403.
export const APP_ORIGIN = 'app://kanat'
const DIST_DIR = join(__dirname, '../dist')

// Must run before the app is ready
export function registerAppScheme() {
  protocol.registerSchemesAsPrivileged([
    { scheme: 'app', privileges: { standard: true, secure: true, supportFetchAPI: true } },
  ])
}

function contentSecurityPolicy({ apiUrl, mediaUrl }: KanatConfig): string {
  return [
    `default-src 'self' ${apiUrl} ${mediaUrl} https://fonts.googleapis.com https://fonts.gstatic.com`,
    `style-src 'self' 'unsafe-inline' https://fonts.googleapis.com`,
    `img-src 'self' data: blob:`,
    `script-src 'self' 'unsafe-eval'`,
  ].join('; ')
}

// Serves the built renderer (dist/) under app://kanat/, with the CSP attached
export function serveApp(config: KanatConfig) {
  const csp = contentSecurityPolicy(config)

  protocol.handle('app', async (request) => {
    const file = join(DIST_DIR, decodeURIComponent(new URL(request.url).pathname))
    if (!file.startsWith(DIST_DIR + sep)) return new Response(null, { status: 404 })

    const res = await net.fetch(pathToFileURL(file).toString())
    const headers = new Headers(res.headers)
    headers.set('Content-Security-Policy', csp)
    return new Response(res.body, { status: res.status, headers })
  })
}
