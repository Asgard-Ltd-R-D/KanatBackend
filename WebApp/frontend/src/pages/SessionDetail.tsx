import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, Square, Plus, Download, FileText, FileSpreadsheet, AlertCircle, RefreshCw,
} from 'lucide-react'
import { format } from 'date-fns'
import { getSession, updateSession, exportUrl } from '../api/sessions'
import { deleteBullet } from '../api/bullets'
import { BulletHole } from '../types'
import { StatusBadge } from '../components/UI/StatusBadge'
import { DetectionBadge } from '../components/Session/DetectionBadge'
import { StatTile } from '../components/UI/StatTile'
import { ConfirmDialog } from '../components/UI/ConfirmDialog'
import { AddBulletModal } from '../components/Session/AddBulletModal'
import { BulletLog } from '../components/Session/BulletLog'
import { LiveDetectionsPanel } from '../components/Session/LiveDetectionsPanel'
import { CameraFeeds } from '../components/Camera/CameraFeeds'
import { RecordingControl } from '../components/Session/RecordingControl'
import { RecordingsCard } from '../components/Session/RecordingsCard'
import { ReplayModal, ReplayTarget } from '../components/Session/ReplayModal'
import { useRecordings } from '../hooks/useRecordings'
import { findMoment } from '../utils/recordings'
import { useSessionLive } from '../hooks/useSessionLive'
import { formatDuration } from '../utils/format'

// A bullet's replay starts this long before it was seen, to show the shot
const REPLAY_PREROLL_S = 3

export function SessionDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [showAddBullet, setShowAddBullet] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<BulletHole | null>(null)
  const [showEndConfirm, setShowEndConfirm] = useState(false)
  const [, setTick] = useState(0)
  const [replay, setReplay] = useState<ReplayTarget | null>(null)

  const { data: session, isLoading, refetch } = useQuery({
    queryKey: ['session', id],
    queryFn: () => getSession(id!),
    enabled: !!id,
  })

  useSessionLive(id, session?.status === 'active')
  const recordings = useRecordings(id!, session?.status === 'completed')

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

  const deleteBulletMutation = useMutation({
    mutationFn: (bulletId: string) => deleteBullet(id!, bulletId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['session', id] })
      qc.invalidateQueries({ queryKey: ['sessions'] })
      setDeleteTarget(null)
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

  return (
    // An active session fills the window: the cameras and the live detections
    // take all the height below the header and stats
    <div className={active ? 'p-8 h-full flex flex-col' : 'p-8'}>
      {/* Top bar */}
      <div className="flex items-start justify-between mb-6 shrink-0">
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
              {/* Once ended, only to say its Run's end was not confirmed */}
              {session.detection && (active || session.detection.state === 'end_unconfirmed') && (
                <DetectionBadge detection={session.detection} />
              )}
            </div>
            <p className="text-sm text-slate-500 mt-0.5">
              {format(new Date(session.started_at), 'EEEE, MMM d yyyy · HH:mm')}
              {' · '}{formatDuration(session.started_at, session.ended_at)}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {session.status === 'active' && <RecordingControl session={session} />}

          {session.status === 'active' && (
            <button
              onClick={() => setShowEndConfirm(true)}
              className="flex items-center gap-2 px-4 py-2 bg-amber-50 dark:bg-amber-500/10 hover:bg-amber-100 dark:hover:bg-amber-500/20 border border-amber-200 dark:border-amber-500/30 text-amber-700 dark:text-amber-400 text-sm font-medium rounded-lg transition-colors"
            >
              <Square size={14} />
              End Session
            </button>
          )}

          {session.status === 'completed' && (
            <button
              onClick={() => setShowAddBullet(true)}
              className="flex items-center gap-2 px-4 py-2 bg-blue-50 dark:bg-blue-600/10 hover:bg-blue-100 dark:hover:bg-blue-600/20 border border-blue-200 dark:border-blue-600/30 text-blue-700 dark:text-blue-400 text-sm font-medium rounded-lg transition-colors"
            >
              <Plus size={14} />
              Add Bullet
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
                download
                className="flex items-center gap-1.5 px-3 py-2 text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 text-sm font-medium rounded-lg transition-colors"
                title="Export CSV"
              >
                <Download size={14} />
                CSV
              </a>
              <a
                href={exportUrl(session.id, 'excel')}
                download
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

      {/* Active: stats + stream + live bullet feed */}
      {active && (
        <div className="flex-1 min-h-0 flex flex-col gap-4">
          {/* Mini stats */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 shrink-0">
            <StatTile label="Total Bullets" value={bullets.length} />
            <StatTile label="AI Detected" value={bullets.filter(b => b.source === 'model').length} />
            <StatTile label="Manual" value={bullets.filter(b => b.source === 'manual').length} />
            <StatTile label="Duration" value={formatDuration(session.started_at, null)} />
          </div>

          {/* Cameras (2/3) and live detections (1/3), both to the bottom of the window */}
          <div className="flex-1 min-h-[420px] grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2 flex flex-col min-h-0">
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2 shrink-0">Camera Feed</p>
              <div className="flex-1 min-h-[300px]">
                <CameraFeeds />
              </div>
            </div>

            <div className="flex flex-col min-h-0">
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2 shrink-0">Live Detections</p>
              <LiveDetectionsPanel bullets={bullets} />
            </div>
          </div>
        </div>
      )}

      {/* Completed: stats + bullet table */}
      {session.status === 'completed' && (
        <>
          <div className="grid grid-cols-2 gap-4 mb-6">
            <StatTile label="Total Bullets" value={bullets.length} />
            <StatTile label="Duration" value={formatDuration(session.started_at, session.ended_at)} />
          </div>

          <RecordingsCard
            recordings={recordings.data}
            isLoading={recordings.isLoading}
            isError={recordings.isError}
            onRetry={() => recordings.refetch()}
            onPlay={alias => setReplay({ alias })}
          />

          <BulletLog
            bullets={bullets}
            onDelete={setDeleteTarget}
            canReplay={b => !!recordings.data && findMoment(recordings.data, b.first_seen_at) !== null}
            onReplay={b => {
              const moment = recordings.data && findMoment(recordings.data, b.first_seen_at, REPLAY_PREROLL_S)
              if (moment) setReplay({ alias: moment.alias, part: moment.part, offsetS: moment.offsetS })
            }}
          />

          <ReplayModal
            sessionId={session.id}
            recordings={recordings.data ?? []}
            target={replay}
            onChange={setReplay}
          />
        </>
      )}

      <ConfirmDialog
        open={showEndConfirm}
        title="End Session"
        message={`End "${session.name}"?`}
        loadingLabel="Ending…"
        confirmLabel="End Session"
        onConfirm={() => endMutation.mutate()}
        onCancel={() => {
          setShowEndConfirm(false)
          endMutation.reset()
        }}
        loading={endMutation.isPending}
        error={endMutation.error?.message}
      />

      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete Bullet"
        message={`Delete bullet #${deleteTarget?.rank ?? ''}?`}
        confirmLabel="Delete"
        onConfirm={() => deleteTarget && deleteBulletMutation.mutate(deleteTarget.id)}
        onCancel={() => {
          setDeleteTarget(null)
          deleteBulletMutation.reset()
        }}
        loading={deleteBulletMutation.isPending}
        error={deleteBulletMutation.error?.message}
      />

      <AddBulletModal
        open={showAddBullet}
        sessionId={session.id}
        onClose={() => setShowAddBullet(false)}
        onSuccess={() => {}}
      />
    </div>
  )
}
