// Runtime config from kanat-config.json, handed to the page by the preload
// script. The fallbacks cover running the renderer outside Electron.
export const API_URL = window.kanat?.apiUrl ?? 'http://127.0.0.1:8000'
export const MEDIA_URL = window.kanat?.mediaUrl ?? 'http://127.0.0.1:8889'
