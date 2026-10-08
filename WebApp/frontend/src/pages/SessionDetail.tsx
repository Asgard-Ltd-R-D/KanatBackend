import { useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, Square, Plus, Trash2, Download, FileText, FileSpreadsheet,
  Target as TargetIcon, AlertCircle, RefreshCw, Crosshair,
} from 'lucide-react'
import { format } from 'date-fns'
import { getSession, updateSession, exportUrl } from '../api/sessions'
import { deleteBullet } from '../api/bullets'
import { BulletHole } from '../types'
import { StatusBadge } from '../components/StatusBadge'
import { TargetOverlay } from '../components/TargetOverlay'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { AddBulletModal } from '../components/AddBulletModal'

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function formatDuration(a: string, b: string | null): string {
  const ms = (b ? new Date(b).getTime() : Date.now()) - new Date(a).getTime()
  const m = Math.floor(ms / 60000)
  const s = Math.floor((ms % 60000) / 1000)
  return `${m}m ${s}s`
}

function StatTile({ label, value, icon: Icon }: {
  label: string; value: string | number; icon?: React.ElementType
}) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl px-5 py-4">
      <div className="flex items-center gap-2 mb-2">
        {Icon && <Icon size={14} className="text-slate-500" />}
        <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">{label}</p>
      </div>
      <p className="text-2xl font-semibold text-slate-100">{value}</p>
    </div>
  )
}

export function SessionDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [showAddBullet, setShowAddBullet] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<BulletHole | null>(null)
  const [showEndConfirm, setShowEndConfirm] = useState(false)
  const [view, setView] = useState<'target' | 'table'>('target')

  const { data: session, isLoading, isError, refetch } = useQuery({
    queryKey: ['session', id],
    queryFn: () => getSession(id!),
    refetchInterval: (query) =>
      (query.state.data as { status?: string } | undefined)?.status === 'active' ? 5000 : false,
    enabled: !!id,
  })

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
      setDeleteTarget(null)
    },
  })

  if (isLoading) {
    return (
      <div className="p-8">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-6 h-6 bg-slate-800 rounded animate-pulse" />
          <div className="h-6 w-48 bg-slate-800 rounded animate-pulse" />
        </div>
        <div className="grid grid-cols-2 gap-4 mb-8">
          {[...Array(2)].map((_, i) => (
            <div key={i} className="bg-slate-900 border border-slate-800 rounded-xl px-5 py-4 h-24 animate-pulse" />
          ))}
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl h-96 animate-pulse" />
      </div>
    )
  }

  if (isError || !session) {
    return (
      <div className="p-8 flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <AlertCircle size={40} className="text-red-400" />
        <p className="text-slate-300 font-medium">Failed to load session</p>
        <div className="flex gap-3">
          <button onClick={() => refetch()} className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium rounded-lg transition-colors">
            <RefreshCw size={14} /> Retry
          </button>
          <button onClick={() => navigate('/')} className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium rounded-lg transition-colors">
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
      <div className="flex items-start justify-between mb-8">
        <div className="flex items-center gap-4">
          <Link
            to="/"
            className="p-2 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition-colors"
          >
            <ArrowLeft size={18} />
          </Link>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold text-slate-100">{session.name}</h1>
              <StatusBadge status={session.status} />
            </div>
            <p className="text-sm text-slate-500 mt-0.5">
              {format(new Date(session.started_at), 'EEEE, MMM d yyyy · HH:mm')}
              {session.ended_at && (
                <> · {formatDuration(session.started_at, session.ended_at)}</>
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {session.status === 'active' && (
            <button
              onClick={() => setShowEndConfirm(true)}
              className="flex items-center gap-2 px-4 py-2 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 text-amber-400 text-sm font-medium rounded-lg transition-colors"
            >
              <Square size={14} />
              End Session
            </button>
          )}

          {session.status === 'completed' && (
            <button
              onClick={() => setShowAddBullet(true)}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600/10 hover:bg-blue-600/20 border border-blue-600/30 text-blue-400 text-sm font-medium rounded-lg transition-colors"
            >
              <Plus size={14} />
              Add Bullet
            </button>
          )}

          {session.status === 'completed' && (
            <div className="flex items-center gap-1 pl-2 border-l border-slate-700">
              <a
                href={exportUrl(session.id, 'pdf')}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1.5 px-3 py-2 text-slate-400 hover:text-slate-200 hover:bg-slate-800 text-sm font-medium rounded-lg transition-colors"
                title="Export PDF"
              >
                <FileText size={14} />
                PDF
              </a>
              <a
                href={exportUrl(session.id, 'csv')}
                download
                className="flex items-center gap-1.5 px-3 py-2 text-slate-400 hover:text-slate-200 hover:bg-slate-800 text-sm font-medium rounded-lg transition-colors"
                title="Export CSV"
              >
                <Download size={14} />
                CSV
              </a>
              <a
                href={exportUrl(session.id, 'excel')}
                download
                className="flex items-center gap-1.5 px-3 py-2 text-slate-400 hover:text-slate-200 hover:bg-slate-800 text-sm font-medium rounded-lg transition-colors"
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
      <div className="grid grid-cols-2 gap-4 mb-8">
        <StatTile label="Total Bullets" value={bullets.length} icon={Crosshair} />
        <StatTile label="Duration" value={formatDuration(session.started_at, session.ended_at)} icon={TargetIcon} />
      </div>

      {/* View toggle */}
      <div className="flex items-center gap-1 mb-6 bg-slate-900 border border-slate-800 rounded-lg p-1 w-fit">
        <button
          onClick={() => setView('target')}
          className={`flex items-center gap-2 px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
            view === 'target' ? 'bg-slate-700 text-slate-100' : 'text-slate-500 hover:text-slate-300'
          }`}
        >
          <TargetIcon size={14} />
          Target View
        </button>
        <button
          onClick={() => setView('table')}
          className={`flex items-center gap-2 px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
            view === 'table' ? 'bg-slate-700 text-slate-100' : 'text-slate-500 hover:text-slate-300'
          }`}
        >
          <FileText size={14} />
          Bullet Log
        </button>
      </div>

      {/* Target view */}
      {view === 'target' && (
        <div className="grid grid-cols-3 gap-6">
          <div className="col-span-2 bg-slate-900 border border-slate-800 rounded-xl p-4">
            <div className="max-w-sm mx-auto">
              <TargetOverlay bullets={bullets} />
            </div>
          </div>

          {/* Bullet list */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
            <h3 className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-3">
              Bullets ({bullets.length})
            </h3>
            {bullets.length === 0 ? (
              <p className="text-slate-600 text-xs">No bullets yet</p>
            ) : (
              <div className="space-y-1 max-h-96 overflow-y-auto">
                {bullets.map((b) => (
                  <div key={b.id} className="flex items-center gap-2 py-1.5">
                    <span className="text-xs text-slate-600 font-mono w-5 text-right flex-shrink-0">
                      {b.rank}
                    </span>
                    <span className="text-xs text-slate-400 font-mono">
                      {b.position_x.toFixed(0)}, {b.position_y.toFixed(0)}
                    </span>
                    {b.source === 'manual' && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-700 text-slate-400 ml-auto flex-shrink-0">
                        M
                      </span>
                    )}
                    <span className={`text-xs text-slate-500 font-mono ${b.source !== 'manual' ? 'ml-auto' : ''}`}>
                      {formatTime(b.first_seen_at)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Bullet log table */}
      {view === 'table' && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800">
                <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Rank</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Time</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Position</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Source</th>
                <th className="text-right px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {bullets.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-16 text-center">
                    <div className="flex flex-col items-center gap-3">
                      <Crosshair size={32} className="text-slate-700" />
                      <p className="text-slate-500 text-sm">No bullets detected yet</p>
                      {session.status === 'active' && (
                        <p className="text-slate-600 text-xs">The detection model will report bullets automatically</p>
                      )}
                    </div>
                  </td>
                </tr>
              )}
              {bullets.map((b) => (
                <tr key={b.id} className="hover:bg-slate-800/40 transition-colors">
                  <td className="px-4 py-3 text-slate-600 font-mono text-xs">{b.rank}</td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-300">{formatTime(b.first_seen_at)}</td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-400">
                    {b.position_x.toFixed(1)}, {b.position_y.toFixed(1)}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      b.source === 'model'
                        ? 'bg-blue-500/10 text-blue-400'
                        : 'bg-slate-700 text-slate-400'
                    }`}>
                      {b.source}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end">
                      <button
                        onClick={() => setDeleteTarget(b)}
                        className="p-1.5 text-slate-600 hover:text-red-400 hover:bg-red-400/10 rounded transition-colors"
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
      )}

      <ConfirmDialog
        open={showEndConfirm}
        title="End Session"
        message={`End "${session.name}" now? The session will be marked as completed with ${bullets.length} bullet${bullets.length !== 1 ? 's' : ''} recorded. You can still export results after.`}
        confirmLabel="End Session"
        onConfirm={() => endMutation.mutate()}
        onCancel={() => setShowEndConfirm(false)}
        loading={endMutation.isPending}
      />

      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete Bullet"
        message={`Remove bullet #${deleteTarget ? (bullets.indexOf(deleteTarget) + 1) : ''}? This cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={() => deleteTarget && deleteBulletMutation.mutate(deleteTarget.id)}
        onCancel={() => setDeleteTarget(null)}
        loading={deleteBulletMutation.isPending}
      />

      <AddBulletModal
        open={showAddBullet}
        sessionId={session.id}
        onClose={() => setShowAddBullet(false)}
        onSuccess={() => qc.invalidateQueries({ queryKey: ['session', id] })}
      />
    </div>
  )
}
