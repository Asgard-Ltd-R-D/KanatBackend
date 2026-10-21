// WHEP signalling against MediaMTX's WebRTC server. The video itself flows
// over WebRTC (UDP, webrtcLocalUDPAddress); these calls only open and close it.
import { WhepSession } from '../types'
import { MEDIA_URL } from '../utils/config'

export async function whepConnect(path: string, offerSdp: string): Promise<WhepSession> {
  const url = `${MEDIA_URL}/${encodeURIComponent(path)}/whep`
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/sdp' },
    body: offerSdp,
  })

  if (res.status !== 200 && res.status !== 201) {
    // 404: the path exists but nothing is publishing to it. 400: the video
    // service does not have the camera yet (the backend adds it within seconds)
    const reason =
      res.status === 404 ? 'No signal from camera'
      : res.status === 400 ? 'Camera not set up in the video service yet'
      : `Connection error (HTTP ${res.status})`
    throw new Error(reason)
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
