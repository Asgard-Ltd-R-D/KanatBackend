// WHEP signalling against MediaMTX's WebRTC server. The video itself flows
// over WebRTC (UDP, webrtcLocalUDPAddress); these calls only open and close it.
import { WhepSession } from '../types'

// MediaMTX's WebRTC server, on the same PC
const MEDIA_URL = 'http://localhost:8889'

export async function whepConnect(path: string, offerSdp: string): Promise<WhepSession> {
  const url = `${MEDIA_URL}/${encodeURIComponent(path)}/whep`
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/sdp' },
    body: offerSdp,
  })

  if (res.status !== 200 && res.status !== 201) {
    throw new Error(res.status === 404 ? 'Stream not found' : `Connection error (HTTP ${res.status})`)
  }

  // MediaMTX returns a relative Location; resolve it against MediaMTX, not the app
  const location = res.headers.get('Location')
  return {
    answerSdp: await res.text(),
    resourceUrl: location ? new URL(location, url).href : null,
  }
}

export function whepDisconnect(resourceUrl: string): void {
  fetch(resourceUrl, { method: 'DELETE' }).catch(() => {})
}
