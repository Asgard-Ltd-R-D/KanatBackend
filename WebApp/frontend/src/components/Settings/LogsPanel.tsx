import { Download } from 'lucide-react'
import { logsExportUrl } from '../../api/logs'

// Downloading the logs for support: the backend zips the whole log folder and
// the app saves it (a target="_blank" link, which window.ts turns into a Save
// dialog). The operator emails the one file to support.
export function LogsPanel() {
  return (
    <section className="mt-10">
      <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-1">Logs</h2>
      <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">
        Save all log files as a single .zip to send to support.
      </p>
      <a
        href={logsExportUrl()}
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-2 px-4 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-sm font-medium rounded-lg transition-colors"
      >
        <Download size={16} />
        Download logs (.zip)
      </a>
    </section>
  )
}
