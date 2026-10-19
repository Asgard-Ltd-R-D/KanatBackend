// Runtime config from kanat-config.json, handed to the page by the preload
// script. The fallbacks cover running the renderer outside Electron.
export const API_URL = window.kanat?.apiUrl ?? 'http://localhost:8000'
export const MEDIA_URL = window.kanat?.mediaUrl ?? 'http://localhost:8889'
