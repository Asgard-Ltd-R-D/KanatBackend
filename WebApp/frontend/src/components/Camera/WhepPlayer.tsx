import { VideoOff, Loader2, RotateCcw } from 'lucide-react'
import { useWhepStream } from '../../hooks/useWhepStream'

interface WhepPlayerProps {
  path: string // MediaMTX path name, e.g. "camA"
  label?: string // shown over the video, top right
}

// Fills its container; the video keeps its proportions inside it
export function WhepPlayer({ path, label }: WhepPlayerProps) {
  const { videoRef, status, reason, reconnect, onPlaying } = useWhepStream(path)

  return (
    <div className="relative w-full h-full min-h-0 bg-black rounded-xl overflow-hidden">
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
          <p className="text-slate-400 text-sm">Connecting…</p>
        </div>
      )}

      {status === 'error' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/80">
          <VideoOff size={28} className="text-slate-600" />
          <div className="text-center">
            <p className="text-slate-400 text-sm">{reason ?? 'Stream unavailable'}</p>
            <p className="text-slate-600 text-xs mt-0.5">Retrying…</p>
          </div>
          <button
            onClick={reconnect}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium"
          >
            <RotateCcw size={14} /> Retry now
          </button>
        </div>
      )}

      {label && (
        <div className="absolute top-3 right-3 bg-black/60 rounded-full px-2.5 py-1">
          <span className="text-[11px] font-mono text-white/80">{label}</span>
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
