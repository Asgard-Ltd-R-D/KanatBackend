import { useCallback, useEffect, useRef, useState } from 'react'
import { whepConnect, whepDisconnect } from '../api/whep'
import { StreamStatus } from '../types'

// How long a dropped connection may stay down before we report it as lost
const STALL_MS = 5000
// After a failure, how long before trying again on its own: a camera may come
// online after the page opened
const RETRY_MS = 5000
// A camera that stops sending leaves the connection up with no video in it, so
// the bytes received are watched: none for this long is reported as no video
const WATCH_MS = 2000
const NO_VIDEO_MS = 8000

// Plays a MediaMTX path over WebRTC (WHEP) into the returned video ref, and
// keeps retrying after a failure. `reconnect` tries again straight away.
export function useWhepStream(path: string) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [status, setStatus] = useState<StreamStatus>('loading')
  const [reason, setReason] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  const reconnect = useCallback(() => setAttempt((a) => a + 1), [])
  const onPlaying = useCallback(() => setStatus('playing'), [])

  useEffect(() => {
    setStatus('loading')
    setReason(null)

    const pc = new RTCPeerConnection({ bundlePolicy: 'max-bundle' })
    const stream = new MediaStream()
    if (videoRef.current) videoRef.current.srcObject = stream

    let closed = false
    let resourceUrl: string | null = null
    let stallTimer: ReturnType<typeof setTimeout> | undefined
    let retryTimer: ReturnType<typeof setTimeout> | undefined
    let lastBytes = 0
    let lastGrowth = Date.now()

    const videoBytes = async () => {
      let bytes = 0
      ;(await pc.getStats()).forEach((report) => {
        if (report.type === 'inbound-rtp' && report.kind === 'video') bytes += report.bytesReceived ?? 0
      })
      return bytes
    }
    const watchdog = setInterval(async () => {
      const bytes = await videoBytes().catch(() => lastBytes)
      if (bytes > lastBytes) {
        lastBytes = bytes
        lastGrowth = Date.now()
      } else if (Date.now() - lastGrowth > NO_VIDEO_MS) {
        fail('No video from camera')
      }
    }, WATCH_MS)

    const fail = (why: string) => {
      if (closed || retryTimer) return
      setReason(why)
      setStatus('error')
      retryTimer = setTimeout(() => setAttempt((a) => a + 1), RETRY_MS)
    }
    const armStall = (why: string) => {
      clearTimeout(stallTimer)
      stallTimer = setTimeout(() => fail(why), STALL_MS)
    }

    pc.addTransceiver('video', { direction: 'recvonly' })
    pc.addTransceiver('audio', { direction: 'recvonly' })

    pc.ontrack = (ev) => {
      stream.addTrack(ev.track)
      if (ev.track.kind === 'video') {
        ev.track.addEventListener('ended', () => fail('Stream ended'), { once: true })
      }
    }

    pc.onconnectionstatechange = () => {
      const s = pc.connectionState
      if (s === 'connected') clearTimeout(stallTimer)
      else if (s === 'disconnected') armStall('Connection lost')
      else if (s === 'failed') fail('Connection failed')
    }

    // Non-trickle WHEP: send the offer once every ICE candidate is in it
    const iceGathered = () =>
      new Promise<void>((resolve) => {
        if (pc.iceGatheringState === 'complete') return resolve()
        pc.addEventListener('icegatheringstatechange', () => {
          if (pc.iceGatheringState === 'complete') resolve()
        })
      })

    pc.createOffer()
      .then((offer) => pc.setLocalDescription(offer))
      .then(iceGathered)
      .then(() => whepConnect(path, pc.localDescription?.sdp ?? ''))
      .then((session) => {
        if (closed) {
          // Unmounted while connecting: release the session MediaMTX just opened
          if (session.resourceUrl) whepDisconnect(session.resourceUrl)
          return
        }
        resourceUrl = session.resourceUrl
        return pc.setRemoteDescription({ type: 'answer', sdp: session.answerSdp })
      })
      .catch((err) => fail(err instanceof Error ? err.message : 'Connection error'))

    return () => {
      closed = true
      clearInterval(watchdog)
      clearTimeout(stallTimer)
      clearTimeout(retryTimer)
      if (resourceUrl) whepDisconnect(resourceUrl)
      pc.close()
    }
  }, [path, attempt])

  return { videoRef, status, reason, reconnect, onPlaying }
}
