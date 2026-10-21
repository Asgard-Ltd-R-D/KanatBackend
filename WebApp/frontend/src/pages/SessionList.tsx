import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Pencil, Trash2, ChevronRight, Target, AlertCircle, X, Check } from 'lucide-react'
import { format } from 'date-fns'
import { getSessions, updateSession, deleteSession } from '../api/sessions'
import { Session } from '../types'
import { StatusBadge } from '../components/UI/StatusBadge'
import { ConfirmDialog } from '../components/UI/ConfirmDialog'
import { NewSessionModal } from '../components/Session/NewSessionModal'
import { StatTile } from '../components/UI/StatTile'
import { formatDuration } from '../utils/format'

const SKELETON_WIDTHS = ['65%', '55%', '40%', '30%', '25%', '20%']

function SkeletonRow() {
  return (
    <tr>
      {SKELETON_WIDTHS.map((w, i) => (
        <td key={i} className="px-4 py-4">
          <div className="h-4 bg-slate-100 dark:bg-slate-800 rounded animate-pulse" style={{ width: w }} />
        </td>
      ))}
    </tr>
  )
}

export function SessionList() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [showNew, setShowNew] = useState(false)
  const [editId, setEditId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<Session | null>(null)

  const { data: sessions, isLoading, isError, refetch } = useQuery({
    queryKey: ['sessions'],
    queryFn: getSessions,
  })

  const renameMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => updateSession(id, { name }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sessions'] })
      setEditId(null)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteSession(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sessions'] })
      setDeleteTarget(null)
    },
  })

  const totalBullets = sessions?.reduce((s, sess) => s + (sess.status === 'active' ? 0 : (sess.bullet_count ?? 0)), 0) ?? 0
  const activeSessions = sessions?.filter(s => s.status === 'active').length ?? 0

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">Sessions</h1>
        </div>
        <button
          onClick={() => setShowNew(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors shadow-lg shadow-blue-600/20"
        >
          <Plus size={16} />
          New Session
        </button>
      </div>

      <NewSessionModal open={showNew} onClose={() => setShowNew(false)} />

      {/* Stats */}
      {sessions && sessions.length > 0 && (
        <div className="grid grid-cols-3 gap-4 mb-8">
          <StatTile label="Total Sessions" value={sessions.length} />
          <StatTile label="Active" value={activeSessions} />
          <StatTile label="Total Bullets" value={totalBullets} />
        </div>
      )}

      {/* Error */}
      {isError && (
        <div className="flex items-center gap-3 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 rounded-xl px-5 py-4 mb-6">
          <AlertCircle size={18} className="text-red-500 dark:text-red-400 flex-shrink-0" />
          <p className="text-red-700 dark:text-red-300 text-sm">Failed to load sessions</p>
          <button onClick={() => refetch()} className="ml-auto text-red-500 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 text-sm underline">
            Retry
          </button>
        </div>
      )}

      {/* Table */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden shadow-sm dark:shadow-none">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900">
              <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 dark:text-slate-500 uppercase tracking-wider">Session</th>
              <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 dark:text-slate-500 uppercase tracking-wider">Date</th>
              <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 dark:text-slate-500 uppercase tracking-wider">Duration</th>
              <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 dark:text-slate-500 uppercase tracking-wider">Status</th>
              <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 dark:text-slate-500 uppercase tracking-wider">Bullets</th>
              <th className="text-right px-4 py-3 text-xs font-medium text-slate-500 dark:text-slate-500 uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
            {isLoading && [...Array(4)].map((_, i) => <SkeletonRow key={i} />)}

            {!isLoading && sessions?.length === 0 && (
              <tr>
                <td colSpan={6} className="py-20 text-center">
                  <div className="flex flex-col items-center gap-3">
                    <div className="w-14 h-14 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center">
                      <Target size={24} className="text-slate-400 dark:text-slate-600" />
                    </div>
                    <p className="text-slate-600 dark:text-slate-400 font-medium">No sessions yet</p>
                    <button
                      onClick={() => setShowNew(true)}
                      className="mt-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors"
                    >
                      Start First Session
                    </button>
                  </div>
                </td>
              </tr>
            )}

            {sessions?.map(session => (
              <tr
                key={session.id}
                onClick={() => navigate(`/sessions/${session.id}`)}
                className="hover:bg-slate-50 dark:hover:bg-slate-800/50 cursor-pointer group transition-colors"
              >
                <td className="px-4 py-3.5" onClick={e => editId === session.id && e.stopPropagation()}>
                  {editId === session.id ? (
                    <div className="flex items-center gap-2" onClick={e => e.stopPropagation()}>
                      <input
                        autoFocus
                        value={editName}
                        onChange={e => setEditName(e.target.value)}
                        onKeyDown={e => {
                          if (e.key === 'Enter') renameMutation.mutate({ id: session.id, name: editName })
                          if (e.key === 'Escape') setEditId(null)
                        }}
                        className="bg-slate-50 dark:bg-slate-800 border border-blue-500 rounded px-2 py-1 text-sm text-slate-900 dark:text-slate-100 focus:outline-none w-48"
                      />
                      <button onClick={() => renameMutation.mutate({ id: session.id, name: editName })} className="text-emerald-600 dark:text-emerald-400 hover:text-emerald-700 dark:hover:text-emerald-300">
                        <Check size={14} />
                      </button>
                      <button onClick={() => setEditId(null)} className="text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300">
                        <X size={14} />
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-slate-800 dark:text-slate-200 group-hover:text-slate-900 dark:group-hover:text-white transition-colors">
                        {session.name}
                      </span>
                      <ChevronRight size={14} className="text-slate-400 dark:text-slate-600 group-hover:text-slate-500 dark:group-hover:text-slate-400 transition-colors" />
                    </div>
                  )}
                </td>

                <td className="px-4 py-3.5 text-slate-500 dark:text-slate-400">
                  {format(new Date(session.started_at), 'MMM d, yyyy · HH:mm')}
                </td>

                <td className="px-4 py-3.5">
                  {session.status === 'active' ? (
                    <span className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 text-xs">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 dark:bg-emerald-400 animate-pulse" />
                      In progress
                    </span>
                  ) : (
                    <span className="text-slate-500 dark:text-slate-400">{formatDuration(session.started_at, session.ended_at)}</span>
                  )}
                </td>

                <td className="px-4 py-3.5">
                  <StatusBadge status={session.status} />
                </td>

                <td className="px-4 py-3.5 text-slate-700 dark:text-slate-300 font-mono text-sm">
                  {session.status === 'active' ? '—' : (session.bullet_count ?? 0)}
                </td>

                <td className="px-4 py-3.5" onClick={e => e.stopPropagation()}>
                  <div className="flex items-center justify-end gap-1">
                    <button
                      onClick={() => { setEditId(session.id); setEditName(session.name) }}
                      className="p-1.5 text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded transition-colors"
                      title="Rename"
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      onClick={() => setDeleteTarget(session)}
                      className="p-1.5 text-slate-400 dark:text-slate-500 hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-400/10 rounded transition-colors"
                      title="Delete"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete Session"
        message={`Delete "${deleteTarget?.name}" with its bullets and video? This cannot be undone.`}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
        onCancel={() => {
          setDeleteTarget(null)
          deleteMutation.reset()
        }}
        loading={deleteMutation.isPending}
        error={deleteMutation.error?.message}
      />
    </div>
  )
}
