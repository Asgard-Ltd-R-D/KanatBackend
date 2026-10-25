import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../api/client'
import { openSessionLive } from '../api/live'
import { getSession } from '../api/sessions'
import { BulletHole, LiveEvent, Session } from '../types'
import { log } from '../utils/logger'

// Retries after the backend refuses the stream because the Session is unknown,
// before giving up. Any other refusal (the database down) is retried until it
// works.
const MAX_UNKNOWN_RETRIES = 3
const REFUSED_RETRY_MS = 1000
// The backend pings an idle stream every 15 s. Silence this long means it is
// frozen: reconnect.
const SILENCE_MS = 40_000
// Wait between attempts to refetch the Session after one failed
const RECONCILE_RETRY_MS = 2000

function upsertBullet(session: Session, bullet: BulletHole): Session {
  const others = (session.bullet_holes ?? []).filter((b) => b.id !== bullet.id)
  return { ...session, bullet_holes: [...others, bullet].sort((a, b) => a.rank - b.rank) }
}

// As the backend does: the bullets after the deleted one move up a rank
function removeBullet(session: Session, bulletId: string): Session {
  const bullets = session.bullet_holes ?? []
  const gone = bullets.find((b) => b.id === bulletId)
  if (!gone) return session
  return {
    ...session,
    bullet_holes: bullets
      .filter((b) => b.id !== bulletId)
      .map((b) => (b.rank > gone.rank ? { ...b, rank: b.rank - 1 } : b)),
  }
}

function applyEvent(session: Session, event: LiveEvent): Session {
  switch (event.type) {
    case 'bullet_created':
      return upsertBullet(session, event.bullet)
    case 'bullet_deleted':
      return removeBullet(session, event.bullet_id)
    case 'session_updated':
      return { ...session, name: event.name, status: event.status, ended_at: event.ended_at, record: event.record }
    case 'detection_updated':
      return { ...session, detection: event.detection }
    case 'run_moved':
      return session
  }
}

// Keeps the ['session', id] query current from the backend's live events while
// `enabled`. A dropped stream is reconnected by the browser itself, a silent or
// refused one by this hook.
export function useSessionLive(sessionId: string | undefined, enabled: boolean) {
  const qc = useQueryClient()

  useEffect(() => {
    if (!sessionId || !enabled) return

    const key = ['session', sessionId]
    let source: EventSource | null = null
    let retryTimer: ReturnType<typeof setTimeout> | undefined
    let silenceTimer: ReturnType<typeof setTimeout> | undefined
    let reconcileTimer: ReturnType<typeof setTimeout> | undefined
    let unknown = 0
    let stopped = false
    // Refused since the stream was last open: logged once, then retried quietly
    let refusedSince: number | null = null

    const heard = () => {
      clearTimeout(silenceTimer)
      silenceTimer = setTimeout(() => {
        log.warning('Live updates went silent; reconnecting', { session_id: sessionId, silent_s: SILENCE_MS / 1000 })
        source?.close()
        connect()
      }, SILENCE_MS)
    }

    // Refetch the Session, and keep trying until one refetch succeeds: the
    // stream does not replay an event whose refetch failed
    const reconcile = async () => {
      clearTimeout(reconcileTimer)
      await qc.invalidateQueries({ queryKey: key })
      if (!stopped && qc.getQueryState(key)?.status === 'error') {
        reconcileTimer = setTimeout(reconcile, RECONCILE_RETRY_MS)
      }
    }

    const connect = () => {
      source = openSessionLive(sessionId)

      // Also fires after each of the browser's own reconnects
      source.onopen = () => {
        unknown = 0
        if (refusedSince !== null) {
          log.info('Live updates back', { session_id: sessionId, refused_s: Math.round((Date.now() - refusedSince) / 1000) })
          refusedSince = null
        }
        heard()
        // Catch up on anything that happened before this stream was listening
        reconcile()
      }

      source.addEventListener('ping', heard)

      source.onmessage = (msg) => {
        heard()
        const event = JSON.parse(msg.data) as LiveEvent
        // On screen at once, even if the backend cannot be refetched right now
        qc.setQueryData<Session>(key, (s) => s && applyEvent(s, event))
        // Then confirm with the backend, except for a plain new bullet. A fetch
        // already in flight may have read the database before this event and
        // would overwrite it: reconcile restarts it.
        if (event.type !== 'bullet_created' || qc.isFetching({ queryKey: key })) reconcile()
        if (event.type === 'session_updated') qc.invalidateQueries({ queryKey: ['sessions'] })
      }

      source.onerror = () => {
        // Not listening any more; onopen starts the watch again
        clearTimeout(silenceTimer)
        // CONNECTING: the backend is unreachable and the browser is already
        // reconnecting. CLOSED: the backend answered with an error, and the
        // browser has given up.
        if (source?.readyState !== EventSource.CLOSED) return
        refused()
      }
    }

    // The browser does not say why it was refused: ask. The answer also lands
    // in the cache, so a Session that has ended stops this hook.
    const refused = async () => {
      if (refusedSince === null) {
        refusedSince = Date.now()
        log.warning('Live updates refused by the backend', { session_id: sessionId })
      }
      try {
        await qc.fetchQuery({ queryKey: key, queryFn: () => getSession(sessionId), retry: false })
      } catch (err) {
        const isUnknown = err instanceof ApiError && err.status === 404
        if (isUnknown && ++unknown > MAX_UNKNOWN_RETRIES) return
      }
      if (!stopped) retryTimer = setTimeout(connect, REFUSED_RETRY_MS)
    }

    connect()

    return () => {
      stopped = true
      clearTimeout(retryTimer)
      clearTimeout(silenceTimer)
      clearTimeout(reconcileTimer)
      source?.close()
    }
  }, [sessionId, enabled, qc])
}
