import base64
import csv
import io
import math
import re
import urllib.parse
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import openpyxl
from jinja2 import Environment
from openpyxl.styles import Alignment, Font, PatternFill

from sqlalchemy.orm import Session as DBSession

from app.models import Session
from app.repositories import runs as runs_repo
from app.services import baseline_image, groups, run_space

_REPORT_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    @page {
      size: A4;
      margin: 36px 40px 48px;
      @bottom-left { content: "KANAT \\2014 Range Session Report"; font-size: 7.5px; color: #9aa6b4; }
      @bottom-right { content: "Page " counter(page) " / " counter(pages); font-size: 7.5px; color: #9aa6b4; }
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: Helvetica, Arial, sans-serif; color: #1a2433; font-size: 10px; line-height: 1.4;
           font-feature-settings: "tnum" 1; font-variant-numeric: tabular-nums; }

    /* Masthead: steel band, the session name is the title, system mark at right */
    .masthead { display: flex; justify-content: space-between; align-items: flex-end;
                background: #13283f; color: #fff; padding: 14px 18px 12px; }
    .masthead h1 { font-size: 19px; font-weight: 700; letter-spacing: -0.01em; line-height: 1.1; }
    .m-sub { color: #9db3cc; font-size: 9px; margin-top: 2px; }
    .m-mark { text-align: right; }
    .m-sys { font-size: 12px; font-weight: 700; letter-spacing: 0.22em; }
    .m-gen { color: #9db3cc; font-size: 8px; margin-top: 2px; }
    .accent { height: 2px; background: #c62a1b; margin-bottom: 10px; }

    /* Session readout: one light strip, label over value */
    .readout { width: 100%; border-collapse: collapse; background: #f5f7f9; margin-bottom: 14px; }
    .readout td { padding: 7px 12px; vertical-align: top; }
    .ro-k { display: block; font-size: 7px; font-weight: 700; letter-spacing: 0.1em;
            text-transform: uppercase; color: #8893a2; margin-bottom: 2px; }
    .ro-v { display: block; font-size: 11px; font-weight: 700; color: #13283f; white-space: nowrap; }

    /* One block per board; each board after the first starts a new page */
    .board + .board { break-before: page; page-break-before: always; }
    .board-head { display: flex; justify-content: space-between; align-items: baseline;
                  border-bottom: 2px solid #13283f; padding-bottom: 4px; margin-bottom: 8px; break-after: avoid; }
    .board-name { font-size: 13px; font-weight: 700; color: #13283f; }
    .board-count { font-size: 9px; font-weight: 600; color: #6a7686; }

    /* Every section under a board carries the same title */
    .sec { font-size: 8px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: #13283f;
           border-bottom: 1px solid #d5dbe2; padding-bottom: 3px; margin: 12px 0 6px; break-after: avoid; }

    /* The frame, across the page. Its height comes from padding-bottom (set inline
       per board), the picture is placed inside it, and shots sit on top. */
    .target-fig { margin: 0 auto; break-inside: avoid; }
    .target { position: relative; height: 0; }
    .target-img { position: absolute; display: block; }
    .hole { position: absolute; transform: translate(-50%, -50%); width: 14px; height: 14px;
            border-radius: 50%; border: 1px solid #16a34a; }
    /* The live marker: a hollow ring, its number above it (on a light chip so it reads over a photo) */
    .hole-n { position: absolute; left: 50%; bottom: 100%; transform: translateX(-50%); margin-bottom: 1px;
              color: #16a34a; font-size: 8px; font-weight: 700; line-height: 1; white-space: nowrap;
              background: rgba(255, 255, 255, 0.85); border-radius: 3px; padding: 1px 2px; }
    /* Each Target's outline over the frame, named above it */
    .outlines { position: absolute; left: 0; top: 0; width: 100%; height: 100%; }
    .target-n { position: absolute; transform: translate(-50%, -100%); margin-top: -2px;
                color: #b91c1c; font-size: 8px; font-weight: 700; line-height: 1; white-space: nowrap;
                background: rgba(255, 255, 255, 0.85); border-radius: 3px; padding: 1px 3px; }
    /* Over the frame, a marker projected beyond the picture is clipped, not drawn over the layout */
    .target.clip { overflow: hidden; }

    table { width: 100%; border-collapse: collapse; }
    /* The header's colour is on the row, one rectangle: painted cell by cell, a viewer
       draws a hairline between two neighbours */
    thead tr { background: #13283f; }
    thead th { color: #fff; text-align: left; font-weight: 600; font-size: 7.5px; letter-spacing: 0.04em; padding: 5px 7px; }
    tbody td { padding: 4px 7px; border-bottom: 1px solid #eef1f4; font-size: 9px; color: #27313f; }
    tbody tr:last-child td { border-bottom: 0; }
    .num, th.num { text-align: right; }
    .stats { border: 1px solid #e2e7ec; break-inside: avoid; }
    .stats td.t { font-weight: 700; color: #13283f; }
    .note { color: #6a7686; font-size: 8.5px; margin-top: 5px; }
    .note b { color: #1a2433; }
    .muted { color: #8893a2; font-size: 9px; }

    /* The shot log: one card per Target, two side by side */
    .grid { width: 100%; border-collapse: separate; border-spacing: 0; }
    .grid > tbody > tr > td { width: 50%; vertical-align: top; padding: 0 0 10px 0; border: 0; }
    .grid > tbody > tr > td.l { padding-right: 6px; }
    .grid > tbody > tr > td.r { padding-left: 6px; }
    /* A card too tall for a page breaks across it, its header rows (the
       Target's name and the columns) repeated, rather than leaving a blank
       page before it */
    .card { border: 1px solid #e2e7ec; }
    .card thead tr.card-head { background: #13283f; }
    .card thead th.card-name { color: #fff; font-size: 9px; font-weight: 700; letter-spacing: 0; padding: 5px 8px; }
    .card thead th.card-count { color: #9db3cc; font-size: 8px; font-weight: 400; text-align: right; padding: 5px 8px; }
    .card thead tr.cols { background: #f0f3f6; }
    .card thead tr.cols th { color: #51607a; }
    .card tbody td { color: #3a4454; }
  </style>
</head>
<body>
  <header class="masthead">
    <div>
      <h1>{{ session.name }}</h1>
      <div class="m-sub">Range session report</div>
    </div>
    <div class="m-mark">
      <div class="m-sys">KANAT</div>
      <div class="m-gen">Generated {{ generated_at }}</div>
    </div>
  </header>
  <div class="accent"></div>

  <table class="readout">
    <tr>
      <td style="width: 26%"><span class="ro-k">Started</span><span class="ro-v">{{ started }}</span></td>
      <td style="width: 26%"><span class="ro-k">Ended</span><span class="ro-v">{% if ended %}{{ ended }}{% else %}&mdash;{% endif %}</span></td>
      <td><span class="ro-k">Duration</span><span class="ro-v">{{ duration }}</span></td>
      <td><span class="ro-k">Shots</span><span class="ro-v">{{ total_bullets }}</span></td>
      <td><span class="ro-k">Boards</span><span class="ro-v">{{ boards | length }}</span></td>
    </tr>
  </table>

  {% for board in boards %}
  <section class="board">
    <div class="board-head">
      <span class="board-name">{{ board.alias }}</span>
      <span class="board-count">{{ board.bullets | length }} shot{{ '' if board.bullets | length == 1 else 's' }}</span>
    </div>

    <figure class="target-fig" style="width: {{ '%.3f' % board.fig_width }}%">
      <div class="target{{ ' clip' if board.canvas.clip }}" style="padding-bottom: {{ '%.3f' % board.canvas.pad_pct }}%">
        <img class="target-img" src="{{ board.image_uri }}"
             style="left: {{ '%.3f' % board.canvas.img.left }}%; top: {{ '%.3f' % board.canvas.img.top }}%; width: {{ '%.3f' % board.canvas.img.width }}%; height: {{ '%.3f' % board.canvas.img.height }}%">
        {% if board.targets %}
        <svg class="outlines" viewBox="0 0 {{ '%.3f' % board.canvas.vw }} {{ '%.3f' % board.canvas.vh }}" preserveAspectRatio="none">
          {% for t in board.targets %}
          <polygon points="{{ t.points }}" fill="none" stroke="#ef4444" stroke-width="{{ '%.3f' % board.canvas.stroke }}" stroke-linejoin="round"/>
          {% endfor %}
        </svg>
        {% for t in board.targets %}
        <span class="target-n" style="left: {{ '%.3f' % t.left }}%; top: {{ '%.3f' % t.top }}%">Target {{ t.number }}</span>
        {% endfor %}
        {% endif %}
        {% for b in board.bullets if b.left is not none %}
        <span class="hole" style="left: {{ '%.3f' % b.left }}%; top: {{ '%.3f' % b.top }}%"><span class="hole-n">{{ b.rank }}</span></span>
        {% endfor %}
      </div>
    </figure>

    <div class="sec">Group statistics (MPI)</div>
    {% if board.grouping.groups %}
    <table class="stats">
      <thead>
        <tr>
          <th>Target</th>
          <th class="num">Shots</th>
          <th class="num">MPI X (cm)</th>
          <th class="num">MPI Y (cm)</th>
          <th class="num">CEP (cm)</th>
          <th class="num">Mean R (cm)</th>
          <th class="num">RMS R (cm)</th>
          <th class="num">Ext. Spread (cm)</th>
        </tr>
      </thead>
      <tbody>
        {% for g in board.grouping.groups %}
        <tr>
          <td class="t">Target {{ g.target_index + 1 }}</td>
          <td class="num">{{ g.n }}</td>
          <td class="num">{{ g.mpi_x_mm | cm }}</td>
          <td class="num">{{ g.mpi_y_mm | cm }}</td>
          <td class="num">{{ g.cep_mm | cm }}</td>
          <td class="num">{{ g.mean_radius_mm | cm }}</td>
          <td class="num">{{ g.rms_radius_mm | cm }}</td>
          <td class="num">{{ g.extreme_spread_mm | cm }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <p class="muted">No group statistics: no positioned shots on a target.</p>
    {% endif %}
    <p class="note">
      Not in a group &mdash; Without a position: <b>{{ board.grouping.without_position }}</b>
    </p>

    <div class="sec">Shot log</div>
    <table class="grid">
      <tbody>
        {% for pair in board.shot_log | batch(2) %}
        <tr>
          {% for section in pair %}
          <td class="{{ 'l' if loop.first else 'r' }}">
            <div class="card">
              <table class="shotlog">
                <thead>
                  <!-- In the header, so a card that runs onto the next page names its Target there too -->
                  <tr class="card-head">
                    <th colspan="2" class="card-name">{{ section.label }}</th>
                    <th colspan="2" class="card-count">{{ section.bullets | length }} shot{{ '' if section.bullets | length == 1 else 's' }}</th>
                  </tr>
                  <tr class="cols">
                    <th class="num">#</th>
                    <th>Detected at</th>
                    <th class="num">X (cm)</th>
                    <th class="num">Y (cm)</th>
                  </tr>
                </thead>
                <tbody>
                  {% for b in section.bullets %}
                  <tr>
                    <td class="num">{{ b.rank }}</td>
                    <td>{{ b.ts }}</td>
                    <td class="num">{{ b.x_mm | cm }}</td>
                    <td class="num">{{ b.y_mm | cm }}</td>
                  </tr>
                  {% endfor %}
                </tbody>
              </table>
            </div>
          </td>
          {% endfor %}
          {% if pair | length == 1 %}<td class="r"></td>{% endif %}
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </section>
  {% endfor %}
</body>
</html>"""

# The target artwork is authored at this pixel size; a Bullet Hole's position is
# stored in these same template coordinates (ADR-0009), so a hole maps straight
# to a percentage over the picture — the same mapping the app's overlay uses.
_TEMPLATE_W = 1405
_TEMPLATE_H = 1120


@lru_cache(maxsize=1)
def _target_data_uri() -> str:
    """The Target picture as a data URI, so the PDF carries it with no file or
    network lookup at render time. Cached: the same bytes for every report.

    The artwork's white is not white: its palette holds dozens of near-whites
    (253, 254, 255...) in a noisy pattern, which a PDF viewer shows as faint lines
    in a grid over the picture. Every near-white entry is made pure white."""
    data = (Path(__file__).resolve().parent.parent / "assets" / "target.png").read_bytes()
    return "data:image/png;base64," + base64.b64encode(_flat_white(data)).decode("ascii")


# A palette colour with every channel at or above this is paper, not ink
_NEAR_WHITE = 235


def _flat_white(png: bytes) -> bytes:
    """`png` with its near-white palette entries made pure white; the bytes as they
    came if it is not a palette image or the imaging library is missing."""
    try:
        from PIL import Image
    except ImportError:
        return png
    image = Image.open(io.BytesIO(png))
    palette = image.getpalette()
    if image.mode != "P" or palette is None:
        return png
    for i in range(0, len(palette) - 2, 3):
        if min(palette[i:i + 3]) >= _NEAR_WHITE:
            palette[i:i + 3] = [255, 255, 255]
    image.putpalette(palette)
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _board_picture(db: DBSession | None, session_id, alias: str | None) -> dict:
    """What a board is drawn over: `{"uri", "frame"}`. When the board's latest
    Run has a stored baseline frame that still exists, `uri` is that frame and
    `frame` carries its `template_to_picture` and pixel size, to project shots
    onto it, and the board's Runs (in taken_at order) to carry an earlier Run's
    shots into the latest's space; otherwise `uri` is the printed artwork and
    `frame` is None."""
    if db is None or alias is None:
        return {"uri": _target_data_uri(), "frame": None, "runs": []}
    # The Runs, read once: the image and the homography come from the same row
    runs = runs_repo.of_camera(db, session_id, alias)
    artwork = {"uri": _target_data_uri(), "frame": None, "runs": runs}
    run = runs[-1] if runs else None
    path = baseline_image.absolute_path(run.baseline_image_path) if run and run.baseline_image_path else None
    if path is None:
        return artwork
    try:
        view = run.baseline_view
        frame = {
            "matrix": view["template_to_picture"],
            "width": float(view["picture"]["width"]),
            "height": float(view["picture"]["height"]),
            "targets": view.get("targets") or [],
        }
        if not (math.isfinite(frame["width"]) and math.isfinite(frame["height"])
                and frame["width"] > 0 and frame["height"] > 0):
            return artwork
        _project(frame["matrix"], 0.0, 0.0)  # a malformed matrix falls back too
        uri = f"data:{baseline_image.media_type(path)};base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    except (KeyError, IndexError, TypeError, ValueError, OSError):
        return artwork
    return {"uri": uri, "frame": frame, "runs": runs}


def _project(matrix, x: float, y: float) -> tuple[float, float] | None:
    """A template point through a 3x3 homography, in picture px; None for a point
    on its line at infinity."""
    w = matrix[2][0] * x + matrix[2][1] * y + matrix[2][2]
    if abs(w) < 1e-9:
        return None
    return ((matrix[0][0] * x + matrix[0][1] * y + matrix[0][2]) / w,
            (matrix[1][0] * x + matrix[1][1] * y + matrix[1][2]) / w)


def _carried(runs: list, holes) -> list[tuple[float, float]]:
    """Each hole's position in the latest Run's template space: as stored with
    at most one Run, carried from its own Run otherwise; as stored if a Run's
    view is malformed."""
    if len(runs) < 2:
        return [(h.position_x, h.position_y) for h in holes]
    try:
        return run_space.holes_over(runs[-1], runs, holes)
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError):
        return [(h.position_x, h.position_y) for h in holes]


# The A4 page's printable width (210 mm less the 40 px margins) and the most
# height the board's figure may take on it, in CSS px, leaving the session
# header, the board's title and the start of its statistics room on page one
_PRINTABLE_W = 210 / 25.4 * 96 - 80
_FIGURE_MAX_H = 560


def _figure_width(pad_pct: float) -> float:
    """The figure's width, as a percentage of the page's, so its height
    (pad_pct of its width) stays within _FIGURE_MAX_H: the full width for a
    camera frame, narrower for a tall canvas (shots on Targets stacked
    vertically), scaled as a whole so every marker stays on the page."""
    height_at_full = _PRINTABLE_W * pad_pct / 100
    return min(100.0, _FIGURE_MAX_H / height_at_full * 100) if height_at_full > 0 else 100.0


def _frame_canvas(frame: dict) -> dict:
    """The drawing area when the board is the baseline frame: the frame itself."""
    return {
        "pad_pct": frame["height"] / frame["width"] * 100,
        "img": {"left": 0.0, "top": 0.0, "width": 100.0, "height": 100.0},
        # The outlines' SVG is drawn in frame px; ~1.5px wide at the figure's full width
        "vw": frame["width"], "vh": frame["height"], "stroke": frame["width"] / 520 * 1.5,
        "clip": True,
    }


def _target_outlines(frame: dict) -> list[dict]:
    """Each Target's outline projected onto the frame, as SVG points in frame px,
    with its name's place (centred above it, as a percentage of the frame).
    `number` is target_index + 1, as the live overlay names it; an outline that
    cannot be projected or is malformed is left out."""
    out = []
    for i, outline in enumerate(frame.get("targets") or []):
        try:
            pts = [_project(frame["matrix"], float(x), float(y)) for x, y in outline]
        except (TypeError, ValueError):
            continue
        if not pts or any(p is None or not (math.isfinite(p[0]) and math.isfinite(p[1])) for p in pts):
            continue
        # Centred over the outline, just above its topmost point
        centre_x = (min(p[0] for p in pts) + max(p[0] for p in pts)) / 2
        top_y = min(p[1] for p in pts)
        out.append({
            "number": i + 1,
            "points": " ".join(f"{x:.2f},{y:.2f}" for x, y in pts),
            # Kept inside the frame: the figure clips, and a name at its edge would be cut in half
            "left": min(max(centre_x / frame["width"] * 100, 6.0), 94.0),
            "top": max(top_y / frame["height"] * 100, 4.0),
        })
    return out


def _board_canvas(points: list[tuple[float, float]]) -> dict:
    """The drawing area for a board: the artwork box (0..TEMPLATE) widened to
    hold every shot. A board can watch more than one printed Target, and every
    Target's shots are stored in the one reference Target's coordinates (the
    detection maps them through the same homography), so a shot on a neighbouring
    Target lies outside 0..TEMPLATE. Plotting against the artwork alone would push
    it off the edge and lose it; instead the canvas grows to cover it and the
    artwork sits in its place. With every shot inside the artwork (the usual, one
    Target per board) the canvas is exactly the artwork, unchanged."""
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    min_x, max_x = min([0.0, *xs]), max([float(_TEMPLATE_W), *xs])
    min_y, max_y = min([0.0, *ys]), max([float(_TEMPLATE_H), *ys])
    cw, ch = max_x - min_x, max_y - min_y
    return {
        "min_x": min_x, "min_y": min_y, "cw": cw, "ch": ch,
        "pad_pct": ch / cw * 100,  # padding-bottom hack sets the box's height from its width
        "img": {
            "left": (0.0 - min_x) / cw * 100,
            "top": (0.0 - min_y) / ch * 100,
            "width": _TEMPLATE_W / cw * 100,
            "height": _TEMPLATE_H / ch * 100,
        },
    }


def _boards_for_report(bullets, db: DBSession | None = None, session_id=None) -> list[dict]:
    """One entry per board, in the groupings' order (alias order, no-board last),
    each with a canvas, the board's Bullet Holes placed on it (left/top as a
    percentage of the canvas) and its Group statistics."""
    by_alias: dict[str | None, list] = {}
    for b in bullets:
        by_alias.setdefault(b.camera_alias, []).append(b)
    boards = []
    for bg in groups.groupings(bullets):
        holes = sorted(by_alias.get(bg.camera_alias, []), key=lambda b: b.rank)
        picture = _board_picture(db, session_id, bg.camera_alias)
        frame = picture["frame"]
        # Each Run may hang its template coordinates on another Target, so a
        # shot from an earlier Run is first carried into the latest Run's space
        # (as the live Overlay does), on the frame or on the artwork alike
        points = _carried(picture["runs"], holes)
        carried = dict(zip(map(id, holes), points))
        if frame is None:
            canvas = _board_canvas(points)
            place = lambda b: ((carried[id(b)][0] - canvas["min_x"]) / canvas["cw"] * 100,
                               (carried[id(b)][1] - canvas["min_y"]) / canvas["ch"] * 100)
        else:
            canvas = _frame_canvas(frame)

            def place(b, frame=frame, carried=carried):
                projected = _project(frame["matrix"], *carried[id(b)])
                if projected is None:
                    return None
                return projected[0] / frame["width"] * 100, projected[1] / frame["height"] * 100
        boards.append({
            "alias": bg.camera_alias or "No board",
            "fig_width": _figure_width(canvas["pad_pct"]),
            "targets": _target_outlines(frame) if frame else [],
            "grouping": bg.grouping,
            "canvas": canvas,
            "image_uri": picture["uri"],
            # A shot that cannot be placed on the frame is left off the picture,
            # though it stays in the shot log
            "bullets": [{
                "rank": b.rank,
                "ts": _local_clock(b.first_seen_at),
                "x_mm": b.x_mm,
                "y_mm": b.y_mm,
                "left": at[0] if at else None,
                "top": at[1] if at else None,
            } for b in holes for at in [place(b)]],
            # The shot log, one section per Target; ranks stay the board's own
            "shot_log": [{
                "label": label,
                "bullets": [{"rank": b.rank, "ts": _local_clock(b.first_seen_at), "x_mm": b.x_mm, "y_mm": b.y_mm}
                            for b in section],
            } for label, section in _by_target(holes)],
        })
    return boards


def _render_report_html(session: Session, db: DBSession | None = None) -> str:
    bullets = _by_board_then_rank(session.bullet_holes)
    now = _as_local(datetime.now(timezone.utc))
    return _jinja_env.from_string(_REPORT_HTML).render(
        session=session,
        total_bullets=len(bullets),
        boards=_boards_for_report(bullets, db, getattr(session, "id", None)),
        started=_local_clock(session.started_at),
        ended=_local_clock(session.ended_at) if session.ended_at else None,
        duration=_session_duration(session),
        generated_at=f"{now:%Y-%m-%d %H:%M}",
    )


def _as_local(moment: datetime) -> datetime:
    """A stored time (UTC) converted to the PC's time zone. The database keeps UTC;
    every export shows the conversion, as the PC's own clock reads it."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone()


def _local_clock(moment: datetime) -> str:
    """The converted time, written YYYY-MM-DD HH:MM:SS: what every export prints."""
    return _as_local(moment).strftime("%Y-%m-%d %H:%M:%S")


def _session_duration(session: Session) -> str:
    if session.ended_at and session.started_at:
        # As the app writes it (frontend utils/format.ts): 12m 4s, and from an
        # hour on 1h 5m 4s, never 65m 4s
        total_s = max(0, int((session.ended_at - session.started_at).total_seconds()))
        h, rest = divmod(total_s, 3600)
        m, s = divmod(rest, 60)
        return f"{h}h {m}m {s}s" if h else f"{m}m {s}s"
    return "—"


def _ascii_slug(name: str) -> str:
    slug = name.encode("ascii", errors="replace").decode()
    slug = re.sub(r"[^\w\s-]", "_", slug)
    slug = re.sub(r"[\s]+", "_", slug)
    return slug.strip("_") or "session"


def _content_disposition(session: Session, ext: str) -> str:
    date_str = _as_local(session.started_at).strftime("%Y%m%d")
    fallback = f"session_{_ascii_slug(session.name)}_{date_str}.{ext}"
    utf8_name = f"session_{session.name.replace(' ', '_')}_{date_str}.{ext}"
    encoded = urllib.parse.quote(utf8_name, safe="-._~")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"


_jinja_env = Environment(autoescape=True)
# A stored millimetre measure shown in centimetres, to 0.01 cm; a Group of one has no spread
# (+ 0.0 turns a rounded -0.0 into 0.0, so a hole on the centre line never reads "-0.00")
_jinja_env.filters["cm"] = lambda v: "—" if v is None else f"{round(v / 10, 2) + 0.0:.2f}"


def _target_label(hole) -> str:
    """Which Target a hole is on, as every export names it: "Target N" (from 1),
    or "No target" for one without (a manual one, or a Miss stored before #422)."""
    if hole.target_index is not None:
        return f"Target {hole.target_index + 1}"
    return "No target"


def _target_order(hole) -> tuple:
    """Targets in index order, then the holes on no Target."""
    return (0, hole.target_index) if hole.target_index is not None else (1, 0)


def _by_target(holes) -> list[tuple[str, list]]:
    """One board's holes as (label, holes in rank order), one section per Target."""
    sections: dict[tuple, list] = {}
    for h in sorted(holes, key=lambda h: (_target_order(h), h.rank)):
        sections.setdefault(_target_order(h), []).append(h)
    return [(_target_label(hs[0]), hs) for _, hs in sorted(sections.items())]


def _cm(v: float | None) -> float | None:
    """A stored millimetre value in centimetres, to 0.01 cm."""
    return None if v is None else round(v / 10, 2) + 0.0


def _by_board_then_target(bullets):
    """Holes by board (alias order, no-board last), then Target, then rank."""
    return sorted(bullets, key=lambda b: (b.camera_alias is None, b.camera_alias or "", _target_order(b), b.rank))


def _by_board_then_rank(bullets):
    """Holes grouped by board (alias order, no-board last), each board's in
    rank order: ranks run per board now."""
    return sorted(bullets, key=lambda b: (b.camera_alias is None, b.camera_alias or "", b.rank))


def generate_pdf(session: Session, db: DBSession | None = None) -> bytes:
    html = _render_report_html(session, db)
    # Imported here: WeasyPrint needs Pango's system libraries (GTK on
    # Windows), and a PC without them still runs everything but the PDF
    import weasyprint

    return weasyprint.HTML(string=html, base_url=None, url_fetcher=_embedded_only).write_pdf()


def _embedded_only(url: str, *args, **kwargs):
    """The PDF's URL fetcher: the report's own images are data URIs; anything
    else (a file or a server) is never fetched."""
    import weasyprint

    if not url.startswith("data:"):
        raise ValueError("The report loads only its embedded images")
    return weasyprint.default_url_fetcher(url, *args, **kwargs)


def generate_csv(session: Session) -> str:
    bullets = _by_board_then_rank(session.bullet_holes)
    output = io.StringIO()
    writer = csv.writer(output)
    # The shots, one per row (no Source column), per Target; in cm from its centre
    writer.writerow(["board", "target", "rank", "first_seen_at", "x_cm", "y_cm"])
    for b in _by_board_then_target(bullets):
        writer.writerow([
            b.camera_alias or "",
            _target_label(b),
            b.rank,
            _local_clock(b.first_seen_at),
            _cm(b.x_mm),
            _cm(b.y_mm),
        ])
    # The Group statistics (MPI), the detail response's numbers in centimetres, as
    # the PDF and the Excel Groups sheet show them. A blank row sets this second table apart.
    writer.writerow([])
    writer.writerow(["board", "target", "bullet_holes", "mpi_x_cm", "mpi_y_cm", "cep_cm",
                     "mean_radius_cm", "rms_radius_cm", "extreme_spread_cm"])
    for bg in groups.groupings(bullets):
        board = bg.camera_alias or ""
        for g in bg.grouping.groups:
            writer.writerow([board, f"Target {g.target_index + 1}", g.n, _cm(g.mpi_x_mm), _cm(g.mpi_y_mm),
                             _cm(g.cep_mm), _cm(g.mean_radius_mm), _cm(g.rms_radius_mm),
                             _cm(g.extreme_spread_mm)])
        writer.writerow([board, "Without a position", bg.grouping.without_position])
    return output.getvalue()


def _append_header(ws, headers: list[str]) -> None:
    ws.append(headers)
    for cell in ws[ws.max_row]:
        cell.fill = PatternFill("solid", fgColor="1E293B")
        cell.font = Font(bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center")


def _fit_columns(ws) -> None:
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = max(max_len + 2, 12)


def generate_excel(session: Session) -> bytes:
    bullets = _by_board_then_rank(session.bullet_holes)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Bullet Holes"
    _append_header(ws, ["Board", "Target", "#", "Detected At", "X (cm)", "Y (cm)"])

    for b in _by_board_then_target(bullets):
        ws.append([
            b.camera_alias or "—",
            _target_label(b),
            b.rank,
            _local_clock(b.first_seen_at),
            _cm(b.x_mm),
            _cm(b.y_mm),
        ])
        for cell in ws[ws.max_row][4:]:
            cell.number_format = "0.00"
    _fit_columns(ws)

    # The same rows and counts as the detail response's groupings, per board
    ws = wb.create_sheet("Groups")
    _append_header(ws, ["Board", "Target", "Bullet Holes", "MPI X (cm)", "MPI Y (cm)", "CEP (cm)",
                        "Mean Radius (cm)", "RMS Radius (cm)", "Extreme Spread (cm)"])
    for bg in groups.groupings(bullets):
        board = bg.camera_alias or "No board"
        for g in bg.grouping.groups:
            ws.append([board, f"Target {g.target_index + 1}", g.n, _cm(g.mpi_x_mm), _cm(g.mpi_y_mm),
                       _cm(g.cep_mm), _cm(g.mean_radius_mm), _cm(g.rms_radius_mm), _cm(g.extreme_spread_mm)])
            for cell in ws[ws.max_row][3:]:
                cell.number_format = "0.00"
        ws.append([board, "Without a Position", bg.grouping.without_position])
        ws.append([])
    _fit_columns(ws)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
