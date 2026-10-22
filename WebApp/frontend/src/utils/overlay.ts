// Where the Overlay draws (ADR-0009). Pure, so node --test checks it:
// npm test

export type Point = [number, number]

export interface Size {
  width: number
  height: number
}

// How far the video's proportions may stray from the picture's and still be
// the same picture: a decoder's few rows of padding, not another crop
const ASPECT_TOLERANCE = 0.01

// Maps a template point to element px: through `H`, a Run's
// template_to_picture, onto the baseline frame's `picture`, then into the
// rectangle object-contain shows the `video` in, inside an `element` of that
// size. Null while the video's size is unknown, or when its proportions
// differ from the picture's: then it is not the picture the Run saw.
export function templateToElement(
  H: number[][],
  picture: Size,
  video: Size,
  element: Size,
): ((p: Point) => Point) | null {
  if (!(video.width > 0 && video.height > 0)) return null
  const aspect = picture.width / picture.height
  if (Math.abs(video.width / video.height - aspect) > ASPECT_TOLERANCE * aspect) return null
  const scale = Math.min(element.width / video.width, element.height / video.height)
  const width = video.width * scale
  const height = video.height * scale
  const left = (element.width - width) / 2
  const top = (element.height - height) / 2
  return ([x, y]) => {
    const w = H[2][0] * x + H[2][1] * y + H[2][2]
    const px = (H[0][0] * x + H[0][1] * y + H[0][2]) / w
    const py = (H[1][0] * x + H[1][1] * y + H[1][2]) / w
    return [left + (px * width) / picture.width, top + (py * height) / picture.height]
  }
}
