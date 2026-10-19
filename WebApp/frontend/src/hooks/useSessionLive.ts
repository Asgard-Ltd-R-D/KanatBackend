import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../api/client'
import { openSessionLive } from '../api/live'
import { getSession } from '../api/sessions'
import { BulletHole, LiveEvent, Session } from '../types'

// Retries after the backend refuses the stream because the Session is unknown,
// before giving up. Any other refusal (the database down) is retried until it
// works.
const MAX_UNKNOWN_RETRIES = 3
const REFUSED_RETRY_MS = 1000
// The backend pings an idle stream every 15 s. Silence this long means it is
// frozen: reconnect.
const SILENCE_MS = 40_000

function upsertBullet(session: Session, bullet: BulletHole): Session {
  const others = (session.bullet_holes ?? []).filter((b) => b.id !== bullet.id)
  return { ...session, bullet_holes: [...others, bullet].sort((a, b) => a.rank - b.rank) }
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
    let unknown = 0
    let stopped = false

    const heard = () => {
      clearTimeout(silenceTimer)
      silenceTimer = setTimeout(() => {
        source?.close()
        connect()
      }, SILENCE_MS)
    }

    const connect = () => {
      source = openSessionLive(sessionId)

      // Also fires after each of the browser's own reconnects
      source.onopen = () => {
        unknown = 0
        heard()
        // Catch up on anything that happened before this stream was listening
        qc.invalidateQueries({ queryKey: key })
      }

      source.addEventListener('ping', heard)

      source.onmessage = (msg) => {
        heard()
        const event = JSON.parse(msg.data) as LiveEvent
        if (event.type === 'bullet_created' && !qc.isFetching({ queryKey: key })) {
          qc.setQueryData<Session>(key, (s) => s && upsertBullet(s, event.bullet))
        } else {
          // A fetch already in flight may have read the database before this
          // event, and would overwrite it: restart it instead. A delete
          // renumbers the bullets after it, and a status change ends the live
          // view: take the backend's word for both.
          qc.invalidateQueries({ queryKey: key })
          if (event.type === 'session_updated') qc.invalidateQueries({ queryKey: ['sessions'] })
        }
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
      source?.close()
    }
  }, [sessionId, enabled, qc])
}
