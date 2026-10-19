import { VideoOff, Loader2, RotateCcw } from 'lucide-react'
import { useWhepStream } from '../../hooks/useWhepStream'

interface WhepPlayerProps {
  path: string // MediaMTX path name, e.g. "camA"
}

export function WhepPlayer({ path }: WhepPlayerProps) {
  const { videoRef, status, reason, reconnect, onPlaying } = useWhepStream(path)

  return (
    <div className="relative w-full aspect-video bg-black rounded-xl overflow-hidden">
      <video
        ref={videoRef}
        autoPlay
        muted
        playsInline
        onPlaying={onPlaying}
        className="w-full h-full object-contain"
      />

      {status === 'loading' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/80">
          <Loader2 size={28} className="text-slate-400 animate-spin" />
          <p className="text-slate-400 text-sm">Connecting to stream…</p>
        </div>
      )}

      {status === 'error' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/80">
          <VideoOff size={28} className="text-slate-600" />
          <p className="text-slate-500 text-sm">{reason ?? 'Stream unavailable'}</p>
          <button
            onClick={reconnect}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium"
          >
            <RotateCcw size={14} /> Reconnect
          </button>
        </div>
      )}

      {status === 'playing' && (
        <div className="absolute top-3 left-3 flex items-center gap-1.5 bg-black/60 rounded-full px-2.5 py-1">
          <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
          <span className="text-[10px] font-medium text-white/80 uppercase tracking-wider">Live</span>
        </div>
      )}
    </div>
  )
}
