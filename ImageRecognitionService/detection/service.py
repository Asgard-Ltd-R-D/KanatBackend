"""The Detection Service (CONTEXT.md, ADR-0008): a process that stays
running, loads the detector once, and starts and ends Runs for the WebApp
backend over a control API on 127.0.0.1 (#223).

    POST /runs {session_id, camera, stream_url}   start the Run on that
                                          camera's Stream; answered once it is
                                          watching
    POST /runs/{session_id}/{camera}/end  end it; answered once its posts
                                          are drained
    POST /runs/{session_id}/{camera}/stop the same, judging no Candidate it
                                          has open: a baseline retaken after
                                          a sheet is re-hung (#327)
    GET  /status                          every Run and its state, under
                                          `runs`, and the detector's device
                                          and model

A Session watches every enabled camera at once, so the service runs many Runs
concurrently, one per (session_id, camera): each is the command line's live
Run — `process` on its own Stream, on its own worker thread, registering its
own Board — and its Confirmed Bullet Holes are posted by a `WebAppPublisher`
of its own, naming its Session and camera, on the v2 contract. The one loaded
detector is shared behind an inference lock, so only one inference runs at a
time (the GPU serialises them anyway); everything else is per-Run and parallel.
"""
import argparse
import json
import logging
import signal
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

import cv2
import numpy as np

from detection import logs, webapp
from detection import new_bullet_holes as nbh

log = logging.getLogger("detection.service")

# The control API's port unless --port says otherwise: beside the backend's 8000,
# and clear of MediaMTX's, whose RTP and RTCP default to UDP 8000 and 8001.
DEFAULT_PORT = 8010

# How long a start waits for its Run to be watching before it ends the Run and
# fails: the Stream's open and first read, each bounded by STREAM_TIMEOUT_MS,
# then Board space and the baseline, ~2 s on the development Mac (#220). Past
# it the Stream gave frame 0 and then dropped, and reconnecting would hold the
# one Run for good.
START_TIMEOUT_S = 15   # PROVISIONAL

# How long an end lets a watching Run look on, judging the Candidates it has
# open, before it stops the Run as it stands (#228): one persistence window
# (PERSIST_FRAMES at LIVE_FPS, 1 s since #313) past the Look in hand, to the
# stride's Look that judges the last, ~3 s on the development Mac at the 2 s
# window it was measured with (#228). Past it the Stream
# gave no frames to judge them on, and a Candidate still open is unconfirmable.
ENDING_TIMEOUT_S = 5   # PROVISIONAL

# The most points a Target's outline is sent in. A contour found in a frame
# runs to hundreds, and the Baseline View rides on every status read, every
# 5 s (ADR-0009); at the picture's scale a template px is a fraction of a px.
OUTLINE_POINTS = 64


class _Run:
    """A Run as `/status` reports it: its Session and camera, its state
    (`starting`, `watching`, `ending`) and since when, and once watching its
    Baseline Marks counted, its Baseline View and how far it has watched
    (ADR-0009). `ready` is set once it is watching or has failed, `ended` once
    it has ended and its posts are drained. `dropping` once it is stopped
    (#327): nothing is posted from then on, the Look in hand's included."""
    def __init__(self, session_id, camera):
        self.session_id, self.camera = session_id, camera
        self.baseline_marks, self.error = None, None
        self.dropping = False
        self.baseline_view = None
        self.loop, self.ready, self.ended = None, threading.Event(), threading.Event()
        self.deadline = time.monotonic() + START_TIMEOUT_S
        self.enter("starting")

    def enter(self, state):
        self.state, self.since = state, datetime.now(timezone.utc)

    def view(self):
        return {"session_id": self.session_id, "camera": self.camera, "state": self.state,
                "since": self.since.isoformat(), "baseline_marks": self.baseline_marks,
                "baseline_view": self.baseline_view, **self.watched()}

    def watched(self):
        """`registered`, its latest registered Look's time and
        template_to_picture, and `looked_at`, its latest Look's time,
        registered or Lost: both None until it is watching (ADR-0009)."""
        if self.baseline_view is None:
            return {"registered": None, "looked_at": None}
        (index, view), looked = self.loop.registered, self.loop.looked
        return {"registered": {"at": _at(self.loop, index), "template_to_picture": view.H.tolist()},
                "looked_at": _at(self.loop, looked)}


def warm(model, device=None):
    """`model` called three times on a blank frame, before the service's
    control API answers or end_to_end's replay starts (#319): a cold first
    call (seconds on MPS, CUDA's setup on a GPU) would otherwise fall inside
    the first Run's baseline, holding its reader while MediaMTX discards what
    it fell behind by (#117). The service hands no `device`, as each Run's
    call is handed none, so it warms the device Runs use. Answers the device
    the detector resolved to, not what was asked for: handed none, `cuda:0`
    when CUDA is visible, else `cpu`. A failure is logged and raised: the
    service then never answers, so never reads as up."""
    started = time.perf_counter()
    try:
        for _ in range(3):
            nbh._detect(model, [np.zeros((640, 640, 3), np.uint8)], 640,
                        nbh.DEFAULT_CONFIDENCE, device)
        resolved = str(model.predictor.device)   # ultralytics' predictor, set up by the first call
    except Exception:
        log.exception("Detector warm-up failed")
        raise
    seconds = time.perf_counter() - started
    log.info("Detector warmed on %s in %.2f s", resolved, seconds,
             extra={"device": resolved, "seconds": round(seconds, 2)})
    return resolved


def model_name(path):
    """The name the status indicator shows for the weights at `path`: their
    training run's folder (`kanat_yolo26m_v1/weights/best.pt`), since every
    run's file is `best.pt`, else the file's own name less its extension."""
    path = Path(path)
    return path.parent.parent.name if path.parent.name == "weights" else path.stem


class DetectionService:
    """Runs on `model`, a detector `load_model` loaded once for all of them,
    posting to the backend at `backend_url`. `opener` opens each Run's
    Stream, by default the command line's (`RegisteredFrames.open`).
    `device` is the detector's, as `warm` answered it, and `model_name` its
    weights' `model_name`, both for `/status`.

    Each call answers `(HTTP status, JSON body)`, as the control API sends it.
    """
    def __init__(self, model, backend_url, opener=None, device=None, model_name=None):
        self._model, self._backend_url, self._opener = model, backend_url, opener
        self.device, self.model_name = device, model_name
        self._lock = threading.Lock()
        # Every active Run, keyed by (session_id, camera): a Session watches
        # every enabled camera at once, each on its own Stream and worker
        # thread (#341). They share the one loaded model, serialised by:
        self._inference_lock = threading.Lock()
        self._runs = {}

    def status(self):
        """Every Run's `view`, in the order they started; empty with none."""
        with self._lock:
            return [run.view() for run in self._runs.values()]

    def start(self, session_id, camera, stream_url):
        """The Run on this camera's Stream, started unless it is already
        active, answered once it is watching. Another Session's Run still
        active is a 409 (the backend keeps one Session; this holds the one Run
        a time per Session, so `current_session` is never another's); this
        Session's other cameras run concurrently. The same (session, camera)
        Run already ending is a 409. A Run that fails to start, or is not
        watching by `START_TIMEOUT_S`, is a 502 naming why, and leaves nothing
        behind."""
        key = (session_id, camera)
        with self._lock:
            other = next((r for r in self._runs.values() if r.session_id != session_id), None)
            if other is not None:
                log.warning("Run refused for session %s: another Session's Run is active", session_id,
                            extra={"session_id": session_id, "active_session_id": other.session_id})
                return 409, {"detail": "another Session's Run is active", "run": other.view()}
            run = self._runs.get(key)
            if run is None:
                run = self._runs[key] = _Run(session_id, camera)
                logs.current_session = session_id
                log.info("Run starting on %s for camera %s", nbh._redacted(stream_url), camera,
                         extra={"stream_url": nbh._redacted(stream_url), "camera": camera})
                threading.Thread(target=self._work, args=(run, stream_url), daemon=True,
                                 name=f"Run {session_id} {camera}").start()
        if not run.ready.wait(max(0.0, run.deadline - time.monotonic())):
            log.error("Run on camera %s not watching within %g s: no baseline was built, so it is ended",
                      camera, START_TIMEOUT_S, extra={"camera": camera})
            self._end(run)
            return 502, {"detail": f"not watching within {START_TIMEOUT_S:g} s: "
                                   f"no baseline was built"}
        with self._lock:
            if run.error:
                return 502, {"detail": run.error}
            if run.state != "watching":
                return 409, {"detail": "the Run is ending", "run": run.view()}
            return 200, run.view()

    def end(self, session_id, camera, judge=True):
        """End the Run on this camera, answered once it has ended and its posts
        are drained. A watching Run first judges the Candidates it has open,
        opening none, for up to `ENDING_TIMEOUT_S` (#228), unless `judge` is
        false: then they are dropped unposted, the re-hung sheet's change
        that opened them gone with its baseline (#327); one still starting
        stops at once. Answered with its Baseline View, which names it, and
        how far it watched, its last `registered` and `looked_at`. No such
        Run is a 404."""
        with self._lock:
            run = self._runs.get((session_id, camera))
            if run is None:
                return 404, {"detail": "no such Run"}
        log.info("Run on camera %s ending: judging the Candidates it has open, then draining its posts"
                 if judge else
                 "Run on camera %s stopping: dropping the Candidates it has open, then draining its posts",
                 camera, extra={"camera": camera})
        self._end(run, judge)
        return 200, {"session_id": session_id, "camera": camera, "state": "ended",
                     "baseline_view": run.baseline_view, **run.watched()}

    def close(self):
        """End every Run, as `end` does, in parallel: how the service shuts
        down."""
        with self._lock:
            runs = list(self._runs.values())
        threads = [threading.Thread(target=self._end, args=(run,)) for run in runs]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    def _end(self, run, judge=True):
        with self._lock:
            was, loop = run.state, run.loop
            if was != "ending":   # a repeat end waits on the first, its time kept
                run.enter("ending")
            if not judge:
                run.dropping = True
            # Flags only, so set under the lock: a Run that reads `ending` is
            # already finishing, or stopped
            if was == "watching" and judge:
                loop.finish()
            elif was in ("watching", "starting") and loop:   # starting: no baseline, so no Candidate yet
                loop.stop()
        if was == "watching" and not run.ended.wait(ENDING_TIMEOUT_S):
            loop.stop()   # harmless once it has finished and is draining
        run.ended.wait()

    def _work(self, run, stream_url):
        try:
            loop = nbh.RegisteredFrames.open(stream_url, None, self._model, opener=self._opener)
            loop.inference_lock = self._inference_lock   # the shared model, serialised
            with self._lock:
                run.loop = loop
                ending = run.state == "ending"   # ended while its Stream opened
            if ending:
                loop.stop()
            with webapp.WebAppPublisher(run.session_id, run.camera, self._backend_url) as publisher:
                def publish(hole):
                    # A stop's lands between Looks, so the Look in hand may
                    # still confirm one of the Candidates it drops
                    if run.dropping:
                        log.info("Bullet Hole not posted: the Run is stopping")
                    else:
                        publisher.publish(hole)
                nbh.process(loop, None, publish=publish,
                            watching=lambda view, marks: self._watching(run, view, marks))
        except BaseException as error:   # SystemExit too: how a Run's open fails
            run.error = str(error) or type(error).__name__
            # A SystemExit is how a Stream that cannot be opened or read says
            # so: its message is the whole story, with no traceback to add
            log.error("Run on camera %s failed: %s", run.camera, run.error,
                      exc_info=not isinstance(error, SystemExit), extra={"camera": run.camera})
        finally:
            log.info("Run on camera %s ended", run.camera, extra={"camera": run.camera})
            with self._lock:
                key = (run.session_id, run.camera)
                if self._runs.get(key) is run:
                    del self._runs[key]
                if not self._runs:
                    logs.current_session = None
            run.ready.set()
            run.ended.set()

    def _watching(self, run, view, marks):
        baseline_view = _baseline_view(view, run.loop, marks)
        with self._lock:
            run.baseline_marks, run.baseline_view = len(marks), baseline_view
            if run.state == "starting":
                run.enter("watching")
        log.info("Run on camera %s watching, %d Baseline Mark(s) on the Board", run.camera, len(marks),
                 extra={"camera": run.camera, "baseline_marks": len(marks)})
        run.ready.set()


def _baseline_view(view, loop, marks):
    """Where the baseline frame, frame 0 of `loop`, showed Board space `view`
    in the camera's picture (ADR-0009): its time on `first_seen_at`'s clock,
    its size, the template's homography onto it, and in template coordinates
    each Target's outline, in `target_index` order, and each of its Baseline
    Marks, `marks` in Board space."""
    height, width = loop.base.shape[:2]
    return {"taken_at": _at(loop, 0),
            "picture": {"width": width, "height": height},
            "template_to_picture": view.H.tolist(),
            "targets": [_outline(view.board_to_template(t)) for t in view.targets],
            "baseline_marks": view.board_to_template(marks[:, :2]).astype(float).round(1).tolist()}


def _at(loop, index):
    """Frame `index` of `loop`'s time, on `first_seen_at`'s clock."""
    return loop.wall_clock(index).astimezone(timezone.utc).isoformat(timespec="milliseconds")


def _outline(points):
    """A Target's outline cut to at most OUTLINE_POINTS of its own points, by
    simplifying it to within a template px, then two, four..."""
    points, tolerance = points.reshape(-1, 1, 2).astype("float32"), 1.0
    while len(cut := cv2.approxPolyDP(points, tolerance, True)) > OUTLINE_POINTS:
        tolerance *= 2
    return cut.reshape(-1, 2).astype(float).round(1).tolist()


def _start_body(raw):
    """`(session_id, camera, stream_url)` from a start's body, the Session's
    UUID normalised, or None unless it is a Session's UUID, a camera alias and
    a Stream's URL."""
    try:
        body = json.loads(raw)
        session_id = str(uuid.UUID(body["session_id"]))
        camera, url = body["camera"], body["stream_url"]
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    if isinstance(camera, str) and camera and isinstance(url, str) and nbh._is_stream(url):
        return (session_id, camera, url)
    return None


def serve(service, port=DEFAULT_PORT, host="127.0.0.1"):
    """The control API for `service`, bound to 127.0.0.1 by default: it has
    no authentication, so nothing off this PC may reach it (ADR-0008). In a
    container (Dockerfile) it binds 0.0.0.0 inside the container's network,
    which publishes no port to the PC's. The caller runs its
    `serve_forever`."""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/status":
                self._answer(200, {"runs": service.status(), "device": service.device,
                                   "model": service.model_name})
            else:
                self._answer(404, {"detail": "no such resource"})

        def do_POST(self):
            parts = self.path.strip("/").split("/")
            if parts == ["runs"]:
                body = _start_body(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                self._answer(*service.start(*body) if body else
                             (400, {"detail": "a JSON body with the Session's UUID as "
                                              "session_id, a camera alias as camera, and an "
                                              "rtsp:// or rtsps:// stream_url"}))
            elif len(parts) == 4 and parts[0] == "runs" and parts[3] in ("end", "stop"):
                try:
                    session_id = str(uuid.UUID(parts[1]))
                except ValueError:
                    self._answer(404, {"detail": "no such Run"})
                    return
                self._answer(*service.end(session_id, unquote(parts[2]), judge=parts[3] == "end"))
            else:
                self._answer(404, {"detail": "no such resource"})

        def log_message(self, format, *args):
            # Each request, the backend's status read every 5 s included
            log.debug(format, *args)

        def _answer(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return ThreadingHTTPServer((host, port), Handler)


if __name__ == "__main__":
    p = argparse.ArgumentParser("The Detection Service: Runs the WebApp backend starts "
                                "and ends over a control API on 127.0.0.1 (ADR-0008)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT,
                   help=f"the control API's port (default: {DEFAULT_PORT})")
    p.add_argument("--host", default="127.0.0.1",
                   help="the address the control API binds: 127.0.0.1 (default), or 0.0.0.0 "
                        "inside a container, whose network reaches it from the backend's only")
    p.add_argument("--model", default=nbh.DEFAULT_MODEL)
    # 127.0.0.1, not localhost: on Windows localhost tries IPv6 first, and
    # waits for it to fail on every post
    p.add_argument("--backend-url", default="http://127.0.0.1:8000",
                   help="WebApp backend base URL (default: http://127.0.0.1:8000)")
    p.add_argument("--log-dir", type=Path, default=None,
                   help=f"where to write {logs.LOG_FILE} (default: KANAT_LOG_DIR, "
                        "else the repo's WebApp/logs when it exists)")
    a = p.parse_args()
    log_file = logs.configure(a.log_dir)
    nbh.preset_capture_options()   # once, so the Runs' stream opens never race over it
    log.info("Loading the detector %s", a.model, extra={"log_file": str(log_file)})
    model = nbh.load_model(a.model)
    device = warm(model)   # before the control API binds: until warmed, nothing answers
    service = DetectionService(model, a.backend_url, device=device,
                               model_name=model_name(a.model))
    server = serve(service, a.port, a.host)
    log.info("Detection Service started: control API on http://%s:%d; SIGINT or SIGTERM "
             "ends any Run as an end does, then the service", a.host, a.port,
             extra={"host": a.host, "port": a.port, "model": a.model, "backend_url": a.backend_url,
                    "device": device})
    signal.signal(signal.SIGTERM, signal.default_int_handler)   # a stop, as Ctrl-C is
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        log.info("Detection Service stopping")
        server.server_close()
        service.close()
