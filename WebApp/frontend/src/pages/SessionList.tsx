import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Pencil, Trash2, ChevronRight, Target, AlertCircle, X, Check } from 'lucide-react'
import { format, isToday } from 'date-fns'
import { getSessions, createSession, updateSession, deleteSession } from '../api/sessions'
import { Session } from '../types'
import { StatusBadge } from '../components/StatusBadge'
import { ConfirmDialog } from '../components/ConfirmDialog'

function formatDuration(startedAt: string, endedAt: string | null): string {
  const start = new Date(startedAt).getTime()
  const end = endedAt ? new Date(endedAt).getTime() : Date.now()
  const ms = end - start
  const m = Math.floor(ms / 60000)
  const s = Math.floor((ms % 60000) / 1000)
  return `${m}m ${s}s`
}

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl px-5 py-4">
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-1">{label}</p>
      <p className="text-2xl font-semibold text-slate-100">{value}</p>
    </div>
  )
}

function SkeletonRow() {
  return (
    <tr>
      {[...Array(6)].map((_, i) => (
        <td key={i} className="px-4 py-4">
          <div className="h-4 bg-slate-800 rounded animate-pulse" style={{ width: `${60 + Math.random() * 40}%` }} />
        </td>
      ))}
    </tr>
  )
}

export function SessionList() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [newName, setNewName] = useState('')
  const [showNew, setShowNew] = useState(false)
  const [editId, setEditId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<Session | null>(null)

  const { data: sessions, isLoading, isError, refetch } = useQuery({
    queryKey: ['sessions'],
    queryFn: getSessions,
  })

  const createMutation = useMutation({
    mutationFn: () => createSession(newName.trim() || 'Unnamed Session'),
    onSuccess: (session) => {
      qc.invalidateQueries({ queryKey: ['sessions'] })
      setShowNew(false)
      setNewName('')
      navigate(`/sessions/${session.id}`)
    },
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

  const totalBullets = sessions?.reduce((s, sess) => s + (sess.bullet_count ?? 0), 0) ?? 0
  const activeSessions = sessions?.filter(s => s.status === 'active').length ?? 0
  const todaySessions = sessions?.filter(s => isToday(new Date(s.started_at))).length ?? 0

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100">Range Sessions</h1>
          <p className="text-sm text-slate-500 mt-0.5">Manage and review shooting sessions</p>
        </div>
        <button
          onClick={() => setShowNew(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors shadow-lg shadow-blue-600/20"
        >
          <Plus size={16} />
          New Session
        </button>
      </div>

      {/* New session modal */}
      {showNew && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setShowNew(false)} />
          <div className="relative bg-slate-900 border border-slate-800 rounded-xl shadow-2xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-slate-100">New Session</h3>
              <button onClick={() => setShowNew(false)} className="text-slate-500 hover:text-slate-300">
                <X size={20} />
              </button>
            </div>
            <input
              autoFocus
              type="text"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !createMutation.isPending && createMutation.mutate()}
              placeholder="Session name (e.g. Morning Range - Alpha)"
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500 mb-4"
            />
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowNew(false)}
                className="px-4 py-2 text-sm font-medium text-slate-300 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => createMutation.mutate()}
                disabled={createMutation.isPending}
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors disabled:opacity-50"
              >
                {createMutation.isPending ? 'Creating…' : 'Start Session'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Stats */}
      {sessions && sessions.length > 0 && (
        <div className="grid grid-cols-3 gap-4 mb-8">
          <StatCard label="Total Sessions" value={sessions.length} />
          <StatCard label="Active" value={activeSessions} />
          <StatCard label="Total Bullets" value={totalBullets} />
        </div>
      )}

      {/* Error */}
      {isError && (
        <div className="flex items-center gap-3 bg-red-500/10 border border-red-500/30 rounded-xl px-5 py-4 mb-6">
          <AlertCircle size={18} className="text-red-400 flex-shrink-0" />
          <p className="text-red-300 text-sm">Failed to load sessions.</p>
          <button onClick={() => refetch()} className="ml-auto text-red-400 hover:text-red-300 text-sm underline">
            Retry
          </button>
        </div>
      )}

      {/* Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-800">
              <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Session</th>
              <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Date</th>
              <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Duration</th>
              <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Status</th>
              <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Bullets</th>
              <th className="text-right px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {isLoading && [...Array(4)].map((_, i) => <SkeletonRow key={i} />)}

            {!isLoading && sessions?.length === 0 && (
              <tr>
                <td colSpan={6} className="py-20 text-center">
                  <div className="flex flex-col items-center gap-3">
                    <div className="w-14 h-14 rounded-full bg-slate-800 flex items-center justify-center">
                      <Target size={24} className="text-slate-600" />
                    </div>
                    <p className="text-slate-400 font-medium">No sessions yet</p>
                    <p className="text-slate-600 text-xs">Start your first session to begin tracking</p>
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
                className="hover:bg-slate-800/50 cursor-pointer group transition-colors"
              >
                {/* Name */}
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
                        className="bg-slate-800 border border-blue-500 rounded px-2 py-1 text-sm text-slate-100 focus:outline-none w-48"
                      />
                      <button
                        onClick={() => renameMutation.mutate({ id: session.id, name: editName })}
                        className="text-emerald-400 hover:text-emerald-300"
                      >
                        <Check size={14} />
                      </button>
                      <button onClick={() => setEditId(null)} className="text-slate-500 hover:text-slate-300">
                        <X size={14} />
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-slate-200 group-hover:text-white transition-colors">
                        {session.name}
                      </span>
                      <ChevronRight size={14} className="text-slate-600 group-hover:text-slate-400 transition-colors" />
                    </div>
                  )}
                </td>

                <td className="px-4 py-3.5 text-slate-400">
                  {format(new Date(session.started_at), 'MMM d, yyyy · HH:mm')}
                </td>

                <td className="px-4 py-3.5">
                  {session.status === 'active' ? (
                    <span className="flex items-center gap-1.5 text-emerald-400 text-xs">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      In progress
                    </span>
                  ) : (
                    <span className="text-slate-400">{formatDuration(session.started_at, session.ended_at)}</span>
                  )}
                </td>

                <td className="px-4 py-3.5">
                  <StatusBadge status={session.status} />
                </td>

                <td className="px-4 py-3.5 text-slate-300 font-mono text-sm">
                  {session.bullet_count ?? 0}
                </td>

                <td className="px-4 py-3.5" onClick={e => e.stopPropagation()}>
                  <div className="flex items-center justify-end gap-1">
                    <button
                      onClick={() => { setEditId(session.id); setEditName(session.name) }}
                      className="p-1.5 text-slate-500 hover:text-slate-300 hover:bg-slate-700 rounded transition-colors"
                      title="Rename"
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      onClick={() => setDeleteTarget(session)}
                      className="p-1.5 text-slate-500 hover:text-red-400 hover:bg-red-400/10 rounded transition-colors"
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
        message={`Are you sure you want to delete "${deleteTarget?.name}"? This will also delete all ${deleteTarget?.bullet_count ?? 0} bullet holes. This action cannot be undone.`}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
        onCancel={() => setDeleteTarget(null)}
        loading={deleteMutation.isPending}
      />
    </div>
  )
}
