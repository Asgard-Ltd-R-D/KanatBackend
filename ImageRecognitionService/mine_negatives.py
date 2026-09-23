"""Background negatives from unsealed footage: gravel tiles with empty label files.

86% of raw detections land on gravel — dark specks on a light ground, which the
training set never contained as a negative (ADR-0003). The fix is images with
no annotation. This makes them from spent and threshold-work footage — the
sources ADR-0005 allows — and makes them safely:

- **Sealed footage is refused outright.** Every recording is looked up in the
  manifest by content hash; a sealed one stops the run, and unlike scoring
  there is no `--final-run` — a final run measures once, mining trains on it,
  and a checkpoint cannot un-see it (ADR-0005). An unallocated one stops it too.
- **The image is the one the runtime shows the model**: the rectified Board
  canvas at detection scale, cut into `TILE_PX` tiles so training does not
  rescale it. `TILE_PX` is the checkpoint's training `imgsz`.
- **Only ground survives.** An empty label file claims there is no Bullet Hole
  in the image, and the Board is covered in them — Misses on the paper included.
  So everything that is not gravel or dirt is blacked out, the way the warp
  already blacks out whatever lies beyond the frame. Tiles are taken where the
  ground is, most ground first.
- **Sparse.** One frame per `STEP_S`, and a tile that nearly repeats one already
  kept from the same Capture Setup is dropped: a static camera over static
  gravel is one image, however many frames — or files — show it.
- **Auditable.** `sources.csv` names the recording, hash, Capture Setup, role,
  frame and tile of every negative written. It is committed; the images are not.

The manifest's analysis `window` is not used. It bounds what is scored, and a
negative is scored against nothing: gravel is gravel anywhere in the clip.

    python mine_negatives.py videos/CamA_20260914_141446.mkv ... --out negatives/

A recording whose canvas holds no ground contributes nothing, and says so —
the CamB close-up is one: its canvas is all Board, so the runtime never shows
the model CamB gravel in the first place.
"""
import argparse
import csv
import os

import cv2
import numpy as np

import board
import manifest

TILE_PX = 960      # kanat_yolo26n_v1 trained at imgsz 960; match the checkpoint
STEP_S = 1.0       # PROVISIONAL: one candidate frame per second
DUP_MAD = 6.0      # PROVISIONAL: mean abs grey difference (0-255) at 32x32 below which
                   # two tiles are one image. Measured on CamA_141546, 2 s apart: one
                   # tile position repeats at 0.9-4.4, different positions differ at
                   # 12.9-14.6 (128x128 gives the same split, so 32 loses nothing)
MIN_GROUND = 0.25  # PROVISIONAL: a tile that is mostly black teaches the padding

# Ground is warm: gravel and dirt measure hue 13-20 (OpenCV 0-180), saturation
# 100-163, while the Board's paper, plywood and ring panel measure 102-110 on
# CamA — no overlap. Measured on one afternoon's light; another white balance
# may move both, which is why a canvas with no ground reports itself.
GROUND_HUE = (5, 35)     # PROVISIONAL
GROUND_MIN_SAT = 60      # PROVISIONAL
# Closing fills the dark specks inside gravel — they are the negative's whole
# point — and a blob smaller than MIN_BLOB_PX is a warm smudge or splinter on
# the Board, not ground. GUARD_PX then pulls the ground back from the Board's
# edge, past anything closing reached, so a Bullet Hole at its edge is black.
CLOSE_PX = 15            # PROVISIONAL
MIN_BLOB_PX = 20000      # PROVISIONAL: CamA's gravel strips run to 10^5 px
GUARD_PX = 15            # PROVISIONAL
# A gap enclosed by gravel and smaller than this is a rock or a shadow, not Board:
# rocks wider than CLOSE_PX would otherwise be blacked out, and they are the
# specks the detector mistakes for Bullet Holes. A Board is far larger.
MAX_ROCK_PX = 5000       # PROVISIONAL
MAX_CANVAS_PX = 4096     # beyond this the Board fit is wrong, not merely large
# ECC reaches 0.95-0.99 on every Kanat recording and 0.28-0.47 on the legacy
# clips, whose artwork is not the green Target: the hue gate latches onto dirt
# and the "Board" is a warp of the berm. Convergence, not geometric accuracy —
# which is all this asks: was the Target artwork found at all.
MIN_CORRELATION = 0.80   # PROVISIONAL
THUMB_PX = 32            # near-duplicate comparison size; see DUP_MAD

SOURCE_FIELDS = ["image", "sha256", "file", "capture_setup", "role", "frame",
                 "time_s", "x", "y", "w", "h", "ground_fraction"]


def refuse_sealed(entries, sha):
    """The manifest entry, if the recording may be mined. Sealed never may.

    Not `manifest.check_allowed`: its refusal offers `--final-run`, and here
    there is none to offer. Role lookup, and its errors, are the manifest's.
    """
    if manifest.role_for(entries, sha) == manifest.SEALED:
        raise SystemExit(
            f"[REFUSED] sha256 {sha} is sealed held-out footage (ADR-0005). No "
            "pixel of it may become a negative, not even gravel with an empty "
            "label: the background is the domain shift the sealed set measures, "
            "and a checkpoint cannot un-see it. There is no flag for this.")
    return entries[sha]


def ground_mask(canvas):
    """Gravel and dirt in a rectified canvas, as a bool mask."""
    hsv = cv2.cvtColor(canvas, cv2.COLOR_BGR2HSV)
    warm = cv2.inRange(hsv, (GROUND_HUE[0], GROUND_MIN_SAT, 1),
                       (GROUND_HUE[1], 255, 255))
    warm = cv2.morphologyEx(warm, cv2.MORPH_CLOSE, np.ones((CLOSE_PX, CLOSE_PX), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(warm)
    big = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= MIN_BLOB_PX]
    ground = np.isin(labels, big).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(1 - ground, connectivity=4)
    h, w = ground.shape
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        enclosed = x > 0 and y > 0 and x + bw < w and y + bh < h
        if enclosed and area <= MAX_ROCK_PX:
            ground[labels == i] = 1
    guard = np.ones((2 * GUARD_PX + 1, 2 * GUARD_PX + 1), np.uint8)
    # Eroding against a zero border would also pull back from the canvas edge,
    # which is gravel, not Board.
    ground = cv2.erode(ground, guard, borderType=cv2.BORDER_REPLICATE)
    return ground.astype(bool)


def usable_fit(canvas_size, correlation):
    """Did `build_view` find the Target artwork, rather than something green?"""
    return correlation >= MIN_CORRELATION and max(canvas_size) <= MAX_CANVAS_PX


def to_negative(canvas, ground=None):
    """The canvas with everything that is not ground blacked out."""
    ground = ground_mask(canvas) if ground is None else ground
    return np.where(ground[..., None], canvas, 0).astype(np.uint8)


def _starts(length, size):
    """Tile origins along one axis: half-tile steps, plus one flush with the end."""
    if length <= size:
        return [0]
    return sorted(set(range(0, length - size + 1, size // 2)) | {length - size})


def pick_tiles(ground, size=TILE_PX, min_fraction=MIN_GROUND):
    """`(x, y, ground_fraction)` tiles, most ground first, none half-overlapping."""
    h, w = ground.shape
    tw, th = min(size, w), min(size, h)
    candidates = sorted(((x, y, float(ground[y:y + th, x:x + tw].mean()))
                         for y in _starts(h, size) for x in _starts(w, size)),
                        key=lambda t: -t[2])
    picked = []
    for x, y, fraction in candidates:
        if fraction < min_fraction:
            break
        if all(max(0, tw - abs(x - px)) * max(0, th - abs(y - py)) <= tw * th / 2
               for px, py, _ in picked):
            picked.append((x, y, fraction))
    return picked


def thumbnail(tile):
    """What near-duplicates are compared on: grey, `THUMB_PX` square."""
    return cv2.resize(cv2.cvtColor(tile, cv2.COLOR_BGR2GRAY), (THUMB_PX, THUMB_PX),
                      interpolation=cv2.INTER_AREA).astype(np.float32)


def near_duplicate(thumb, kept, max_mad=DUP_MAD):
    """Does `thumb` nearly repeat any of the `kept` thumbnails?"""
    # ponytail: linear scan; a few dozen per Capture Setup. Index if it reaches thousands.
    return any(np.abs(thumb - k).mean() < max_mad for k in kept)


def pad_to_tile(tile, size=TILE_PX):
    """`tile` padded black to `size` square, never scaled.

    Training at `imgsz=size` would upscale a smaller tile, and the runtime never
    does: its `imgsz` is the canvas's own longest side. Black is what the warp
    already puts beyond the frame.
    """
    h, w = tile.shape[:2]
    return cv2.copyMakeBorder(tile, 0, size - h, 0, size - w, cv2.BORDER_CONSTANT, value=0)


def sample_indices(fps, n_frames, step_s=STEP_S):
    """Frame indices one `step_s` apart, from the first frame to the last."""
    step = max(1, round(fps * step_s))
    return list(range(0, n_frames, step))


def mine(video, sha, entry, out, writer, template_mask, kept, step_s=STEP_S):
    """Write every negative one recording yields. Returns how many.

    `kept` holds the thumbnails already written for this recording's Capture
    Setup, and grows: files of one setup repeat each other's gravel.
    """
    stem = os.path.splitext(os.path.basename(video))[0]
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    wanted = set(sample_indices(fps, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), step_s))
    written, repeats, looked, unusable, failed, index = 0, 0, 0, 0, 0, -1
    # Board space is fixed once per recording, as `RegisteredFrames.open` fixes
    # it, and tracked thereafter: rebuilding it per frame would rescale the
    # gravel whenever the reference contour's apparent size changed.
    reference = last = None
    while cap.grab():
        index += 1
        if index not in wanted:
            continue
        ok, frame = cap.retrieve()
        if not ok:
            continue
        looked += 1
        try:
            if reference is None:
                view, correlation = board.build_view(frame, template_mask)
            else:
                view, correlation = board.track_view(frame, template_mask, last)
        except cv2.error:
            failed += 1   # registration did not converge; counted, not folded in
            continue
        if view is None or not usable_fit(view.canvas_size, correlation):
            unusable += 1
            continue
        reference = reference or view
        last = view
        canvas = view.rectify(frame)
        ground = ground_mask(canvas)
        negative = to_negative(canvas, ground)
        for x, y, fraction in pick_tiles(ground):
            region = negative[y:y + TILE_PX, x:x + TILE_PX]
            tile = pad_to_tile(region)
            thumb = thumbnail(tile)
            if near_duplicate(thumb, kept):
                repeats += 1
                continue
            kept.append(thumb)
            written += 1
            # The hash keeps two same-named files from different folders apart.
            name = f"{stem}_{sha[:12]}_f{index:05d}_x{x}_y{y}"
            cv2.imwrite(os.path.join(out, "images", name + ".jpg"), tile)
            open(os.path.join(out, "labels", name + ".txt"), "w").close()
            writer.writerow({"image": name + ".jpg", "sha256": sha, "file": entry["file"],
                             "capture_setup": entry["capture_setup"], "role": entry["role"],
                             "frame": index, "time_s": f"{index / fps:.2f}",
                             "x": x, "y": y, "w": region.shape[1], "h": region.shape[0],
                             "ground_fraction": f"{fraction:.3f}"})
    cap.release()
    print(f"[MINE] {os.path.basename(video)} ({entry['capture_setup']}, {entry['role']}): "
          f"{written} negative(s) from {looked} sampled frame(s); "
          f"{repeats} tile(s) repeating its Capture Setup; "
          f"{unusable} without a usable Board, {failed} failed to register"
          + ("" if written or repeats or unusable + failed == looked
             else " — no ground in the canvas the runtime would show"))
    return written


if __name__ == "__main__":
    p = argparse.ArgumentParser("Background negatives from spent and threshold-work footage")
    p.add_argument("video", nargs="+")
    p.add_argument("--out", required=True, help="a new or empty directory")
    p.add_argument("--step", type=float, default=STEP_S, help="seconds between sampled frames")
    p.add_argument("--template", default=board.DEFAULT_TEMPLATE)
    a = p.parse_args()

    if os.path.isdir(a.out) and os.listdir(a.out):
        p.error(f"{a.out} is not empty; sources.csv must list every image beside it")
    # Every recording is cleared before any is read: a sealed one late in the
    # list must not arrive after the others have already been mined.
    entries = manifest.load()
    cleared = []
    for v in a.video:
        sha = manifest.content_hash(v)
        try:
            cleared.append((v, sha, refuse_sealed(entries, sha)))
        except manifest.ManifestError as why:
            raise SystemExit(f"[REFUSED] {os.path.basename(v)}: {why}")

    template = cv2.imread(a.template)
    _, template_mask = board.find_targets(template, min_area=1)
    for sub in ("images", "labels"):
        os.makedirs(os.path.join(a.out, sub), exist_ok=True)
    with open(os.path.join(a.out, "sources.csv"), "w", newline="") as f:
        writer = csv.DictWriter(f, SOURCE_FIELDS)
        writer.writeheader()
        kept = {}   # Capture Setup -> thumbnails written
        total = sum(mine(v, sha, entry, a.out, writer, template_mask,
                         kept.setdefault(entry["capture_setup"], []), a.step)
                    for v, sha, entry in cleared)
    print(f"[MINE] {total} negative(s) in {a.out}")
