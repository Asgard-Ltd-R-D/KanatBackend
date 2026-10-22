"""The Detection Service (CONTEXT.md, ADR-0008): a process that stays
running, loads the detector once, and starts and ends Runs for the WebApp
backend over a control API on 127.0.0.1 (#223).

    POST /runs {session_id, stream_url}   start the Session's Run; answered
                                          once it is watching
    POST /runs/{session_id}/end           end it; answered once its posts
                                          are drained
    GET  /status                          the Run, if any, and its state

A Run is the command line's live Run: `process` on a Stream, on a worker
thread, its Confirmed Bullet Holes posted by a `WebAppPublisher` of its own,
bound to its Session, on the unchanged v1 contract.
"""
import argparse
import json
import signal
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

from detection import new_bullet_holes as nbh
from detection import webapp

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
# (PERSIST_FRAMES at LIVE_FPS, 2 s) past the Look in hand, to the stride's
# Look that judges the last, ~3 s on the development Mac. Past it the Stream
# gave no frames to judge them on, and a Candidate still open is unconfirmable.
ENDING_TIMEOUT_S = 5   # PROVISIONAL

# The most points a Target's outline is sent in. A contour found in a frame
# runs to hundreds, and the Baseline View rides on every status read, every
# 5 s (ADR-0009); at the picture's scale a template px is a fraction of a px.
OUTLINE_POINTS = 64


class _Run:
    """A Run as `/status` reports it: its Session, its state (`starting`,
    `watching`, `ending`) and since when, and once watching its Baseline
    Marks counted and its Baseline View (ADR-0009). `ready` is set once it is
    watching or has failed, `ended` once it has ended and its posts are
    drained."""
    def __init__(self, session_id):
        self.session_id, self.baseline_marks, self.error = session_id, None, None
        self.baseline_view = None
        self.loop, self.ready, self.ended = None, threading.Event(), threading.Event()
        self.deadline = time.monotonic() + START_TIMEOUT_S
        self.enter("starting")

    def enter(self, state):
        self.state, self.since = state, datetime.now(timezone.utc)

    def view(self):
        return {"session_id": self.session_id, "state": self.state,
                "since": self.since.isoformat(), "baseline_marks": self.baseline_marks,
                "baseline_view": self.baseline_view}


class DetectionService:
    """Runs on `model`, a detector `load_model` loaded once for all of them,
    posting to the backend at `backend_url`. `opener` opens each Run's
    Stream, by default the command line's (`RegisteredFrames.open`).

    Each call answers `(HTTP status, JSON body)`, as the control API sends it.
    """
    def __init__(self, model, backend_url, opener=None):
        self._model, self._backend_url, self._opener = model, backend_url, opener
        self._lock = threading.Lock()
        # ponytail: one Run at a time; concurrent Runs need a detector each (#220)
        self._run = None

    def status(self):
        """The Run's `view`, or None."""
        with self._lock:
            return self._run and self._run.view()

    def start(self, session_id, stream_url):
        """The Session's Run, started unless it is already active, answered
        once it is watching. Another Session's active is a 409, and so is
        this Session's once it is ending. A Run that fails to start, or is
        not watching by `START_TIMEOUT_S`, is a 502 naming why, and leaves
        nothing behind."""
        with self._lock:
            run = self._run
            if run is None:
                run = self._run = _Run(session_id)
                print(f"[SERVICE] Session {session_id}: starting on {nbh._redacted(stream_url)}")
                threading.Thread(target=self._work, args=(run, stream_url), daemon=True,
                                 name=f"Run {session_id}").start()
            elif run.session_id != session_id:
                return 409, {"detail": "another Session's Run is active", "run": run.view()}
        if not run.ready.wait(max(0.0, run.deadline - time.monotonic())):
            self._end(run)
            return 502, {"detail": f"not watching within {START_TIMEOUT_S:g} s: "
                                   f"no baseline was built"}
        with self._lock:
            if run.error:
                return 502, {"detail": run.error}
            if run.state != "watching":
                return 409, {"detail": "the Session's Run is ending", "run": run.view()}
            return 200, run.view()

    def end(self, session_id):
        """End the Session's Run, answered once it has ended and its posts
        are drained. A watching Run first judges the Candidates it has open,
        opening none, for up to `ENDING_TIMEOUT_S` (#228); one still starting
        stops at once. No such Run is a 404."""
        with self._lock:
            run = self._run
            if run is None or run.session_id != session_id:
                return 404, {"detail": "no such Run"}
        self._end(run)
        return 200, {"session_id": session_id, "state": "ended"}

    def close(self):
        """End the Run, if any, as `end` does: how the service shuts down."""
        with self._lock:
            run = self._run
        if run:
            self._end(run)

    def _end(self, run):
        with self._lock:
            was, loop = run.state, run.loop
            if was != "ending":   # a repeat end waits on the first, its time kept
                run.enter("ending")
            # Flags only, so set under the lock: a Run that reads `ending` is
            # already finishing, or stopped
            if was == "watching":
                loop.finish()
            elif was == "starting" and loop:   # no baseline, so no Candidate yet
                loop.stop()
        if was == "watching" and not run.ended.wait(ENDING_TIMEOUT_S):
            loop.stop()   # harmless once it has finished and is draining
        run.ended.wait()

    def _work(self, run, stream_url):
        try:
            loop = nbh.RegisteredFrames.open(stream_url, None, self._model, opener=self._opener)
            with self._lock:
                run.loop = loop
                ending = run.state == "ending"   # ended while its Stream opened
            if ending:
                loop.stop()
            with webapp.WebAppPublisher(run.session_id, self._backend_url) as publisher:
                nbh.process(loop, None, publish=publisher.publish,
                            watching=lambda view, marks: self._watching(run, view, marks))
        except BaseException as error:   # SystemExit too: how a Run's open fails
            run.error = str(error) or type(error).__name__
            print(f"[SERVICE] Session {run.session_id}: the Run failed: {run.error}")
            if not isinstance(error, SystemExit):
                traceback.print_exc()
        finally:
            with self._lock:
                if self._run is run:
                    self._run = None
            print(f"[SERVICE] Session {run.session_id}: the Run has ended")
            run.ready.set()
            run.ended.set()

    def _watching(self, run, view, marks):
        baseline_view = _baseline_view(view, run.loop)
        with self._lock:
            run.baseline_marks, run.baseline_view = len(marks), baseline_view
            if run.state == "starting":
                run.enter("watching")
        print(f"[SERVICE] Session {run.session_id}: watching, {len(marks)} Baseline Mark(s)")
        run.ready.set()


def _baseline_view(view, loop):
    """Where the baseline frame, frame 0 of `loop`, showed Board space `view`
    in the camera's picture (ADR-0009): its time on `first_seen_at`'s clock,
    its size, the template's homography onto it, and each Target's outline in
    template coordinates, in `target_index` order."""
    height, width = loop.base.shape[:2]
    return {"taken_at": loop.wall_clock(0).astimezone(timezone.utc).isoformat(timespec="milliseconds"),
            "picture": {"width": width, "height": height},
            "template_to_picture": view.H.tolist(),
            "targets": [_outline(view.board_to_template(t)) for t in view.targets]}


def _outline(points):
    """A Target's outline cut to at most OUTLINE_POINTS of its own points, by
    simplifying it to within a template px, then two, four..."""
    points, tolerance = points.reshape(-1, 1, 2).astype("float32"), 1.0
    while len(cut := cv2.approxPolyDP(points, tolerance, True)) > OUTLINE_POINTS:
        tolerance *= 2
    return cut.reshape(-1, 2).astype(float).round(1).tolist()


def _start_body(raw):
    """`(session_id, stream_url)` from a start's body, the Session's UUID
    normalised, or None unless it is a Session's UUID and a Stream's URL."""
    try:
        body = json.loads(raw)
        session_id, url = str(uuid.UUID(body["session_id"])), body["stream_url"]
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    return (session_id, url) if isinstance(url, str) and nbh._is_stream(url) else None


def serve(service, port=DEFAULT_PORT):
    """The control API for `service`, bound to 127.0.0.1 only: it has no
    authentication, so nothing off this PC may reach it (ADR-0008). The
    caller runs its `serve_forever`."""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/status":
                self._answer(200, {"run": service.status()})
            else:
                self._answer(404, {"detail": "no such resource"})

        def do_POST(self):
            parts = self.path.strip("/").split("/")
            if parts == ["runs"]:
                body = _start_body(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                self._answer(*service.start(*body) if body else
                             (400, {"detail": "a JSON body with the Session's UUID as "
                                              "session_id and an rtsp:// or rtsps:// stream_url"}))
            elif len(parts) == 3 and parts[0] == "runs" and parts[2] == "end":
                try:
                    self._answer(*service.end(str(uuid.UUID(parts[1]))))
                except ValueError:
                    self._answer(404, {"detail": "no such Run"})
            else:
                self._answer(404, {"detail": "no such resource"})

        def _answer(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    p = argparse.ArgumentParser("The Detection Service: Runs the WebApp backend starts "
                                "and ends over a control API on 127.0.0.1 (ADR-0008)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT,
                   help=f"the control API's port on 127.0.0.1 (default: {DEFAULT_PORT})")
    p.add_argument("--model", default=nbh.DEFAULT_MODEL)
    p.add_argument("--backend-url", default="http://localhost:8000",
                   help="WebApp backend base URL (default: http://localhost:8000)")
    a = p.parse_args()
    service = DetectionService(nbh.load_model(a.model), a.backend_url)
    server = serve(service, a.port)
    print(f"[SERVICE] control API on http://127.0.0.1:{a.port}, detector {a.model}; "
          f"SIGINT or SIGTERM ends any Run as an end does, then the service")
    signal.signal(signal.SIGTERM, signal.default_int_handler)   # a stop, as Ctrl-C is
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        service.close()
