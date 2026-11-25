"""TEMPORARY debug capture (delete before production).

One live-session button records three things to a single timestamped folder,
for working out why a stream or a detection looked wrong:

  - camera-raw.ts   the camera's RTP multicast, copied straight off the wire
                    (the original H.264, before MediaMTX), with ffmpeg -c copy;
  - backend.log / detection.log / frontend.log, the slice written while the
                    recording ran (by byte offset, so no timestamp parsing);
  - overlay.mp4     the app's own view (live video + the overlay), recorded in
                    the renderer and uploaded here (save_overlay), remuxed to
                    MP4 if it arrived as WebM.

It is best-effort: with no ffmpeg on PATH the raw copy and the remux are
skipped and said so in the folder's notes.txt, and the rest is still written.

All of it lives in this module and app/routers/debug.py, plus one button in the
frontend, so the whole feature deletes cleanly.
"""
from __future__ import annotations

import shutil
import subprocess
import threading
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.core.logs import log_dir
from app.models.camera import Camera

log = __import__("logging").getLogger(__name__)

# The logs copied into each recording's folder (core/logs.py writes them there)
_LOG_FILES = ("backend.log", "detection.log", "frontend.log")
# How long stop() waits for ffmpeg to flush and exit before it kills it
_FFMPEG_STOP_WAIT_S = 5
# A safety lease: a live recorder sends a heartbeat (below), which rearms the
# lease; if none arrives within this, the renderer has vanished (window closed,
# reloaded or crashed, missing even the beacon) and the recording is stopped so
# ffmpeg can never write forever. A long live recording keeps its lease by
# heartbeating, so the lease never cuts it short (and its overlay is not lost).
_LEASE_S = 5 * 60


def recordings_dir() -> Path:
    """Where recordings go: a debug-recordings folder inside the log folder, so
    they land where the logs do — a mounted volume in the container deployment
    (/var/log/kanat), the kept data folder on a Windows install."""
    return log_dir() / "debug-recordings"


@dataclass
class _Recording:
    id: str
    folder: Path
    started_at: float  # time.time(), for the notes
    ffmpeg: subprocess.Popen | None
    log_offsets: dict[str, tuple[int, int | None]]  # each log's (size, inode) at start
    notes: list[str] = field(default_factory=list)
    timer: threading.Timer | None = None  # the safety-lease auto-stop


_recordings: dict[str, _Recording] = {}
_lock = threading.Lock()


def _sdp(camera: Camera) -> str:
    """The stream description ffmpeg needs to read the camera's raw RTP, the
    same shape MediaMTX uses: payload type 96 is the cameras' H.264."""
    return (
        "v=0\n"
        "o=- 0 0 IN IP4 127.0.0.1\n"
        "s=KANAT\n"
        f"c=IN IP4 {camera.mcast_ip}\n"
        "t=0 0\n"
        f"m=video {camera.mcast_port} RTP/AVP 96\n"
        "a=rtpmap:96 H264/90000\n"
    )


def _start_raw_capture(folder: Path, camera: Camera, notes: list[str]) -> subprocess.Popen | None:
    """ffmpeg copying the camera's multicast to camera-raw.ts, or None (noted)
    when ffmpeg is missing."""
    if shutil.which("ffmpeg") is None:
        notes.append("camera-raw.ts skipped: ffmpeg not on PATH")
        return None
    if camera.iface:
        # MediaMTX binds the join to this named card; ffmpeg here joins on the
        # host's default interface. On the range PC the installed multicast route
        # (224.0.0.0/4 -> the camera card) sends it out the right card anyway;
        # without that route on a multi-card machine, camera-raw.ts may be empty.
        notes.append(f"camera-raw.ts: joined multicast on the default interface, not {camera.iface!r} "
                     "(relies on the host's multicast route)")
    sdp = folder / "stream.sdp"
    sdp.write_text(_sdp(camera), encoding="ascii")
    out = folder / "camera-raw.ts"
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
        "-protocol_whitelist", "file,crypto,udp,rtp",
        "-i", str(sdp),
        "-c", "copy", "-f", "mpegts", str(out),
    ]
    try:
        return subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                stderr=(folder / "ffmpeg.err.log").open("wb"))
    except OSError as e:
        notes.append(f"camera-raw.ts skipped: ffmpeg would not start ({e})")
        return None


def start(camera: Camera) -> dict:
    """Begin a recording: make the timestamped folder, start the raw copy, and
    note each log file's current size so stop() can slice from there."""
    # The id is in the folder name, and the leaf is created exclusively, so two
    # starts in the same second never share a folder (and overwrite each other)
    rec_id = uuid.uuid4().hex
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    folder = recordings_dir() / f"{stamp}_{rec_id[:8]}"
    folder.mkdir(parents=True, exist_ok=False)
    offsets = {}
    logs = log_dir()
    for name in _LOG_FILES:
        path = logs / name
        st = path.stat() if path.exists() else None
        # size to resume from, and inode to tell a later rotation of this file
        offsets[name] = (st.st_size, st.st_ino) if st else (0, None)
    notes: list[str] = []
    ffmpeg = _start_raw_capture(folder, camera, notes)
    rec = _Recording(id=rec_id, folder=folder, started_at=time.time(),
                     ffmpeg=ffmpeg, log_offsets=offsets, notes=notes)
    with _lock:
        _recordings[rec.id] = rec
        _arm_lease(rec)
    log.info("Debug recording started", extra={"camera": camera.alias, "folder": str(folder)})
    return {"id": rec.id, "folder": str(folder)}


def _arm_lease(rec: _Recording) -> None:
    """(Re)start the safety lease. Call under _lock."""
    if rec.timer is not None:
        rec.timer.cancel()
    rec.timer = threading.Timer(_LEASE_S, _auto_stop, args=[rec.id])
    rec.timer.daemon = True
    rec.timer.start()


def heartbeat(recording_id: str) -> None:
    """A live recorder's keepalive: rearm the lease so it does not fire while the
    renderer is still recording (which would lose the not-yet-uploaded view)."""
    with _lock:
        rec = _recordings.get(recording_id)
        if rec is None:
            raise KeyError(recording_id)
        _arm_lease(rec)


def _auto_stop(recording_id: str) -> None:
    """The safety lease fired: no heartbeat arrived, so the renderer is gone;
    stop the recording it left running."""
    with _lock:
        rec = _recordings.get(recording_id)
    if rec is None:
        return
    rec.notes.append(f"auto-stopped after {_LEASE_S // 60} min without a heartbeat: "
                     "the app stopped sending keepalives (window closed or crashed)")
    log.warning("Debug recording auto-stopped: no heartbeat from the app", extra={"folder": str(rec.folder)})
    with suppress(KeyError):
        stop(recording_id)


def save_overlay(recording_id: str, data: bytes, webm: bool) -> None:
    """Save the app-view recording the renderer uploaded. Written as WebM or
    MP4 by what the browser could record; stop() remuxes a WebM to MP4."""
    rec = _get(recording_id)
    name = "overlay.webm" if webm else "overlay.mp4"
    (rec.folder / name).write_bytes(data)


def stop(recording_id: str) -> dict:
    """End the recording: stop the raw copy, slice the logs into the folder,
    remux the app-view to MP4 if it came as WebM, and write notes.txt."""
    with _lock:
        rec = _recordings.pop(recording_id, None)
        if rec is not None and rec.timer is not None:
            rec.timer.cancel()  # pop and cancel together: no heartbeat can rearm after
    if rec is None:
        raise KeyError(recording_id)

    if rec.ffmpeg is not None:
        _stop_ffmpeg(rec.ffmpeg)
    _slice_logs(rec)
    _remux_overlay(rec)
    _write_notes(rec)
    log.info("Debug recording stopped", extra={"folder": str(rec.folder)})
    return {"folder": str(rec.folder)}


def _get(recording_id: str) -> _Recording:
    with _lock:
        rec = _recordings.get(recording_id)
    if rec is None:
        raise KeyError(recording_id)
    return rec


def _stop_ffmpeg(proc: subprocess.Popen) -> None:
    """Ask ffmpeg to finish (q on its stdin, then terminate), then kill it."""
    try:
        if proc.stdin:
            proc.stdin.write(b"q")
            proc.stdin.flush()
    except OSError:
        pass
    try:
        proc.wait(timeout=_FFMPEG_STOP_WAIT_S)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=_FFMPEG_STOP_WAIT_S)
        except subprocess.TimeoutExpired:
            proc.kill()


def _tail_from(path: Path, offset: int) -> bytes:
    """A file's bytes from `offset` to its end, or b'' if it is gone."""
    if not path.exists():
        return b""
    with path.open("rb") as f:
        f.seek(offset)
        return f.read()


def _rotated_with_inode(logs: Path, name: str, inode: int) -> Path | None:
    """The rotated backup (<name>.YYYY-MM-DD) that is the file the recording
    began in, found by its inode — so rotation is detected by the file actually
    moving, whatever date the handler stamped on the backup."""
    for p in logs.glob(f"{name}.*"):
        with suppress(OSError):
            if p.is_file() and p.stat().st_ino == inode:
                return p
    return None


def _slice_logs(rec: _Recording) -> None:
    """Copy each log file's bytes written while the recording ran, by byte
    offset so no timestamps are parsed. Rotation is detected by the file's
    inode changing (core/logs.py rotates the logs daily, renaming the file):
    then the pre-rotation tail is in the backup that kept the start inode, and
    the current file holds everything written after, so the two are joined.
    Inode, not a date, so it is right however the rename is timed or named."""
    logs = log_dir()
    for name in _LOG_FILES:
        path = logs / name
        start, start_ino = rec.log_offsets.get(name, (0, None))
        exists = path.exists()
        if start_ino is None:
            # Not present when the recording began: all of it now is new
            data = path.read_bytes() if exists else b""
        elif exists and path.stat().st_ino == start_ino:
            data = _tail_from(path, start)  # same file, no rotation
        else:
            # Rotated: the start file (with our offset) moved to a backup
            rotated = _rotated_with_inode(logs, name, start_ino)
            data = (_tail_from(rotated, start) if rotated else b"") + (path.read_bytes() if exists else b"")
        if data or exists:
            (rec.folder / name).write_bytes(data)


def _remux_overlay(rec: _Recording) -> None:
    """Turn overlay.webm into overlay.mp4 (copy video, no re-encode) when the
    browser could only record WebM; needs ffmpeg, else the WebM is left."""
    webm = rec.folder / "overlay.webm"
    if not webm.exists():
        return
    if shutil.which("ffmpeg") is None:
        rec.notes.append("overlay left as WebM: ffmpeg not on PATH to remux to MP4")
        return
    mp4 = rec.folder / "overlay.mp4"
    # Convert to a temp file and publish it only on a clean exit, so a failed
    # convert never deletes the good WebM or leaves a partial overlay.mp4
    tmp = rec.folder / "overlay.remuxing.mp4"
    copy = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-y", "-i", str(webm), "-c", "copy", str(tmp)]
    reencode = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-y", "-i", str(webm), "-c:v", "libx264", str(tmp)]
    try:
        rc = subprocess.run(copy, check=False, stderr=subprocess.DEVNULL).returncode
        if rc != 0:
            # A stream copy can fail if the codec is not MP4-friendly; re-encode
            tmp.unlink(missing_ok=True)
            rc = subprocess.run(reencode, check=False, stderr=subprocess.DEVNULL).returncode
        if rc == 0 and tmp.exists():
            tmp.replace(mp4)
            webm.unlink(missing_ok=True)
        else:
            tmp.unlink(missing_ok=True)
            rec.notes.append("overlay left as WebM: remux to MP4 failed")
    except OSError as e:
        tmp.unlink(missing_ok=True)
        rec.notes.append(f"overlay left as WebM: remux failed ({e})")


def _write_notes(rec: _Recording) -> None:
    lines = [
        f"started: {datetime.fromtimestamp(rec.started_at).isoformat(timespec='seconds')}",
        f"stopped: {datetime.now().isoformat(timespec='seconds')}",
        *rec.notes,
    ]
    (rec.folder / "notes.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
