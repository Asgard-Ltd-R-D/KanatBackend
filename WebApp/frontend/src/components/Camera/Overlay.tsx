import { RefObject, useEffect, useState } from 'react'
import { BaselineView } from '../../types'
import { Size, templateToElement } from '../../utils/overlay'

const OUTLINE_COLOUR = '#22d3ee'

// The video's own size and its box's, followed as the player is resized and
// as the stream's picture loads or changes size
function useVideoSizes(videoRef: RefObject<HTMLVideoElement>) {
  const [sizes, setSizes] = useState<{ video: Size; element: Size } | null>(null)

  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    const measure = () =>
      setSizes({
        video: { width: video.videoWidth, height: video.videoHeight },
        element: { width: video.clientWidth, height: video.clientHeight },
      })
    measure()
    const box = new ResizeObserver(measure)
    box.observe(video)
    // Fired once the picture's size is known, and whenever it changes
    video.addEventListener('resize', measure)
    return () => {
      box.disconnect()
      video.removeEventListener('resize', measure)
    }
  }, [videoRef])

  return sizes
}

// The Overlay (ADR-0009): each Target's outline, labelled with its number,
// where the Run's baseline placed it on the picture. It covers the video
// exactly, and lets every click through to the player.
export function Overlay({ view, videoRef }: { view: BaselineView; videoRef: RefObject<HTMLVideoElement> }) {
  const sizes = useVideoSizes(videoRef)
  const toElement = sizes && templateToElement(view.template_to_picture, view.picture, sizes.video, sizes.element)
  if (!toElement) return null

  return (
    <svg className="absolute inset-0 w-full h-full pointer-events-none" aria-hidden>
      {view.targets.map((outline, i) => {
        const points = outline.map(toElement)
        if (points.length === 0) return null
        const top = points.reduce((a, b) => (b[1] < a[1] ? b : a))
        return (
          <g key={i}>
            <polygon
              points={points.map(p => p.join(',')).join(' ')}
              fill="none"
              stroke={OUTLINE_COLOUR}
              strokeWidth={2}
              strokeLinejoin="round"
            />
            <text
              x={top[0]}
              y={Math.max(top[1] - 6, 14)}
              textAnchor="middle"
              fontSize={12}
              fontWeight={600}
              fill={OUTLINE_COLOUR}
              stroke="black"
              strokeWidth={3}
              paintOrder="stroke"
            >
              Target {i + 1}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
