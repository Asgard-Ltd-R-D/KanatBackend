"""End to end: time a replay through MediaMTX, from each frame sent to the
operator's SSE (#279). Provisional on whatever host runs it: never the
production figure (SOW 2.3.4).

One command replays a recording into VideoService's MediaMTX, watches it live
as the Detection Service would, and posts into a WebApp Session it creates:

    python -m tools.end_to_end data/videos/CamB_20260915_102250.mkv --start 0 --end 46 \\
        --mm-per-px 0.1763 --device mps --out runs/279/default
    python -m tools.end_to_end ... --capture-options 'rtsp_transport;tcp' --decoder-threads 0

MediaMTX (`VideoService/`, Control API on 127.0.0.1:9997) and the WebApp
backend must be running. The replay is a process of its own (`_pace`): it
reads the recording from `--start`, stamps each frame's number in a 16-bit
strip and the wall clock it is sent at as text (top right, off every Board),
paces it at the recording's rate, and pipes it to ffmpeg, which encodes it as
the camera's settings say (H.264 Main, GOP 25, no B-frames, 8 Mbit/s,
live_camera.md) and publishes it. Its send time is when the frame went to the
encoder: encoding is in every "sent to decoded" figure, as a camera's is.

The pipeline runs in this process on the stream, through the Run's `opener`
seam, unchanged: a `Stream` that also notes, per frame taken, its stamp and
when. With the Look Times from `--timing`, the POST answer from the
publisher's log, and an SSE subscription standing in for the frontend, that
gives each stage per frame and per Bullet Hole (`stages`). Also counted: the
decoder's errors on stderr (frames decoded corrupt), and MediaMTX's RTP
packets discarded for this reader (`outboundRTPPacketsDiscarded`).

`--capture-options` sets `OPENCV_FFMPEG_CAPTURE_OPTIONS` for the run, in
place of the pipeline's `STREAM_CAPTURE_OPTIONS`; `--decoder-threads` the
reader's decoder threads, in place of its 1. The second example is the reader
before #279: OpenCV's default options and FFmpeg's choice of threads. Set, the
options replace OpenCV's default, `rtsp_transport;tcp`: give the transport
too, or the reader falls back to FFmpeg's, UDP first.

The model is loaded and warmed before the replay starts, as a Detection
Service's is after its first Run, so the reader joins the replay's first
keyframe after connecting, frame 25. A cold first call on MPS (seconds)
inside the baseline would hold the reader, and MediaMTX discard what it fell
behind by (#117).
"""
import argparse
import csv
import json
import logging
import os
import platform
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from typing import NamedTuple
from urllib.request import Request, urlopen

import cv2
import numpy as np

STAMP_BITS = 16          # 2^16 frames: 43 min at 25 fps
CELL = 16                # px a bit, square
MARGIN = 8               # px from the frame's top and right edges
CLOCK_H = 40             # px under the strip for the wall clock
DECODE_ERROR = re.compile(rb"error while decoding|concealing|corrupt", re.I)
MTX_API = "http://127.0.0.1:9997/v3"
MTX_RTSP = "rtsp://127.0.0.1:8554"
STAGES = ("sent to decoded", "Frame Wait", "Look Time", "Persistence", "posted",
          "delivered by SSE", "first-seen frame sent to delivered")


def _cells(width):
    """Each cell's left x: a white guard, the bits LSB first, a black guard."""
    x0 = width - MARGIN - (STAMP_BITS + 2) * CELL
    return [x0 + i * CELL for i in range(STAMP_BITS + 2)]


def stamp(image, n, sent):
    """Draw frame number `n` as a strip of cells, and `sent` as a clock under
    it, in place at the frame's top right: the strip for `read_stamp`, the
    clock for a human reading it off the WebApp's player."""
    xs = _cells(image.shape[1])
    bits = [1, *((n >> i) & 1 for i in range(STAMP_BITS)), 0]
    for x, b in zip(xs, bits):
        image[MARGIN:MARGIN + CELL, x:x + CELL] = 255 if b else 0
    text = datetime.fromtimestamp(sent).strftime("%H:%M:%S.%f")[:-3]
    y = MARGIN + CELL + CLOCK_H - 10
    image[MARGIN + CELL:MARGIN + CELL + CLOCK_H, xs[0]:xs[-1] + CELL] = 0
    cv2.putText(image, text, (xs[0] + 4, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)


def read_stamp(image):
    """The frame number `stamp` drew, or None: no strip, or a cell neither
    clearly black nor white, as a frame decoded corrupt may give."""
    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    q = CELL // 4
    levels = [grey[MARGIN + q:MARGIN + CELL - q, x + q:x + CELL - q].mean()
              for x in _cells(grey.shape[1])]
    if any(64 < v < 192 for v in levels) or levels[0] < 192 or levels[-1] > 64:
        return None
    return sum(1 << i for i, v in enumerate(levels[1:-1]) if v >= 192)


class Taken(NamedTuple):
    """A frame the loop took: its stream index, its stamp (None unread), the
    wall clock it was taken at, and its Frame Wait in s."""
    index: int
    stamp: int | None
    taken: float
    wait: float


class Hole(NamedTuple):
    """A reported Bullet Hole's wall clocks: Confirmed (published), its POST
    answered, its SSE event received. None for a step not seen."""
    first_frame: int
    confirmed: float
    posted: float | None
    delivered: float | None


def stages(sent, frames, looks, holes):
    """Each stage's durations in s, from `sent` (replay frame -> wall clock
    sent), `frames` (`Taken`, frame 0 first), `looks` (stream index -> Look
    Time ms, Looks past the baseline) and `holes` (`Hole`). A frame's replay
    number is its stamp; one unread, or not frame 0's plus its index, is a
    stamp mismatch, placed by the stamp if read, else by frame 0's plus its
    index."""
    first = next(f for f in frames if f.stamp is not None)   # frame 0's, unless it misread
    offset = first.stamp - first.index
    out = {k: [] for k in STAGES}
    out["stamp mismatches"] = 0
    done = {}   # index -> (sent, Look end)
    for f in frames:
        if f.stamp != offset + f.index:
            out["stamp mismatches"] += 1
        number = offset + f.index if f.stamp is None else f.stamp
        if f.index not in looks or number not in sent:
            continue
        decoded = f.taken - f.wait
        look = looks[f.index] / 1000
        out["sent to decoded"].append(decoded - sent[number])
        out["Frame Wait"].append(f.wait)
        out["Look Time"].append(look)
        done[f.index] = (sent[number], f.taken + look)
    for h in holes:
        if h.first_frame not in done:
            continue
        frame_sent, look_end = done[h.first_frame]
        out["Persistence"].append(h.confirmed - look_end)
        # Both from Confirmed: the backend publishes the SSE event before it
        # answers the POST, so the frontend can hear of a hole first.
        if h.posted is not None:
            out["posted"].append(h.posted - h.confirmed)
        if h.delivered is not None:
            out["delivered by SSE"].append(h.delivered - h.confirmed)
            out["first-seen frame sent to delivered"].append(h.delivered - frame_sent)
    return out


def _pace(video, start, end, url, sent_path):
    """The replay: `video` from `start` to `end` s, stamped, paced at its
    rate into ffmpeg, published at `url`. Writes `frame,sent` to `sent_path`."""
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(start * fps))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
         "-r", f"{fps:g}", "-i", "-", "-an", "-c:v", "libx264", "-preset", "medium",
         "-tune", "zerolatency", "-profile:v", "main", "-pix_fmt", "yuv420p", "-bf", "0",
         "-g", "25", "-keyint_min", "25", "-sc_threshold", "0", "-b:v", "8M", "-maxrate", "8M",
         "-bufsize", "8M", "-f", "rtsp", "-rtsp_transport", "tcp", url],
        stdin=subprocess.PIPE)
    sent = []
    t0 = time.time() + 0.5
    try:
        for i in range(int((end - start) * fps)):
            ok, frame = cap.read()
            if not ok:
                break
            time.sleep(max(0.0, t0 + i / fps - time.time()))
            now = time.time()
            stamp(frame, i, now)
            ffmpeg.stdin.write(frame.tobytes())
            sent.append((i, now))
    except BrokenPipeError:
        pass
    finally:
        ffmpeg.stdin.close()
        ffmpeg.wait()
        with open(sent_path, "w", newline="") as f:
            csv.writer(f).writerows([("frame", "sent"), *sent])


def _api(method, path, body=None, base=MTX_API):
    data = None if body is None else json.dumps(body).encode()
    request = Request(f"{base}{path}", data=data, method=method,
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=5) as response:
        text = response.read()
        return json.loads(text) if text else None


class _Tee:
    """Fd 2 through a pipe, copied to the console and its decoder errors
    counted: FFmpeg's C code writes there, past Python's sys.stderr."""

    def __init__(self):
        self.errors, self._console = 0, os.dup(2)
        read, write = os.pipe()
        os.dup2(write, 2)
        os.close(write)
        self._thread = threading.Thread(target=self._copy, args=(read,), daemon=True)
        self._thread.start()

    def _copy(self, fd):
        for line in os.fdopen(fd, "rb"):
            self.errors += bool(DECODE_ERROR.search(line))
            os.write(self._console, line)

    def close(self):
        sys.stderr.flush()
        os.dup2(self._console, 2)   # the pipe's last writer closes: the copy ends
        self._thread.join(2)


def _discards(path, stop, out):
    """Poll MediaMTX for this path's readers: their RTP packets discarded."""
    while not stop.wait(0.5):
        try:
            for s in _api("GET", "/rtspsessions/list")["items"]:
                if s["path"] == path and s["state"] == "read":
                    out[s["id"]] = s["outboundRTPPacketsDiscarded"]
        except Exception:
            pass   # MediaMTX busy: the next poll


def _subscribe(backend, session_id, delivered, stop, subscribed):
    """The frontend's SSE stream, each bullet_created noted by its `_key`.
    `subscribed` is set once the response starts: the backend subscribes
    before it (routers/live.py), so no event published after is missed."""
    with urlopen(f"{backend}/sessions/{session_id}/live", timeout=60) as stream:
        subscribed.set()
        for line in stream:
            if stop.is_set():
                return
            if line.startswith(b"data:") and b"bullet_created" in line:   # not a ping
                event = json.loads(line[5:])
                if event.get("type") == "bullet_created":
                    b = event["bullet"]
                    # The first: a retried POST's event is the same Bullet Hole again
                    delivered.setdefault(_key(b["first_seen_at"], b["position_x"], b["position_y"]),
                                         time.time())


def _key(at, x, y):
    """One Bullet Hole, as the publisher, its log and the SSE event all carry it:
    first_seen_at (a datetime or as written: UTC, truncated to the ms) and its
    position rounded to the px, since two Bullet Holes first seen on one frame
    share the time but lie a match radius apart (webapp._payload's key)."""
    if isinstance(at, str):
        at = datetime.fromisoformat(at.replace("Z", "+00:00"))
    return at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3], round(x), round(y)


class _Posted(logging.Handler):
    """The publisher's log: when each POST was answered, by `_key`."""

    def __init__(self):
        super().__init__()
        self.at = {}

    def emit(self, record):
        if getattr(record, "status", 0) in (200, 201):
            self.at[_key(record.first_seen_at, *record.position.values())] = record.created


def _row(name, values, unit=1000):
    v = np.asarray(values) * unit
    if not len(v):
        return f"| {name} | 0 | | | |"
    p50, p95 = np.percentile(v, (50, 95))
    return f"| {name} | {len(v)} | {p50:.0f} | {p95:.0f} | {v.max():.0f} |"


def main():
    from detection import logs
    from detection import new_bullet_holes as nbh
    from detection import webapp

    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("video")
    p.add_argument("--start", type=float, required=True)
    p.add_argument("--end", type=float, required=True,
                   help="the replay's end, s: allow a persistence window past the last Hit")
    p.add_argument("--mm-per-px", type=float)
    p.add_argument("--device")
    nbh.add_stride_flag(p)
    p.add_argument("--capture-options", help="OPENCV_FFMPEG_CAPTURE_OPTIONS, in place of the pipeline's")
    p.add_argument("--decoder-threads", type=int,
                   help="the stream reader's decoder threads (CAP_PROP_N_THREADS), in place "
                        "of the pipeline's 1; 0 is FFmpeg's choice")
    p.add_argument("--backend-url", default="http://localhost:8000")
    p.add_argument("--out", required=True, help="a directory for the CSVs")
    a = p.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if a.capture_options is not None:
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = a.capture_options
    logs.configure(to_file=False)
    if a.decoder_threads is not None:
        nbh.STREAM_DECODER_THREADS = a.decoder_threads
    posted = _Posted()
    logging.getLogger("detection.post").addHandler(posted)

    # A path of this run's own, deleted after it: no stale replay or other
    # publisher can be the stream the reader measures
    path = f"e2e-{os.urandom(4).hex()}"
    rtsp = f"{MTX_RTSP}/{path}"
    session = _api("POST", "/sessions", {"name": f"#279 {os.path.basename(a.out)}"},
                   base=a.backend_url)["id"]
    stop, subscribed, delivered, discarded = threading.Event(), threading.Event(), {}, {}
    pacer = tee = None
    added = False
    try:   # from here on, a failure still ends the Session, the replay and the path
        _api("POST", f"/config/paths/add/{path}", {"source": "publisher"})
        added = True
        threading.Thread(target=_subscribe, daemon=True,
                         args=(a.backend_url, session, delivered, stop, subscribed)).start()
        if not subscribed.wait(10):   # else a Bullet Hole could be posted before it, unseen
            raise RuntimeError("the Session's SSE stream did not open in 10 s")
        threading.Thread(target=_discards, args=(path, stop, discarded), daemon=True).start()

        # Warmed before the replay starts (see the module's doc)
        model = nbh.load_model(nbh.DEFAULT_MODEL)
        for _ in range(3):
            nbh._detect(model, [np.zeros((640, 640, 3), np.uint8)], 640, nbh.DEFAULT_CONFIDENCE, a.device)

        sent_path = os.path.join(a.out, "sent.csv")
        pacer = subprocess.Popen([sys.executable, "-c", "import sys; from tools.end_to_end import _pace; "
                                  "_pace(sys.argv[1], *map(float, sys.argv[2:4]), *sys.argv[4:])",
                                  a.video, str(a.start), str(a.end), rtsp, sent_path])
        while not _api("GET", f"/paths/get/{path}").get("ready"):
            if pacer.poll() is not None:
                raise RuntimeError(f"the replay exited (code {pacer.returncode}) before MediaMTX had it")
            time.sleep(0.1)

        taken = []

        class Traced(nbh.Stream):
            def read(self):
                frame = super().read()
                if frame is not None:
                    taken.append(Taken(frame.index, read_stamp(frame.image), time.time(), frame.wait))
                return frame

        def opener(video, start, ref_time):
            source, frame = Traced.open(video, start, ref_time)
            taken.append(Taken(0, read_stamp(frame), time.time(), 0.0))
            return source, frame

        confirmed = []   # (first frame, wall clock, first_seen_at key)

        tee = _Tee()
        with webapp.WebAppPublisher(session, a.backend_url) as publisher:
            def publish(value):
                confirmed.append((value.first_frame, time.time(),
                                  _key(value.first_seen_at, *value.template_xy)))
                publisher.publish(value)

            loop = nbh.RegisteredFrames.open(rtsp, None, model, device=a.device, opener=opener)
            threading.Thread(target=lambda: (pacer.wait(), loop.stop()), daemon=True).start()
            timing = os.path.join(a.out, "timing.csv")
            nbh.process(loop, None, mm_per_tpl_px=a.mm_per_px, stride=a.stride,
                        publish=publish, timing=timing)
            source = loop.source
        time.sleep(2)   # the last SSE events
    finally:
        if tee:
            tee.close()
        stop.set()
        if pacer and pacer.poll() is None:   # a failure: the replay is still publishing
            pacer.terminate()   # its ffmpeg sees its stdin close and exits
        if pacer:
            pacer.wait()
        # One active Session at a time: the next run needs this one ended
        try:
            _api("PATCH", f"/sessions/{session}", {"status": "completed"}, base=a.backend_url)
        finally:
            if added:
                _api("DELETE", f"/config/paths/delete/{path}")

    with open(sent_path) as f:
        sent = {int(r["frame"]): float(r["sent"]) for r in csv.DictReader(f)}
    with open(timing) as f:
        rows = csv.DictReader(line for line in f if not line.startswith("#"))
        looks = {int(r["frame"]): float(r["look_ms"]) for r in rows}
    holes = [Hole(first, at, posted.at.get(key), delivered.get(key))
             for first, at, key in confirmed]
    s = stages(sent, taken, looks, holes)

    with open(os.path.join(a.out, "frames.csv"), "w", newline="") as f:
        csv.writer(f).writerows([Taken._fields, *taken])
    with open(os.path.join(a.out, "holes.csv"), "w", newline="") as f:
        csv.writer(f).writerows([Hole._fields, *holes])
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                            text=True).stdout.strip()
    print(f"\n[E2E] PROVISIONAL, {platform.node()} ({platform.platform()}), {commit}, "
          f"detector on {a.device or 'default'}, OPENCV_FFMPEG_CAPTURE_OPTIONS="
          f"{os.environ.get('OPENCV_FFMPEG_CAPTURE_OPTIONS', nbh.STREAM_CAPTURE_OPTIONS)!r}, decoder threads "
          f"{nbh.STREAM_DECODER_THREADS}")
    print("| Stage, ms | n | P50 | P95 | max |\n|---|---:|---:|---:|---:|")
    for name in STAGES:
        print(_row(name, s[name]))
    first = s["sent to decoded"][0] if s["sent to decoded"] else float("nan")
    lost = sum(n for n, _ in source.upstream)
    print(f"[E2E] first frame past the baseline: sent to decoded {first:.2f} s; [LIVE]'s "
          f"behind {source.behind}, timestamps late {source._skew:.2f} s, live edge "
          f"{source.caught_up} s after watching")
    print(f"[E2E] {len(taken)} frame(s) taken, {source.late} dropped late, {lost} lost upstream, "
          f"{len(source.drops)} drop(s) before the end, {tee.errors} decoder error line(s), "
          f"{s['stamp mismatches']} stamp mismatch(es), MediaMTX discarded "
          f"{sum(discarded.values())} RTP packet(s) for this reader")
    print(f"[E2E] {len(holes)} Bullet Hole(s); Session {session}")


if __name__ == "__main__":
    main()
