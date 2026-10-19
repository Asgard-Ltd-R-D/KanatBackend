import { useCallback, useEffect, useRef, useState } from 'react'
import { whepConnect, whepDisconnect } from '../api/whep'
import { StreamStatus } from '../types'

// How long a dropped connection may stay down before we report it as lost
const STALL_MS = 5000

// Plays a MediaMTX path over WebRTC (WHEP) into the returned video ref.
// `reconnect` tears the peer connection down and opens a new one.
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

    const fail = (why: string) => {
      if (closed) return
      setReason(why)
      setStatus('error')
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
      clearTimeout(stallTimer)
      if (resourceUrl) whepDisconnect(resourceUrl)
      pc.close()
    }
  }, [path, attempt])

  return { videoRef, status, reason, reconnect, onPlaying }
}
