import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, Download, FolderOpen, Lock, Pause, Play, RotateCw, ServerOff } from 'lucide-react'
import { logsExportUrl, readLogs, type LogLine } from '../api/logs'
import { getSessions } from '../api/sessions'
import { log } from '../utils/logger'

// The Logs tab is for engineers: when the install bakes a password
// (window.kanat.logsProtected), it is locked until the password is entered, and
// locked again the moment the operator leaves the tab, so coming back asks for
// the password once more. With no password configured (developing), it is open.
const lockedByDefault = () => !window.kanat?.logsProtected

export function Logs() {
  const [unlocked, setUnlocked] = useState(lockedByDefault)

  // Re-lock on leaving the tab: reset the gate and tell the main process, so the
  // log data cannot be read around the gate from the renderer either.
  useEffect(() => {
    return () => {
      if (window.kanat?.logsProtected) window.kanatLog?.lock()
    }
  }, [])

  if (!unlocked) return <LogsGate onUnlock={() => setUnlocked(true)} />
  return <LogsViewer />
}

function LogsGate({ onUnlock }: { onUnlock: () => void }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState(false)
  const [checking, setChecking] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setChecking(true)
    const ok = (await window.kanatLog?.verifyPassword(password)) ?? false
    setChecking(false)
    if (ok) onUnlock()
    else {
      setError(true)
      setPassword('')
    }
  }

  return (
    <div className="h-full flex items-center justify-center p-8">
      <form
        onSubmit={submit}
        className="w-full max-w-sm text-center bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl px-8 py-10 shadow-sm dark:shadow-none"
      >
        <Lock size={28} className="mx-auto text-slate-400 dark:text-slate-500" />
        <h1 className="mt-4 text-base font-semibold text-slate-900 dark:text-slate-100">Logs are restricted</h1>
        <input
          type="password"
          value={password}
          onChange={(e) => { setPassword(e.target.value); setError(false) }}
          placeholder="Password"
          className="mt-5 w-full px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 placeholder-slate-400"
        />
        {error && <p className="mt-2 text-sm text-red-600 dark:text-red-400">Wrong password.</p>}
        <button
          type="submit"
          disabled={checking || !password}
          className="mt-5 w-full px-3 py-2 text-sm font-medium rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white transition-colors"
        >
          {checking ? 'Checking…' : 'Unlock'}
        </button>
      </form>
    </div>
  )
}

// The backend's, the app's and the Detection Service's logs, read from the
// files the app itself writes (electron/logreader.ts), newest first. No Grafana.
const REFRESH_MS = 3_000
// Levels in order, for the "this level and worse" filter (Python can log critical)
const LEVELS = ['debug', 'info', 'warning', 'error', 'critical'] as const
type Level = (typeof LEVELS)[number]
const SERVICES = ['backend', 'frontend', 'detection'] as const

const LEVEL_STYLE: Record<string, string> = {
  critical: 'text-white bg-red-700 dark:text-red-50 dark:bg-red-800',
  error: 'text-red-700 bg-red-100 dark:text-red-300 dark:bg-red-950',
  warning: 'text-amber-700 bg-amber-100 dark:text-amber-300 dark:bg-amber-950',
  info: 'text-slate-600 bg-slate-100 dark:text-slate-300 dark:bg-slate-800',
  debug: 'text-slate-500 bg-slate-50 dark:text-slate-400 dark:bg-slate-800/60',
}

// YYYY-MM-DD HH:MM:SS on this PC's clock, from an ISO timestamp (or the raw value
// if it is not one): a line from yesterday must not read like one from today
function stamp(time: string): string {
  const d = new Date(time)
  if (isNaN(d.getTime())) return time
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

// The Session a line is about: the name it carries, else the name of its session_id
// from the Sessions list (the Detection Service logs the id only)
function sessionNameOf(line: LogLine, names: Map<string, string>): string | undefined {
  const own = line.fields.session_name
  if (typeof own === 'string' && own) return own
  const id = line.fields.session_id
  return typeof id === 'string' ? names.get(id) : undefined
}

function LogsViewer() {
  const [minLevel, setMinLevel] = useState<Level>('info')
  const [service, setService] = useState<'all' | (typeof SERVICES)[number]>('all')
  const [search, setSearch] = useState('')
  const [live, setLive] = useState(true)

  const query = useQuery({
    queryKey: ['logs'],
    queryFn: () => readLogs(),
    refetchInterval: live ? REFRESH_MS : false,
  })

  // Session names by id, so searching a name finds every line about that Session,
  // the Detection Service's too (they carry the id only)
  const sessions = useQuery({ queryKey: ['sessions'], queryFn: getSessions })
  const names = useMemo(() => new Map((sessions.data ?? []).map((s) => [s.id, s.name])), [sessions.data])

  const lines = query.data ?? []
  const filtered = useMemo(() => {
    const floor = LEVELS.indexOf(minLevel)
    const needle = search.trim().toLowerCase()
    return lines.filter((l) => {
      const rank = LEVELS.indexOf(l.level as Level)
      if (rank !== -1 && rank < floor) return false
      if (service !== 'all' && l.service !== service) return false
      if (needle) {
        const hay = `${l.message} ${l.logger ?? ''} ${sessionNameOf(l, names) ?? ''} ${JSON.stringify(l.fields)}`.toLowerCase()
        if (!hay.includes(needle)) return false
      }
      return true
    })
  }, [lines, minLevel, service, search, names])

  // readLogs returns newest first; show oldest to newest, the newest at the
  // bottom, as a terminal does
  const displayed = useMemo(() => [...filtered].reverse(), [filtered])

  // Keep the newest line in view, but only while the operator is already at the
  // bottom: scrolling up to read stays put, even as refreshes add lines
  const scrollRef = useRef<HTMLDivElement>(null)
  const stick = useRef(true)
  const onScroll = () => {
    const el = scrollRef.current
    if (el) stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40
  }
  useLayoutEffect(() => {
    const el = scrollRef.current
    if (el && stick.current) el.scrollTop = el.scrollHeight
  }, [displayed])

  // Not running in Electron (a plain browser): nothing to read
  if (!window.kanatLog?.read) return <NoViewer />

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between gap-4 px-6 py-3 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
        <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Logs</h1>
        <div className="flex items-center gap-2 flex-shrink-0">
          <select
            value={minLevel}
            onChange={(e) => setMinLevel(e.target.value as Level)}
            title="Show this level and worse"
            className="px-2.5 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200"
          >
            {LEVELS.map((l) => (
              <option key={l} value={l}>
                {l[0].toUpperCase() + l.slice(1)}+
              </option>
            ))}
          </select>
          <select
            value={service}
            onChange={(e) => setService(e.target.value as typeof service)}
            title="Which service"
            className="px-2.5 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200"
          >
            <option value="all">All services</option>
            {SERVICES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search…"
            className="px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 placeholder-slate-400"
          />
          <button
            onClick={() => setLive((v) => !v)}
            title={live ? 'Pause auto-refresh' : 'Resume auto-refresh'}
            className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            {live ? <Pause size={14} /> : <Play size={14} />}
            {live ? 'Live' : 'Paused'}
          </button>
          <button
            onClick={() => query.refetch()}
            title="Reload now"
            className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <RotateCw size={14} className={query.isFetching ? 'animate-spin' : undefined} />
            Reload
          </button>
          <OpenLogFolder />
          <DownloadLogs />
        </div>
      </div>

      <div ref={scrollRef} onScroll={onScroll} className="flex-1 min-h-0 overflow-auto bg-white dark:bg-slate-900">
        {displayed.length === 0 ? (
          <p className="p-8 text-center text-sm text-slate-500 dark:text-slate-400">
            {query.isPending ? 'Reading logs…' : 'No log lines match.'}
          </p>
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800 font-mono text-xs">
            {displayed.map((line) => (
              // Key from the line's whole content (fields included), not its index:
              // a row keeps its identity and expanded state as refreshes add lines,
              // and two rows share a key only when every field is identical — then
              // they are interchangeable, so the expanded view is the same either way
              <Row
                key={`${line.time}|${line.service}|${line.logger ?? ''}|${line.message}|${JSON.stringify(line.fields)}`}
                line={line}
                session={sessionNameOf(line, names)}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

function Row({ line, session }: { line: LogLine; session?: string }) {
  const [open, setOpen] = useState(false)
  const hasFields = Object.keys(line.fields).length > 0
  return (
    <li className="px-6 py-1.5 hover:bg-slate-50 dark:hover:bg-slate-800/50">
      <button
        onClick={() => hasFields && setOpen((v) => !v)}
        className={`w-full flex items-start gap-3 text-left ${hasFields ? '' : 'cursor-default'}`}
      >
        <ChevronRight
          size={12}
          className={`mt-0.5 flex-shrink-0 text-slate-400 transition-transform ${open ? 'rotate-90' : ''} ${hasFields ? '' : 'invisible'}`}
        />
        <span className="flex-shrink-0 tabular-nums text-slate-400 dark:text-slate-500">{stamp(line.time)}</span>
        <span className={`flex-shrink-0 px-1.5 rounded uppercase font-semibold ${LEVEL_STYLE[line.level] ?? LEVEL_STYLE.info}`}>
          {line.level}
        </span>
        <span className="flex-shrink-0 w-16 text-slate-500 dark:text-slate-400">{line.service}</span>
        <span className="text-slate-800 dark:text-slate-200 break-all">{line.message}</span>
        {session && !line.message.includes(session) && (
          <span className="flex-shrink-0 px-1.5 rounded bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300">
            {session}
          </span>
        )}
      </button>
      {open && hasFields && (
        <pre className="ml-8 mt-1 p-2 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 overflow-x-auto">
          {JSON.stringify(line.fields, null, 2)}
        </pre>
      )}
    </li>
  )
}

// Opens the log folder in the system's file manager (the rotated files live there too)
function OpenLogFolder() {
  const dir = window.kanat?.logDir
  const openFolder = window.kanatLog?.openFolder
  if (!dir || !openFolder) return null
  return (
    <button
      onClick={async () => {
        const problem = await openFolder()
        if (problem) log.warning('Opening the log folder failed', { log_dir: dir, problem })
      }}
      title={`Open the log folder: ${dir}`}
      className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
    >
      <FolderOpen size={14} />
      Open folder
    </button>
  )
}

// Downloading the logs for support: the backend zips the whole log folder and
// the app saves it (a target="_blank" link, which window.ts turns into a Save
// dialog). The operator emails the one file to support.
function DownloadLogs() {
  return (
    <a
      href={logsExportUrl()}
      target="_blank"
      rel="noreferrer"
      title="Save all log files as a single .zip to send to support"
      className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
    >
      <Download size={14} />
      Download logs (.zip)
    </a>
  )
}

function NoViewer() {
  return (
    <div className="h-full flex items-center justify-center p-8">
      <div className="max-w-md text-center text-slate-500 dark:text-slate-400">
        <ServerOff size={28} className="mx-auto" />
        <p className="mt-4 text-sm">The log viewer runs inside the desktop app.</p>
        {/* The zip comes from the backend over HTTP, which needs no Electron: a browser can still send it to support */}
        <div className="mt-4 flex justify-center">
          <DownloadLogs />
        </div>
      </div>
    </div>
  )
}
