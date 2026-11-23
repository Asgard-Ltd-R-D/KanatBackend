"""The Detection Service's stall check: ends a Run that is alive but looks at
nothing, and, in thread mode, exits the service for its supervisor to start it
again when a thread cannot be stopped. `DetectionService` (service.py) is a
`StallChecks`, and supplies what these methods use: `_runs`, `_lock`,
`_closing`, `_end`, `_retire` and `drain_limit_s`.

Nothing here imports the detector's libraries: the supervisor reads its default
`STALL_AFTER_S` from here.
"""
import logging
import os
import re
import sys
import threading
import time
import traceback

log = logging.getLogger("detection.stalls")

# A watching Run that looks at no frame for this long is stalled (stuck on its
# Stream, a lock or the GPU, but alive, which `is_alive` cannot tell from a
# healthy one): it is ended, and the backend's reconcile starts it again.
# Measured with 4 Runs on 1080p streams, in both modes, 3 minutes each, with a
# Run ended and started again among them: a healthy Run's longest wait between
# two looks was 0.76 s. It was 10 s, but under load the silhouette check's
# alignment (cv2.findTransformECC, once or twice a look, on every Run at once)
# kept a healthy Run past that and restarted every camera: three stall dumps all
# sat in it. It is 60 s: a thread-mode stall
# restarts every camera, so a false alarm costs as much as a real one.
STALL_AFTER_S = 60
# A Run that looks at nothing because its camera is down (the Stream reopens
# itself) is not stuck: it is waited for, and only past this long is it ended,
# alone and never with the service, for the backend to start again
CAMERA_DOWN_AFTER_S = 120   # PROVISIONAL
STALL_CHECK_EVERY_S = 1
# When a stuck thread makes the service exit, the other Runs are first given this
# long to judge their open Candidates and post what they hold: a shot confirmed
# but not yet sent is otherwise lost with the exit. The stuck Run may hold what
# they need (the GPU, the model's lock), so it is a bounded try, never a wait.
EXIT_DRAIN_S = 8   # PROVISIONAL


def _where(stack_line):
    """A stack line as `board.py:291 in register`."""
    match = re.match(r'File "(.*)", line (\d+), in (.*)', stack_line)
    return f"{os.path.basename(match[1])}:{match[2]} in {match[3]}" if match else stack_line


class StallChecks:
    """The stall check's methods, mixed into `DetectionService`."""

    def watch_stalls(self, every=STALL_CHECK_EVERY_S):
        """The stall check's loop: how the service runs it until it closes."""
        while not self._closing.wait(every):
            try:
                self.check_stalls()
            except Exception:   # the check must outlive whatever one pass hits
                log.exception("Stall check failed")

    def check_stalls(self, now=None):
        """End every watching Run that has looked at no frame for
        `stall_after_s`. A Run that is still starting or already ending has its
        own timeouts, so only a watching one is judged here."""
        now = time.monotonic() if now is None else now
        with self._lock:
            runs = [(run, run.state == "watching") for run in self._runs.values()]
        for run, watching in runs:
            if run.stalled:
                continue   # already ended or being killed: its retirement is under way
            if run.draining and now - run.draining < self.drain_limit_s():
                continue   # done looking, only posting what it confirmed: the publisher's limit applies
            if not watching:
                run.mark_at = now   # its stall time counts from when it watches
                continue
            mark = run.progress()
            if mark != run.mark:
                run.mark, run.mark_at = mark, now
                continue
            down = run.camera_down()
            if run.was_down and not down:
                # The camera is back: its outage was no one's stall, so a fresh interval starts
                # (it has the next frame's registration to look at one)
                run.was_down, run.mark_at = False, now
                continue
            run.was_down = down
            stuck_s = now - run.mark_at
            if stuck_s < self._stall_after_s:
                continue
            if not down:
                self._stalled(run, stuck_s, input_flowing=True)   # video arrives and the Run does not look: stuck
            elif stuck_s >= CAMERA_DOWN_AFTER_S:
                self._stalled(run, stuck_s, input_flowing=False)   # camera down for long: this Run alone
            # else: the camera is down and its stream reopens itself: wait

    def _dump_threads(self, run, silent_s, input_flowing):
        """Logs, in one line, what the stuck Run was doing, before it is ended: a
        stall leaves no error behind, so this is the only record of what it was
        stuck on (the decoder, the shared model's lock, the GPU, a post). The line
        names the file, line and function the Run's thread is in; its full stack
        and where every other thread is are fields, opened by a click in the
        Logs tab."""
        try:
            if run.process is not None:
                # The Run's thread here only watches the worker's pipe: the work, and
                # the model's lock, are in the worker process, which is killed next
                camera_state = "its camera is down" if run.camera_down() else "its video is still arriving"
                log.error("Camera %s: its Run's worker process is stuck for %.0f s (%s); where it is stuck is "
                          "not captured in process mode", run.camera, silent_s, camera_state,
                          extra={"camera": run.camera, "silent_s": round(silent_s), "input_flowing": input_flowing,
                                 "stuck_in": None, "stream_down": run.camera_down(), "looked": run.progress()})
                return
            lock = getattr(self, "_inference_lock", None)
            names = {t.ident: t.name for t in threading.enumerate()}
            frames = sys._current_frames()
            own = f"Run {run.session_id} {run.camera}"   # the Run's thread name (service.py)
            run_stack, others = [], {}
            for ident, frame in frames.items():
                if ident == threading.get_ident():
                    continue   # the stall check itself
                name = names.get(ident, str(ident))
                if name == own:
                    run_stack = [entry.strip().splitlines()[0] for entry in traceback.format_stack(frame, limit=12)]
                else:
                    last = traceback.extract_stack(frame)[-1]
                    others[name] = f"{os.path.basename(last.filename)}:{last.lineno} in {last.name}"
            where = _where(run_stack[-1]) if run_stack else "a place that could not be read"
            holds = "" if lock is None else f"; the model lock is {'held' if lock.locked() else 'free'}"
            camera_state = "its camera is down" if run.camera_down() else "its video is still arriving"
            log.error("Camera %s: its Run is stuck for %.0f s, in %s (%s%s)",
                      run.camera, silent_s, where, camera_state, holds,
                      extra={"camera": run.camera, "silent_s": round(silent_s), "input_flowing": input_flowing,
                             "stuck_in": where, "stream_down": run.camera_down(), "looked": run.progress(),
                             "model_lock_held": lock.locked() if lock is not None else None,
                             "run_stack": run_stack, "other_threads": others})
        except Exception:   # a diagnostic must never stop the stall from being dealt with
            log.exception("Stall dump failed")

    def _stalled(self, run, silent_s, input_flowing):
        with self._lock:
            if run.stalled:
                return   # a pass that overlaps the last one: dealt with once
            run.stalled = True
        self._dump_threads(run, silent_s, input_flowing)
        mode = "process" if run.process is not None else "thread"
        if input_flowing:
            why = "video kept arriving but the Run looked at nothing"
        else:
            why = "its camera sent no video"
        log.error("Camera %s: its Run (%s mode) looked at no frame for %.0f s (%s): the Run is ended and "
                  "started again by the backend; the other cameras are not affected%s",
                  run.camera, mode, silent_s, why,
                  "" if run.process is not None or not (self._exit_on_stall and input_flowing)
                  else " unless the service has to restart (a stuck thread cannot be stopped)",
                  extra={"camera": run.camera, "session_id": run.session_id, "silent_s": round(silent_s),
                         "input_flowing": input_flowing, "run_mode": mode})
        run.error = run.error or f"stalled: no frame looked at for {silent_s:.0f} s"
        run.dropping = True   # nothing a stuck Run posts late is trusted
        if run.process is not None:
            # Killed: its process's end is seen by `_work_process`, which retires the Run
            try:
                run.process.kill()
            except (AttributeError, ValueError, OSError):
                pass
            return
        if self._exit_on_stall and input_flowing:
            # A thread cannot be killed, and one stuck on the GPU or the shared
            # model's lock holds every other Run with it: the whole service exits,
            # for its supervisor to start again
            self._exit_for_restart(run)
            return
        try:
            run.loop.stop()   # asked, though a stuck thread may never hear it
        except Exception:
            pass
        self._retire(run)   # and left behind: it no longer holds the Session or posts

    def _exit_for_restart(self, stuck):
        """The service exits so its supervisor starts it again. The other Runs
        first get EXIT_DRAIN_S to end as `end` does, so the holes they have
        confirmed are posted, not lost with the process."""
        with self._lock:
            others = [r for r in self._runs.values() if r is not stuck and r.state == "watching"]
        cameras = sorted(r.camera for r in others)
        log.critical("The Detection Service is exiting to be restarted: camera %s has a Run stuck that cannot be "
                     "stopped. Cameras %s are saved first (up to %d s), then every camera's Run starts again",
                     stuck.camera, ", ".join(cameras) or "(none)", EXIT_DRAIN_S,
                     extra={"camera": stuck.camera, "session_id": stuck.session_id, "other_cameras": cameras})
        threads = [threading.Thread(target=self._end, args=(r,), daemon=True) for r in others]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + EXIT_DRAIN_S
        for thread in threads:
            thread.join(max(0.0, deadline - time.monotonic()))
        saved = sorted(r.camera for r in others if r.ended.is_set())
        log.critical("The Detection Service exits now: cameras %s were saved, cameras %s were not in time",
                     ", ".join(saved) or "(none)", ", ".join(c for c in cameras if c not in saved) or "(none)",
                     extra={"saved": saved, "not_saved": [c for c in cameras if c not in saved]})
        logging.shutdown()
        os._exit(3)
