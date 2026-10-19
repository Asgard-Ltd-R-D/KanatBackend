import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, Square, Plus, Trash2, Download, FileText, FileSpreadsheet,
  AlertCircle, RefreshCw, Crosshair, Bot, User,
} from 'lucide-react'
import { format } from 'date-fns'
import { getSession, updateSession, exportUrl } from '../api/sessions'
import { deleteBullet } from '../api/bullets'
import { BulletHole } from '../types'
import { StatusBadge } from '../components/UI/StatusBadge'
import { ConfirmDialog } from '../components/UI/ConfirmDialog'
import { AddBulletModal } from '../components/Session/AddBulletModal'
import { WhepPlayer } from '../components/Camera/WhepPlayer'

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function formatDuration(a: string, b: string | null): string {
  const ms = (b ? new Date(b).getTime() : Date.now()) - new Date(a).getTime()
  const m = Math.floor(ms / 60000)
  const s = Math.floor((ms % 60000) / 1000)
  return `${m}m ${s}s`
}

function StatTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl px-5 py-4 shadow-sm dark:shadow-none">
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">{label}</p>
      <p className="text-2xl font-semibold text-slate-900 dark:text-slate-100">{value}</p>
    </div>
  )
}

function SourceBadge({ source }: { source: 'model' | 'manual' }) {
  if (source === 'model') {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full font-semibold tracking-wide bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-500/20">
        <Bot size={9} />
        AI
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full font-semibold tracking-wide bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-200 dark:border-amber-500/20">
      <User size={9} />
      M
    </span>
  )
}

function locationLabel(b: BulletHole): string {
  if (b.target_index !== null) return `Target ${b.target_index + 1}`
  // Model always computes target assignment; null means explicitly outside targets.
  // Manual bullets never supply target_index, so null means location is unknown.
  return b.source === 'model' ? 'Miss' : '—'
}

function mmLabel(b: BulletHole): string {
  if (b.x_mm == null || b.y_mm == null) return '—'
  const sign = (n: number) => (n >= 0 ? `+${n.toFixed(1)}` : n.toFixed(1))
  return `${sign(b.x_mm)}, ${sign(b.y_mm)} mm`
}

export function SessionDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [showAddBullet, setShowAddBullet] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<BulletHole | null>(null)
  const [showEndConfirm, setShowEndConfirm] = useState(false)
  const [, setTick] = useState(0)

  const { data: session, isLoading, isError, refetch } = useQuery({
    queryKey: ['session', id],
    queryFn: () => getSession(id!),
    enabled: !!id,
  })

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

  if (isError || !session) {
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
              {' · '}{formatDuration(session.started_at, session.ended_at)}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
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
      {session.status === 'active' && (
        <div className="flex flex-col gap-4">
          {/* Mini stats */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatTile label="Total Bullets" value={bullets.length} />
            <StatTile label="AI Detected" value={bullets.filter(b => b.source === 'model').length} />
            <StatTile label="Manual" value={bullets.filter(b => b.source === 'manual').length} />
            <StatTile label="Duration" value={formatDuration(session.started_at, null)} />
          </div>

          {/* Stream + feed — fixed layout, neither column grows */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 items-start">
            {/* Camera feed — 2/3 */}
            <div className="lg:col-span-2">
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">Camera Feed</p>
              <WhepPlayer path="loopdemo" />
            </div>

            {/* Live bullet feed — 1/3, fixed height matching approx. video */}
            <div>
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">Live Detections</p>
              <div className="h-[420px] bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden shadow-sm dark:shadow-none flex flex-col">
                {/* Panel header */}
                <div className="shrink-0 px-4 py-2.5 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
                    Newest first
                  </span>
                  <span className="text-[10px] tabular-nums text-slate-400 dark:text-slate-500">
                    {bullets.length} detected
                  </span>
                </div>

                {/* Scrollable list or empty state */}
                {bullets.length === 0 ? (
                  <div className="flex-1 flex flex-col items-center justify-center gap-3">
                    <Crosshair size={28} className="text-slate-300 dark:text-slate-700" />
                    <p className="text-slate-400 dark:text-slate-600 text-sm">Waiting for detections…</p>
                  </div>
                ) : (
                  <ul className="flex-1 min-h-0 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800/60">
                    {[...bullets].reverse().map(b => (
                      <li key={b.id} className="px-4 py-2.5 flex items-start gap-3">
                        <span className="text-[10px] font-mono text-slate-400 dark:text-slate-600 w-5 shrink-0 pt-0.5 text-right">
                          {b.rank}
                        </span>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-0.5">
                            <SourceBadge source={b.source} />
                            <span className="text-xs font-medium text-slate-700 dark:text-slate-300">
                              {locationLabel(b)}
                            </span>
                          </div>
                          <p className="text-[10px] font-mono text-slate-400 dark:text-slate-600">
                            {formatTime(b.first_seen_at)}
                            {b.x_mm != null && b.y_mm != null && (
                              <>
                                <span className="mx-1 text-slate-300 dark:text-slate-700">·</span>
                                {mmLabel(b)}
                              </>
                            )}
                          </p>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
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

          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden shadow-sm dark:shadow-none">
            <div className="px-5 py-3.5 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                Bullet Log
                <span className="ml-2 text-xs font-normal text-slate-400 dark:text-slate-500">({bullets.length})</span>
              </h2>
            </div>

            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50">
                  <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider w-12">#</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Detected At</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Position</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Location</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Offset</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Source</th>
                  <th className="text-right px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                {bullets.length === 0 && (
                  <tr>
                    <td colSpan={7} className="py-16 text-center">
                      <div className="flex flex-col items-center gap-3">
                        <Crosshair size={32} className="text-slate-300 dark:text-slate-700" />
                        <p className="text-slate-500 dark:text-slate-500 text-sm">No bullets recorded</p>
                      </div>
                    </td>
                  </tr>
                )}
                {bullets.map(b => (
                  <tr key={b.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors">
                    <td className="px-4 py-3 text-slate-400 dark:text-slate-600 font-mono text-xs">{b.rank}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-600 dark:text-slate-300">{formatTime(b.first_seen_at)}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-500 dark:text-slate-400">
                      {b.position_x.toFixed(0)}, {b.position_y.toFixed(0)}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-600 dark:text-slate-400">{locationLabel(b)}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-500 dark:text-slate-400">{mmLabel(b)}</td>
                    <td className="px-4 py-3"><SourceBadge source={b.source} /></td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end">
                        <button
                          onClick={() => setDeleteTarget(b)}
                          className="p-1.5 text-slate-400 dark:text-slate-600 hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-400/10 rounded transition-colors"
                          title="Delete bullet"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <ConfirmDialog
        open={showEndConfirm}
        title="End Session"
        message={`End "${session.name}" now? The session will be marked as completed.`}
        confirmLabel="End Session"
        onConfirm={() => endMutation.mutate()}
        onCancel={() => setShowEndConfirm(false)}
        loading={endMutation.isPending}
      />

      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete Bullet"
        message={`Remove bullet #${deleteTarget?.rank ?? ''}? This cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={() => deleteTarget && deleteBulletMutation.mutate(deleteTarget.id)}
        onCancel={() => setDeleteTarget(null)}
        loading={deleteBulletMutation.isPending}
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
