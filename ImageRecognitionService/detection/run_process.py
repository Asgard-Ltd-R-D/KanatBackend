"""A Run in a process of its own (`python -m detection.service --run-mode process`).

By default the Detection Service runs each Run on a thread of its own, all of
them on the one loaded detector behind an inference lock (service.py). This is
the alternative to compare it with: each (session, camera) Run is its own
process, with its own copy of the detector on the GPU, its own Python
interpreter (so no GIL shared with the other cameras) and nothing shared with the
other Runs but the GPU.

The service starts `main` in a spawned process and talks to it over a Pipe:

    service -> Run   "finish"  judge the Candidates open, then end (an end)
                     "stop"    end after the Look in hand (a stop, or any end of
                               a Run still starting)
                     "drop"    post nothing more (a stop judges no Candidate)
    Run -> service   ("watching", baseline_view, marks)   the baseline is built
                     ("watched", {registered, looked_at}) how far it has watched,
                                                          every WATCHED_EVERY_S
                     ("input", stream_is_down)            whether its Stream is down, as often
                     ("draining",)                        it has looked at its last frame and is posting
                                                          what it confirmed (up to the publisher's limit)
                     ("error", why)                       it failed
                     ("ended",)                           it ended, posts drained

The Run's own work is the thread Run's, line for line: `RegisteredFrames.open`,
`process`, a `WebAppPublisher` posting its Bullet Holes to the backend.
"""
import faulthandler
import logging
import os
import threading
import time

from detection import board, logs, webapp
from detection import new_bullet_holes as nbh

log = logging.getLogger("detection.run")

# How often a Run tells the service how far it has watched, for `/status`
WATCHED_EVERY_S = 0.1
# After this long opening the Stream and building the baseline, the Run dumps
# every thread's stack: normally ~2 s, so past it something is stuck
HANG_DUMP_S = 10
# How long a Run whose service has gone gets to end before its process exits
GONE_EXIT_S = 15


def main(conn, model_path, session_id, camera, stream_url, backend_url, log_dir):
    # Imported here, not at the top: service.py imports this module
    from detection import service

    logs.configure(log_dir)
    logs.current_session = session_id
    send_lock = threading.Lock()

    def send(*message):
        with send_lock:
            try:
                conn.send(message)
            except (OSError, ValueError):   # the service is gone
                pass

    state = {"loop": None, "pending": None, "dropping": False}
    state_lock = threading.Lock()

    def apply(loop, command):
        if command == "finish":
            loop.finish()
        elif command == "stop":
            loop.stop()

    def commands():
        while True:
            try:
                command = conn.recv()
            except (EOFError, OSError):
                command = "stop"   # the service is gone: end as a stop does
                # and never outlive it: a Run that cannot end (stuck, or draining
                # posts to nobody) would hold its memory and the GPU for good
                threading.Timer(GONE_EXIT_S, os._exit, args=(1,)).start()
            with state_lock:
                if command == "drop":
                    state["dropping"] = True
                elif state["loop"] is None:   # still loading or opening: applied once it is open
                    state["pending"] = command
                else:
                    apply(state["loop"], command)
            if command == "stop":
                return

    threading.Thread(target=commands, daemon=True, name="Run commands").start()

    report_lock = threading.Lock()   # a report is never sent after the final one

    def report(loop):
        if loop.looked is not None and state.get("watching"):
            send("watched", service._watched_of(loop))
            # And whether its Stream is down: what tells a Run with no video
            # to look at from one that is stuck
            send("input", bool(getattr(loop.source, "down", False)))

    def report_watched(loop):
        while True:
            with report_lock:
                if state.get("done"):
                    return
                report(loop)
            time.sleep(WATCHED_EVERY_S)

    try:
        nbh.preset_capture_options()
        began = time.perf_counter()
        model = nbh.load_model(model_path)
        service.warm(model)
        log.info("Run process on camera %s: detector loaded and warmed in %.1f s", camera,
                 time.perf_counter() - began, extra={"camera": camera})
        # A Run that has not built its baseline by then is stuck: say where, once,
        # on the service's stderr (every thread's stack), so a hang can be read
        faulthandler.dump_traceback_later(HANG_DUMP_S, exit=False)
        loop = nbh.RegisteredFrames.open(stream_url, None, model)
        with state_lock:
            state["loop"] = loop
            pending = state["pending"]
        if pending:
            apply(loop, pending)
        threading.Thread(target=report_watched, args=(loop,), daemon=True, name="Run watched").start()

        def watching(view, marks):
            faulthandler.cancel_dump_traceback_later()
            send("watching", service._baseline_view(view, loop, marks), len(marks))
            state["watching"] = True

        with webapp.WebAppPublisher(session_id, camera, backend_url) as publisher:
            def publish(hole):
                if state["dropping"]:
                    log.info("Bullet Hole not posted on camera %s: the Run is stopping", camera,
                             extra={"camera": camera})
                else:
                    publisher.publish(hole)
            try:
                nbh.process(loop, None, mm_per_tpl_px=board.live_print_scale(), publish=publish,
                            watching=watching)
            finally:
                # Looking is over, whether it ended or failed: the publisher's exit drains its posts
                # next, which has its own time limit and is not a stall
                send("draining")
    except BaseException as error:   # SystemExit too: how a Run's open fails
        why = str(error) or type(error).__name__
        log.error("Run on camera %s failed: %s", camera, why,
                  exc_info=not isinstance(error, SystemExit), extra={"camera": camera})
        send("error", why)
    finally:
        faulthandler.cancel_dump_traceback_later()
        with report_lock:
            state["done"] = True
            # Where it watched to at its last Look, which may fall between two reports: what
            # `end` answers and the backend keeps as how far the Run watched
            if state["loop"] is not None:
                report(state["loop"])
        send("ended")
        try:
            conn.close()
        except OSError:
            pass
