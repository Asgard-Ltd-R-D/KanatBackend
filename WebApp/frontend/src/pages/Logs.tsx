import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ExternalLink, FolderOpen, RotateCw, ServerOff } from 'lucide-react'
import { isGrafanaUp } from '../api/logs'
import { GRAFANA_URL } from '../utils/config'
import { log } from '../utils/logger'

// Grafana's Kanat WebApp dashboard (WebApp/observability/grafana/dashboards)
const DASHBOARD_PATH = '/d/kanat-webapp/kanat-webapp'
// How often to look whether Grafana answers: while it is down, and while it
// is up, so a Grafana stopped later shows how to start it again
const RETRY_MS = 10_000
const RECHECK_MS = 60_000

// Light or dark as the sidebar's switch sets it, on <html> (hooks/useDarkMode.ts)
function useDarkClass() {
  const root = document.documentElement
  const [dark, setDark] = useState(() => root.classList.contains('dark'))
  useEffect(() => {
    const read = () => setDark(root.classList.contains('dark'))
    const observer = new MutationObserver(read)
    observer.observe(root, { attributes: true, attributeFilter: ['class'] })
    // The class may have changed before watching began (the switch's own
    // effect runs after this page's)
    read()
    return () => observer.disconnect()
  }, [root])
  return dark
}

// The backend's and the app's logs, as Grafana shows them from Loki. Grafana
// runs beside the database (WebApp/docker-compose.yml), not in the app.
export function Logs() {
  const dark = useDarkClass()
  const [reloads, setReloads] = useState(0)
  // Only the first look and "Try again" show as looking: not each poll
  const [retrying, setRetrying] = useState(false)
  const grafana = useQuery({
    queryKey: ['grafana-up'],
    queryFn: isGrafanaUp,
    refetchInterval: (query) => (query.state.data ? RECHECK_MS : RETRY_MS),
  })
  const retry = async () => {
    setRetrying(true)
    await grafana.refetch()
    setRetrying(false)
  }

  useEffect(() => {
    if (grafana.data === false) log.warning('Logs tab: Grafana not reachable', { grafana_url: GRAFANA_URL })
  }, [grafana.data])

  const theme = dark ? 'dark' : 'light'
  const dashboardUrl = `${GRAFANA_URL}${DASHBOARD_PATH}?orgId=1&theme=${theme}`

  return (
    // Grafana fills the page; the title and buttons are a bar above it
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between gap-4 px-6 py-3 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
        <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Logs</h1>
        <div className="flex items-center gap-2 flex-shrink-0">
          <OpenLogFolder />
          {grafana.data && (
            <>
              <button
                onClick={() => setReloads((n) => n + 1)}
                title="Reload the dashboard"
                className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              >
                <RotateCw size={14} />
                Reload
              </button>
              <a
                href={`${GRAFANA_URL}${DASHBOARD_PATH}?orgId=1`}
                target="_blank"
                rel="noreferrer"
                title="Open Grafana in the browser, to search and explore"
                className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg bg-blue-600 hover:bg-blue-700 text-white transition-colors"
              >
                <ExternalLink size={14} />
                Open in Grafana
              </a>
            </>
          )}
        </div>
      </div>

      {grafana.data ? (
        <iframe
          key={`${theme}-${reloads}`}
          src={dashboardUrl}
          title="Kanat WebApp logs"
          // Grafana may not take the app's window over (no allow-top-navigation);
          // its links open in the browser (electron/window.ts)
          sandbox="allow-scripts allow-same-origin allow-popups allow-forms allow-downloads"
          className="flex-1 min-h-0 w-full border-0 bg-white dark:bg-slate-900"
        />
      ) : (
        <GrafanaDown checking={grafana.isPending || retrying} onRetry={retry} />
      )}
    </div>
  )
}

// The folder of backend.log, frontend.log, detection.log and postgres/, for
// reading them without Grafana: shown even while Grafana is down. Its path is
// the button's tooltip
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

function GrafanaDown({ checking, onRetry }: { checking: boolean; onRetry: () => void }) {
  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="max-w-md text-center bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl px-8 py-10 shadow-sm dark:shadow-none">
        <ServerOff size={28} className="mx-auto text-slate-400 dark:text-slate-500" />
        <h2 className="mt-4 text-base font-semibold text-slate-900 dark:text-slate-100">
          {checking ? 'Looking for Grafana…' : 'Grafana is not running'}
        </h2>
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
          The logs are shown by Grafana at <span className="font-mono">{GRAFANA_URL}</span>. Start it from the WebApp
          folder:
        </p>
        <pre className="mt-4 px-4 py-3 rounded-lg bg-slate-100 dark:bg-slate-800 text-left text-xs font-mono text-slate-700 dark:text-slate-300 overflow-x-auto">
          docker compose up -d loki alloy grafana
        </pre>
        <button
          onClick={onRetry}
          disabled={checking}
          className="mt-5 inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50 transition-colors"
        >
          <RotateCw size={14} className={checking ? 'animate-spin' : undefined} />
          Try again
        </button>
      </div>
    </div>
  )
}
