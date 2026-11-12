import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, Square, Download, FileText, FileSpreadsheet, AlertCircle, RefreshCw,
} from 'lucide-react'
import { format } from 'date-fns'
import { getSession, updateSession, exportUrl } from '../api/sessions'
import { StatusBadge } from '../components/UI/StatusBadge'
import { StatTile } from '../components/UI/StatTile'
import { ConfirmDialog } from '../components/UI/ConfirmDialog'
import { BoardTabs } from '../components/Session/BoardTabs'
import { CameraFeeds } from '../components/Camera/CameraFeeds'
import { useCameras } from '../hooks/useCameras'
import { useSessionLive } from '../hooks/useSessionLive'
import { boardsOf } from '../utils/boards'
import { formatDuration } from '../utils/format'

export function SessionDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [showEndConfirm, setShowEndConfirm] = useState(false)
  const [, setTick] = useState(0)

  const { data: session, isLoading, refetch } = useQuery({
    queryKey: ['session', id],
    queryFn: () => getSession(id!),
    enabled: !!id,
  })

  useSessionLive(id, session?.status === 'active')
  const { data: cameras } = useCameras()

  useEffect(() => {
    if (session?.status !== 'active') return
    const t = setInterval(() => setTick(n => n + 1), 1000)
    return () => clearInterval(t)
  }, [session?.status])

  const endMutation = useMutation({
    mutationFn: () => updateSession(id!, { status: 'completed' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['session', id] })
      qc.invalidateQueries({ queryKey: ['sessions'] })
      setShowEndConfirm(false)
    },
  })

  if (isLoading) {
    return (
      <div className="p-8">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-6 h-6 bg-slate-200 dark:bg-slate-800 rounded animate-pulse" />
          <div className="h-6 w-48 bg-slate-200 dark:bg-slate-800 rounded animate-pulse" />
        </div>
        <div className="grid grid-cols-2 gap-4 mb-8">
          {[...Array(2)].map((_, i) => (
            <div key={i} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl px-5 py-4 h-24 animate-pulse" />
          ))}
        </div>
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl h-96 animate-pulse" />
      </div>
    )
  }

  // Only when there is nothing to show: a failed refetch keeps the session on screen
  if (!session) {
    return (
      <div className="p-8 flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <AlertCircle size={40} className="text-red-500 dark:text-red-400" />
        <p className="text-slate-700 dark:text-slate-300 font-medium">Failed to load session</p>
        <div className="flex gap-3">
          <button onClick={() => refetch()} className="flex items-center gap-2 px-4 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-sm font-medium rounded-lg transition-colors">
            <RefreshCw size={14} /> Retry
          </button>
          <button onClick={() => navigate('/')} className="flex items-center gap-2 px-4 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-sm font-medium rounded-lg transition-colors">
            <ArrowLeft size={14} /> Back
          </button>
        </div>
      </div>
    )
  }

  const bullets = session.bullet_holes ?? []
  const active = session.status === 'active'
  // The boards: every enabled camera, merged with the Session's detections,
  // groupings and holes by camera_alias
  const boards = boardsOf(session, cameras)

  return (
    <div className="p-8">
      {/* Top bar */}
      <div className="flex items-start justify-between mb-6">
        <div className="flex items-center gap-4">
          <Link
            to="/"
            className="p-2 rounded-lg text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <ArrowLeft size={18} />
          </Link>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">{session.name}</h1>
              <StatusBadge status={session.status} />
            </div>
            <p className="text-sm text-slate-500 mt-0.5">
              {format(new Date(session.started_at), 'EEEE, MMM d yyyy · HH:mm')}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {active && (
            <button
              onClick={() => setShowEndConfirm(true)}
              className="flex items-center gap-2 px-4 py-2 bg-amber-50 dark:bg-amber-500/10 hover:bg-amber-100 dark:hover:bg-amber-500/20 border border-amber-200 dark:border-amber-500/30 text-amber-700 dark:text-amber-400 text-sm font-medium rounded-lg transition-colors"
            >
              <Square size={14} />
              End Session
            </button>
          )}

          {session.status === 'completed' && (
            <div className="flex items-center gap-1 pl-2 border-l border-slate-200 dark:border-slate-700">
              <a
                href={exportUrl(session.id, 'pdf')}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1.5 px-3 py-2 text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 text-sm font-medium rounded-lg transition-colors"
                title="Export PDF"
              >
                <FileText size={14} />
                PDF
              </a>
              <a
                href={exportUrl(session.id, 'csv')}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1.5 px-3 py-2 text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 text-sm font-medium rounded-lg transition-colors"
                title="Export CSV"
              >
                <Download size={14} />
                CSV
              </a>
              <a
                href={exportUrl(session.id, 'excel')}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1.5 px-3 py-2 text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 text-sm font-medium rounded-lg transition-colors"
                title="Export Excel"
              >
                <FileSpreadsheet size={14} />
                Excel
              </a>
            </div>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-4 mb-6 max-w-md">
        <StatTile label="Total Bullets" value={bullets.length} />
        <StatTile label="Duration" value={formatDuration(session.started_at, session.ended_at)} />
      </div>

      {/* Active: every enabled camera, live, each with its own board overlay */}
      {active && (
        <div className="mb-6">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">Camera Feed</p>
          <div className="h-[60vh] min-h-[320px]">
            <CameraFeeds runs={session.runs ?? []} bullets={bullets} detections={session.detections ?? []} />
          </div>
        </div>
      )}

      {/* Per board: detection, retake, Group, bullet log and manual-add */}
      <BoardTabs session={session} boards={boards} />

      <ConfirmDialog
        open={showEndConfirm}
        title="End Session"
        message={`End "${session.name}"?`}
        // Until the Run has judged its last Candidates and posted them, up to ~3 s
        loadingLabel="Closing…"
        confirmLabel="End Session"
        onConfirm={() => endMutation.mutate()}
        onCancel={() => {
          setShowEndConfirm(false)
          endMutation.reset()
        }}
        loading={endMutation.isPending}
        error={endMutation.error?.message}
      />
    </div>
  )
}
