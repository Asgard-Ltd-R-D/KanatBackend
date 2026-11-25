// TEMPORARY debug capture (delete before production). One toggle on the live
// session: it records the raw camera stream (backend), the logs (backend) and
// the app's view with overlay (here), into one timestamped folder. Records
// until pressed again or the session ends.
import { RefObject, useEffect, useRef, useState } from 'react'
import { Circle, Loader2, Square } from 'lucide-react'
import clsx from 'clsx'
import { beaconStop, heartbeat, startRecording, stopRecording, uploadOverlay } from '../../api/debug'
import { ApiError } from '../../api/client'
import { startAppViewRecording, AppViewRecording } from '../../utils/debugRecorder'
import { log } from '../../utils/logger'

type State = 'idle' | 'recording' | 'busy'

// Keepalive interval, well under the backend's lease window (5 min)
const HEARTBEAT_MS = 60_000

export function DebugRecordButton({
  feedRef,
  camera,
  active,
}: {
  feedRef: RefObject<HTMLElement>
  camera?: string
  active: boolean
}) {
  const [state, setState] = useState<State>('idle')
  const idRef = useRef<string | null>(null)
  const appViewRef = useRef<AppViewRecording | null>(null)
  // Set once the component is gone, so a start that resolves after unmount
  // stops the backend recording it created instead of leaking it.
  const disposedRef = useRef(false)
  // The stop in flight, so a second stop (e.g. a press then unmount) joins it
  // instead of racing: a duplicate would 404 the first's overlay upload.
  const stopPromiseRef = useRef<Promise<void> | null>(null)

  const runStop = async () => {
    const id = idRef.current
    if (!id) return
    const appView = appViewRef.current
    appViewRef.current = null
    setState('busy')
    // Finalising the app-view (upload) must never skip the backend stop: a
    // leaked ffmpeg would record forever. So upload is best-effort, and the id
    // is kept until the backend stop itself succeeds, so a failure can retry.
    try {
      if (appView) await uploadOverlay(id, await appView.stop())
    } catch (err) {
      log.warning('Debug overlay upload failed; stopping the recording anyway', { error: String(err) })
    }
    try {
      const { folder } = await stopRecording(id)
      idRef.current = null
      log.info('Debug recording saved', { folder })
      setState('idle')
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        // Already gone on the backend (its safety lease expired, or a duplicate
        // stop won): terminal, not retryable — unstick the button.
        idRef.current = null
        log.warning('Debug recording was already stopped (lease expired?)', { error: String(err) })
        setState('idle')
      } else {
        log.warning('Debug recording did not stop; it can be stopped again', { error: String(err) })
        stopPromiseRef.current = null // let another press / unmount retry
        setState('recording') // keep the id
      }
    }
  }

  const stop = (): Promise<void> => {
    if (stopPromiseRef.current) return stopPromiseRef.current
    const p = runStop()
    stopPromiseRef.current = p
    return p
  }

  const start = async () => {
    stopPromiseRef.current = null
    setState('busy')
    let id: string
    try {
      ;({ id } = await startRecording(camera))
    } catch (err) {
      log.warning('Debug recording could not start', { error: String(err) })
      setState('idle')
      return
    }
    // Gone before the backend answered: stop what we just started, don't adopt it
    if (disposedRef.current) {
      void stopRecording(id).catch(() => {})
      return
    }
    idRef.current = id
    if (feedRef.current) {
      try {
        appViewRef.current = startAppViewRecording(feedRef.current)
      } catch (err) {
        log.warning('App-view recording could not start (stream, logs still captured)', { error: String(err) })
      }
    }
    setState('recording')
  }

  // The session ending stops a running recording so its files are saved.
  useEffect(() => {
    if (!active && idRef.current) void stop()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active])
  // Leaving the page: mark disposed (so a pending start stops itself) and stop
  // any running recording. disposed is reset here on setup so a StrictMode
  // remount (setup, cleanup, setup) does not leave it stuck true.
  useEffect(() => {
    disposedRef.current = false
    return () => {
      disposedRef.current = true
      if (idRef.current) void stop()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  // Closing or reloading the Electron window skips React cleanup, so a beacon
  // stops the backend recording on the way out (the lease is the last resort).
  useEffect(() => {
    const onUnload = () => {
      if (idRef.current) beaconStop(idRef.current)
    }
    window.addEventListener('beforeunload', onUnload)
    return () => window.removeEventListener('beforeunload', onUnload)
  }, [])
  // While recording, keep the backend lease alive, so a long live recording is
  // never auto-stopped under the operator (which would lose its view). Well
  // under the lease window, so one missed beat is harmless.
  useEffect(() => {
    if (state !== 'recording') return
    const t = window.setInterval(() => {
      if (idRef.current) heartbeat(idRef.current)
    }, HEARTBEAT_MS)
    return () => window.clearInterval(t)
  }, [state])

  const recording = state === 'recording'
  return (
    <button
      type="button"
      onClick={() => (recording ? void stop() : void start())}
      disabled={state === 'busy'}
      title="Debug only: record the raw stream, logs and this view to a folder"
      className={clsx(
        'flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg border transition-colors press',
        recording
          ? 'bg-red-600 hover:bg-red-700 border-red-600 text-white'
          : 'bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300',
        state === 'busy' && 'opacity-60 cursor-wait',
      )}
    >
      {state === 'busy' ? (
        <Loader2 size={14} className="animate-spin" />
      ) : recording ? (
        <Square size={14} className="fill-current" />
      ) : (
        <Circle size={14} className="fill-red-500 text-red-500" />
      )}
      {recording ? 'Stop Rec' : 'Debug Rec'}
    </button>
  )
}
