// TEMPORARY debug capture (delete before production). Records the app's own
// view of a live camera — the <video> with the detection <svg> overlay drawn
// over it — by compositing both onto a canvas and recording that canvas. The
// result is what the operator sees on screen.

const FPS = 25
// How often the overlay picture is re-rasterised from the live SVG. The holes
// change rarely, so a few times a second keeps the video smooth and cheap.
const OVERLAY_REFRESH_MS = 200

// MediaRecorder records whatever the engine supports; the backend remuxes a
// WebM to MP4. MP4 first so no remux is needed where the engine can do it.
const MIME_TYPES = [
  'video/mp4;codecs=avc1',
  'video/mp4',
  'video/webm;codecs=vp9',
  'video/webm;codecs=vp8',
  'video/webm',
]

export interface AppViewRecording {
  stop: () => Promise<Blob>
}

function pickMimeType(): string | undefined {
  return MIME_TYPES.find(t => MediaRecorder.isTypeSupported(t))
}

// The live SVG as a canvas, so it can be drawn onto the recording. Cloned with
// an explicit size and namespace so it rasterises on its own; redrawn when the
// overlay changes. Decoded through an <img> (Chromium cannot createImageBitmap
// an SVG blob) onto an offscreen canvas, so the result survives the object URL
// being revoked. Plain shapes/text only — no external refs — so the canvas
// stays untainted and the recording can be read.
function rasteriseSvg(svg: SVGSVGElement, width: number, height: number): Promise<HTMLCanvasElement | null> {
  const clone = svg.cloneNode(true) as SVGSVGElement
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  clone.setAttribute('width', String(width))
  clone.setAttribute('height', String(height))
  clone.setAttribute('viewBox', `0 0 ${width} ${height}`)
  const xml = new XMLSerializer().serializeToString(clone)
  const url = URL.createObjectURL(new Blob([xml], { type: 'image/svg+xml' }))
  return new Promise<HTMLCanvasElement | null>(resolve => {
    const img = new Image()
    img.onload = () => {
      const off = document.createElement('canvas')
      off.width = width
      off.height = height
      off.getContext('2d')!.drawImage(img, 0, 0, width, height)
      URL.revokeObjectURL(url)
      resolve(off)
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      resolve(null) // a frame with no overlay beats a broken recording
    }
    img.src = url
  })
}

// Fit the video into the canvas the way object-contain does: centred, keeping
// its proportions, so the recording matches what is on screen (letterbox and all).
function containRect(vw: number, vh: number, cw: number, ch: number) {
  const scale = Math.min(cw / vw, ch / vh)
  const w = vw * scale
  const h = vh * scale
  return { x: (cw - w) / 2, y: (ch - h) / 2, w, h }
}

// Record the one live camera inside `container` (its <video> and overlay <svg>).
export function startAppViewRecording(container: HTMLElement): AppViewRecording {
  const video = container.querySelector('video')
  if (!video) throw new Error('no live video to record')
  // The overlay belongs to THIS video's player (its parent), not any other
  // camera tile in the container — so a hidden overlay on the first tile can't
  // pull another tile's detections onto this video.
  const player: ParentNode = video.parentElement ?? container

  const canvas = document.createElement('canvas')
  canvas.width = Math.max(2, video.clientWidth)
  canvas.height = Math.max(2, video.clientHeight)
  const ctx = canvas.getContext('2d')!

  let overlayBitmap: HTMLCanvasElement | null = null
  let refreshing = false
  const refresh = () => {
    // The detection overlay specifically — not a toolbar/status icon, which are
    // also <svg>. Absent when the overlay is off or the board is not watching.
    const svg = player.querySelector('svg[data-detection-overlay]')
    if (!svg || refreshing) {
      if (!svg) overlayBitmap = null
      return
    }
    refreshing = true
    rasteriseSvg(svg as SVGSVGElement, canvas.width, canvas.height)
      .then(bmp => { overlayBitmap = bmp })
      .finally(() => { refreshing = false })
  }
  refresh()
  const refreshTimer = window.setInterval(refresh, OVERLAY_REFRESH_MS)

  let raf = 0
  const draw = () => {
    // Follow the video element's current size, so a window resize or focus
    // change keeps the overlay (rasterised at the canvas size) aligned with the
    // video instead of stretching old coordinates into a stale canvas.
    const cw = Math.max(2, video.clientWidth)
    const ch = Math.max(2, video.clientHeight)
    if (canvas.width !== cw || canvas.height !== ch) {
      canvas.width = cw
      canvas.height = ch
      refresh() // re-rasterise the overlay at the new size
    }
    ctx.fillStyle = 'black'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    if (video.videoWidth > 0) {
      const r = containRect(video.videoWidth, video.videoHeight, canvas.width, canvas.height)
      ctx.drawImage(video, r.x, r.y, r.w, r.h)
    }
    if (overlayBitmap) ctx.drawImage(overlayBitmap, 0, 0, canvas.width, canvas.height)
    raf = requestAnimationFrame(draw)
  }
  raf = requestAnimationFrame(draw)

  const stream = canvas.captureStream(FPS)
  const mimeType = pickMimeType()
  const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
  const chunks: Blob[] = []
  recorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data) }
  recorder.start()

  return {
    stop: () =>
      new Promise<Blob>(resolve => {
        recorder.onstop = () => {
          cancelAnimationFrame(raf)
          window.clearInterval(refreshTimer)
          stream.getTracks().forEach(t => t.stop())
          resolve(new Blob(chunks, { type: mimeType ?? 'video/webm' }))
        }
        recorder.stop()
      }),
  }
}
