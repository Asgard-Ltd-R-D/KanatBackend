"""Keeps MediaMTX's camera paths matching the cameras table.

Each enabled camera is a MediaMTX path named after its alias whose source is the
camera's RTP multicast (`udp+rtp://group:port?interface=card`): MediaMTX joins
the group itself and reads the H.264 directly, so no GStreamer runs. The
`interface` is the camera's network card by name, so the UI's card picker
decides which card each camera is read on. A disabled camera keeps its path
without a source, because MediaMTX's playback server only plays recordings of a
configured path. Paths added through the Control API live only in MediaMTX's
memory, so they are re-applied when the backend starts and every
camera_sync_interval_s after.

VideoService's run_record.sh/.ps1 (GStreamer) is no longer in this pipeline; the
scripts stay in VideoService for other uses. A path made by an older backend
still runs GStreamer, so the sync recognises it and clears its runOnInit.

Recording follows the Sessions: the cameras record while an active Session has
`record` on, and stop when none has.
"""
import asyncio
import logging
import threading
import time
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session as DBSession

from app.config.settings import settings
from app.core.database import SessionLocal
from app.models import Camera
from app.repositories import cameras as cameras_repo
from app.repositories import sessions as sessions_repo
from app.services import cameras, mediamtx, recordings

log = logging.getLogger(__name__)

# As KanatFrontend recorded: fMP4 in 10-minute files, deleted after a day.
# Durations are written the way MediaMTX reports them back ("10m" reads back as
# "10m0s"), so an unchanged path compares equal and is left alone.
RECORDING = {
    "recordPath": "./recordings/%path/%Y-%m-%d_%H-%M-%S-%f",
    "recordFormat": "fmp4",
    "recordPartDuration": "2s",
    "recordSegmentDuration": "10m0s",
    "recordDeleteAfter": "1d",
}

# The GStreamer recorder older backends ran for each camera. No longer used to
# build a path; kept so a path left over from such a backend is recognised as a
# camera's and converted (is_camera_path).
_RECORD_SCRIPTS = {"bash": "./run_record.sh", "powershell": "./run_record.ps1"}

_lock = threading.Lock()
# The loop's clock. It counts from an arbitrary start (on Linux, the boot), so
# the loop never compares it with a fixed time
_clock = time.monotonic
# Aliases already reported as clashing with a mediamtx.yml path, so the sync
# loop logs each once rather than every round
_conflicts: set[str] = set()
# Whether the cameras were last set to record, so a change is logged once
_recording: bool | None = None
# Whether the sync last found mediamtx.yml unknown, so that is logged once
_config_unknown = False


def _rtp_source(camera: Camera) -> str:
    """The camera's multicast as a MediaMTX source. `?interface=` binds the read
    to the camera's network card by its name (Get-NetAdapter on Windows,
    `ip link` on Linux), so the UI's card picker decides which card the camera is
    read on; without a card MediaMTX reads on the OS's default interface. The
    name is percent-encoded, so a card named "Ethernet 2" is carried safely."""
    source = f"udp+rtp://{camera.mcast_ip}:{camera.mcast_port}"
    if camera.iface:
        source += f"?interface={quote(camera.iface, safe='')}"
    return source


def _rtp_sdp(camera: Camera) -> str:
    """The stream description MediaMTX needs to read raw RTP. The range cameras
    repeat their parameter sets (SPS/PPS) inside the H.264, so only the payload
    type and clock are needed here; 96 is the cameras' H.264 payload type."""
    return (
        "v=0\n"
        "o=- 0 0 IN IP4 127.0.0.1\n"
        "s=KANAT\n"
        f"c=IN IP4 {camera.mcast_ip}\n"
        "t=0 0\n"
        f"m=video {camera.mcast_port} RTP/AVP 96\n"
        "a=rtpmap:96 H264/90000\n"
    )


def path_config(camera: Camera, record: bool) -> dict:
    """The camera's MediaMTX path: MediaMTX reads the camera's RTP multicast
    itself. runOnInit is set empty so a path made by an older backend stops its
    GStreamer recorder when this backend patches it."""
    return {
        "source": _rtp_source(camera),
        "sourceOnDemand": False,
        "rtpSDP": _rtp_sdp(camera),
        # Cleared so a path an older backend left as a publisher with a GStreamer
        # runOnInit is converted to a clean udp+rtp path, not a mixed one
        "overridePublisher": False,
        "runOnInit": "",
        "runOnInitRestart": False,
        "record": record,
        **RECORDING,
    }


def playback_only_config() -> dict:
    """A disabled camera's path: nothing runs or records on it, and its
    recordings stay playable."""
    return {
        "source": "publisher",
        "sourceOnDemand": False,
        "overridePublisher": True,
        "runOnInit": "",
        "runOnInitRestart": False,
        "record": False,
        **RECORDING,
    }


def is_camera_path(name: str, config: dict, config_paths: mediamtx.ConfigPaths | None) -> bool:
    """Whether a path is one of the cameras', which the sync may patch and
    delete. A path mediamtx.yml defines never is, whatever its settings. Of the
    rest, an enabled camera's path reads udp+rtp (or, left by an older backend,
    runs run_record.sh/.ps1), and a disabled camera's is the playback-only path;
    without mediamtx.yml's paths, only the first counts."""
    source = config.get("source") or ""
    run_on_init = config.get("runOnInit") or ""
    if source.startswith("udp+rtp://") or any(script in run_on_init for script in _RECORD_SCRIPTS.values()):
        return config_paths is None or not config_paths.defines(name)
    if config_paths is None or config_paths.defines(name):
        return False
    return all(config.get(key) == value for key, value in playback_only_config().items())


def taken_by_config(alias: str) -> bool:
    """Whether a path of that name belongs to MediaMTX itself (e.g. loopdemo, or
    a name a ~regular expression in mediamtx.yml matches): a camera of that
    name would overwrite or shadow it, and deleting the camera would delete it. False
    when neither mediamtx.yml nor MediaMTX says so; the sync never touches such
    paths anyway."""
    config_paths = mediamtx.config_paths()
    if config_paths is not None and config_paths.defines(alias):
        return True
    try:
        config = mediamtx.list_path_configs().get(alias)
    except mediamtx.MediaMTXUnreachable:
        return False
    return config is not None and not is_camera_path(alias, config, config_paths)


def sync(db: DBSession) -> None:
    """Make MediaMTX's camera paths match the database. Changes nothing while
    mediamtx.yml is unknown (unreadable, or a regular expression not trusted):
    MediaMTX lists a ~regexp path under its key, not the names it covers, so
    any name might be its. Raises MediaMTXUnreachable if it cannot be reached."""
    global _config_unknown
    global _recording
    with _lock:
        record = sessions_repo.recording_session_active(db)
        wanted = {
            c.alias: path_config(c, record) if c.enabled else playback_only_config()
            for c in cameras_repo.list_all(db)
        }
        current = mediamtx.list_path_configs()
        config_paths = mediamtx.config_paths()
        if config_paths is None:
            if not _config_unknown:
                log.warning("mediamtx.yml unreadable or not understood (MEDIAMTX_CONFIG?): cameras are not applied to MediaMTX")
                _config_unknown = True
            return
        if _config_unknown:
            log.info("mediamtx.yml read again: cameras are applied to MediaMTX")
            _config_unknown = False

        for name, config in wanted.items():
            existing = current.get(name)
            if config_paths.defines(name) or (existing is not None and not is_camera_path(name, existing, config_paths)):
                # mediamtx.yml owns this name (the API refuses it, but a camera
                # can get it while MediaMTX was down or the YAML changes later):
                # adding or patching would turn the static path, or the name
                # its ~regular expression covers, into this camera, and
                # deleting the camera would then remove it
                if name not in _conflicts:
                    log.warning("Camera '%s' is not applied: mediamtx.yml has a path of that name", name)
                    _conflicts.add(name)
                continue
            if existing is None:
                mediamtx.add_path(name, config)
                log.info("MediaMTX path '%s' added", name, extra={"camera": name, "record": config["record"]})
                continue
            changed = {key: value for key, value in config.items() if existing.get(key) != value}
            if changed:
                mediamtx.patch_path(name, changed)
                log.info("MediaMTX path '%s' updated: %s", name, ", ".join(sorted(changed)),
                         extra={"camera": name, "fields": sorted(changed)})

        for name, existing in current.items():
            if name not in wanted and is_camera_path(name, existing, config_paths):
                mediamtx.delete_path(name)
                log.info("MediaMTX path '%s' removed: no camera has that name", name, extra={"camera": name})

        if record != _recording and wanted:
            # Once MediaMTX has the cameras set to it, not when only asked; at
            # startup only if they record, there being no "stopped" before
            if _recording is not None or record:
                log.info("Cameras %s recording", "started" if record else "stopped",
                         extra={"record": record, "cameras": sorted(wanted)})
            _recording = record


def sync_soon(db: DBSession) -> None:
    """Sync after a change, without failing the request when MediaMTX is down:
    the sync loop applies it once MediaMTX is back."""
    try:
        sync(db)
    except mediamtx.MediaMTXUnreachable as e:
        log.warning("MediaMTX not updated now, the sync loop will retry: %s", e)


def _sync_once() -> None:
    db = SessionLocal()
    try:
        sync(db)
        aliases = [c.alias for c in cameras_repo.list_all(db)]
        # Every current Session's recorded spans, so a recording the OS held open
        # until it reached a newer Session is kept, not deleted (retry_deletions)
        now = datetime.now(timezone.utc)
        live_windows = [(i.started_at, i.ended_at or now) for i in sessions_repo.all_intervals(db)]
    finally:
        db.close()
    cameras.watch_traffic()
    removed = recordings.remove_unused_recordings(aliases)
    if removed:
        log.info("Deleted %s day-old recording file(s) of cameras that no longer exist", removed,
                 extra={"files_deleted": removed})
    retried = recordings.retry_deletions(live_windows)
    if retried:
        log.info("Deleted %s file(s) that were still in use when their deletion was asked", retried,
                 extra={"files_deleted": retried})


async def run_forever() -> None:
    """The sync loop, started with the app (main.py). Logs only when its state
    changes, not on every failed attempt. Every CACHE_CLEAN_INTERVAL_S it also
    cleans the replay cache."""
    failing = False
    cleaned_at: float | None = None  # first round cleans, whatever the clock reads
    while True:
        if cleaned_at is None or _clock() - cleaned_at >= recordings.CACHE_CLEAN_INTERVAL_S:
            try:
                await run_in_threadpool(recordings.clean_cache)
            except OSError as e:
                log.warning("Cleaning the replay cache failed: %s", e)
            cleaned_at = _clock()
        try:
            await run_in_threadpool(_sync_once)
            if failing:
                log.info("Camera sync with MediaMTX restored")
            failing = False
        except Exception as e:  # keep the loop alive whatever one attempt hits
            if not failing:
                log.warning("Camera sync with MediaMTX failing, retrying every %ss: %s", settings.camera_sync_interval_s, e)
            failing = True
        await asyncio.sleep(settings.camera_sync_interval_s)
