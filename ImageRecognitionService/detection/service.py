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
import traceback
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from detection import new_bullet_holes as nbh
from detection import webapp

# The control API's port unless --port says otherwise: beside the backend's 8000,
# and clear of MediaMTX's, whose RTP and RTCP default to UDP 8000 and 8001.
DEFAULT_PORT = 8010


class _Run:
    """A Run as `/status` reports it: its Session, its state (`starting`,
    `watching`, `ending`) and since when, and its Baseline Marks once
    watching. `ready` is set once it is watching or has failed, `ended` once
    it has ended and its posts are drained."""
    def __init__(self, session_id):
        self.session_id, self.baseline_marks, self.error = session_id, None, None
        self.loop, self.ready, self.ended = None, threading.Event(), threading.Event()
        self.enter("starting")

    def enter(self, state):
        self.state, self.since = state, datetime.now(timezone.utc)

    def view(self):
        return {"session_id": self.session_id, "state": self.state,
                "since": self.since.isoformat(), "baseline_marks": self.baseline_marks}


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
        once it is watching. Another Session's active is a 409. A Run that
        fails to start is a 502 naming why, and leaves nothing behind."""
        with self._lock:
            run = self._run
            if run is None:
                run = self._run = _Run(session_id)
                print(f"[SERVICE] Session {session_id}: starting on {nbh._redacted(stream_url)}")
                threading.Thread(target=self._work, args=(run, stream_url), daemon=True,
                                 name=f"Run {session_id}").start()
            elif run.session_id != session_id:
                return 409, {"detail": "another Session's Run is active", "run": run.view()}
        run.ready.wait()
        if run.error:
            return 502, {"detail": run.error}
        with self._lock:
            return 200, run.view()

    def end(self, session_id):
        """End the Session's Run now, answered once it has ended and its
        posts are drained. No such Run is a 404."""
        with self._lock:
            run = self._run
            if run is None or run.session_id != session_id:
                return 404, {"detail": "no such Run"}
            if run.state != "ending":   # a repeat end keeps the first one's time
                run.enter("ending")
            loop = run.loop
        if loop:
            loop.stop()
        run.ended.wait()
        return 200, {"session_id": session_id, "state": "ended"}

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
                            watching=lambda marks: self._watching(run, marks))
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

    def _watching(self, run, marks):
        with self._lock:
            run.baseline_marks = marks
            if run.state == "starting":
                run.enter("watching")
        print(f"[SERVICE] Session {run.session_id}: watching, {marks} Baseline Mark(s)")
        run.ready.set()


def _start_body(raw):
    """`(session_id, stream_url)` from a start's body, the Session's UUID
    normalised, or None unless it is a Session's UUID and an rtsp:// URL."""
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
                                              "session_id and an rtsp:// stream_url"}))
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
          f"SIGINT or SIGTERM ends any Run, drained, then the service")
    signal.signal(signal.SIGTERM, signal.default_int_handler)   # a stop, as Ctrl-C is
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        run = service.status()
        if run:
            service.end(run["session_id"])
