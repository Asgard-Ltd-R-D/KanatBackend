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
from app.services import baseline_image, groups

_REPORT_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    @page {
      size: A4;
      margin: 42px 44px 52px;
      @bottom-left { content: "KANAT \\2014 Range Session Report"; font-size: 8px; color: #9aa6b4; }
      @bottom-right { content: "Page " counter(page) " / " counter(pages); font-size: 8px; color: #9aa6b4; }
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: Helvetica, Arial, sans-serif; color: #1a2433; font-size: 11px; line-height: 1.45;
           font-feature-settings: "tnum" 1; font-variant-numeric: tabular-nums; }
    .num { font-variant-numeric: tabular-nums; }

    /* Masthead: steel band, the session name is the title, system mark at right */
    .masthead { display: flex; justify-content: space-between; align-items: flex-end;
                background: #13283f; color: #fff; padding: 18px 20px 14px; }
    .masthead h1 { font-size: 21px; font-weight: 700; letter-spacing: -0.01em; line-height: 1.1; }
    .m-sub { color: #9db3cc; font-size: 10px; margin-top: 3px; }
    .m-mark { text-align: right; }
    .m-sys { font-size: 13px; font-weight: 700; letter-spacing: 0.22em; }
    .m-gen { color: #9db3cc; font-size: 8.5px; margin-top: 3px; }
    .accent { height: 2px; background: #c62a1b; margin-bottom: 20px; }

    /* Spec readout: label over value, hairline-separated, instrument style */
    .readout { display: flex; margin-bottom: 26px; }
    .ro { flex: 1; padding: 9px 14px 9px 0; }
    .ro-k { display: block; font-size: 8px; font-weight: 600; letter-spacing: 0.09em;
            text-transform: uppercase; color: #8893a2; margin-bottom: 3px; }
    .ro-v { display: block; font-size: 14px; font-weight: 700; color: #13283f; }
    .ro-v small { font-size: 9px; font-weight: 600; color: #8893a2; }

    /* Lane block: one per board. Each camera after the first starts a new page. */
    .board { margin-bottom: 26px; }
    .board + .board { break-before: page; page-break-before: always; margin-bottom: 0; }
    .board-head { display: flex; justify-content: space-between; align-items: baseline;
                  border-bottom: 2px solid #13283f; padding-bottom: 5px; margin-bottom: 13px; break-after: avoid; }
    .board-name { font-size: 14px; font-weight: 700; color: #13283f; letter-spacing: 0.01em; }
    .board-count { font-size: 10px; font-weight: 600; color: #6a7686; }
    .board-body { display: flex; align-items: flex-start; break-inside: avoid; }

    /* WeasyPrint ignores flexbox `gap`, so the space to the stats is a margin */
    .target-fig { width: 262px; flex: none; margin-right: 44px; }
    /* The drawing canvas: its height comes from padding-bottom (set inline per
       board), the artwork is placed inside it, and shots sit on top. No clipping,
       so a shot on a neighbouring Target (outside the artwork) still shows. */
    .target { position: relative; height: 0; }
    .target-img { position: absolute; display: block; }
    .hole { position: absolute; transform: translate(-50%, -50%); width: 12px; height: 12px;
            border-radius: 50%; border: 1.5px solid #c62a1b; }
    /* The live marker: a hollow ring, its number above it (on a light chip so it reads over a photo) */
    .hole-n { position: absolute; left: 50%; bottom: 100%; transform: translateX(-50%); margin-bottom: 1px;
              color: #c62a1b; font-size: 8.5px; font-weight: 700; line-height: 1; white-space: nowrap;
              background: rgba(255, 255, 255, 0.85); border-radius: 3px; padding: 1px 2px; }
    /* Over the frame, a marker projected beyond the picture is clipped, not drawn over the layout */
    .target.clip { overflow: hidden; }

    .stats { flex: 1; padding-top: 2px; }
    .stats-title { font-size: 10px; font-weight: 700; color: #13283f; letter-spacing: 0.02em; margin-bottom: 7px; }
    .muted { color: #8893a2; font-size: 10px; }
    .note { color: #6a7686; font-size: 9.5px; margin-top: 9px; }
    .note b { color: #1a2433; font-weight: 700; }

    table { width: 100%; border-collapse: collapse; }
    /* The header's colour is on the row, one rectangle: painted cell by cell, a viewer
       draws a hairline between two neighbours */
    thead tr { background: #13283f; }
    thead th { color: #fff; text-align: left; font-weight: 600;
               font-size: 8.5px; letter-spacing: 0.04em; padding: 6px 9px; }
    tbody td { padding: 5px 9px; border-bottom: 1px solid #eef1f4; font-size: 10px; color: #27313f; }
    tbody tr:last-child td { border-bottom: 0; }
    .num { text-align: right; }
    th.num { text-align: right; }
    .stats table { border: 1px solid #e2e7ec; }

    .shotlog { margin-top: 4px; }
    .shotlog-title { font-size: 9px; font-weight: 700; letter-spacing: 0.07em; text-transform: uppercase;
                     color: #8893a2; margin: 15px 0 6px; break-after: avoid; }
    .shotlog thead tr { background: #f0f3f6; }
    .shotlog thead th { color: #51607a; }
    .shotlog tbody td { color: #3a4454; }
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

  <div class="readout">
    <div class="ro"><span class="ro-k">Started</span><span class="ro-v">{{ started }}</span></div>
    <div class="ro"><span class="ro-k">Ended</span><span class="ro-v">{% if ended %}{{ ended }}{% else %}&mdash;{% endif %}</span></div>
    <div class="ro"><span class="ro-k">Duration</span><span class="ro-v">{{ duration }}</span></div>
    <div class="ro"><span class="ro-k">Shots</span><span class="ro-v">{{ total_bullets }}</span></div>
    <div class="ro"><span class="ro-k">Boards</span><span class="ro-v">{{ boards | length }}</span></div>
  </div>

  {% for board in boards %}
  <section class="board">
    <div class="board-head">
      <span class="board-name">{{ board.alias }}</span>
      <span class="board-count">{{ board.bullets | length }} shot{{ '' if board.bullets | length == 1 else 's' }}</span>
    </div>
    <div class="board-body">
      <figure class="target-fig">
        <div class="target{{ ' clip' if board.canvas.clip }}" style="padding-bottom: {{ '%.3f' % board.canvas.pad_pct }}%">
          <img class="target-img" src="{{ board.image_uri }}"
               style="left: {{ '%.3f' % board.canvas.img.left }}%; top: {{ '%.3f' % board.canvas.img.top }}%; width: {{ '%.3f' % board.canvas.img.width }}%; height: {{ '%.3f' % board.canvas.img.height }}%">
          {% for b in board.bullets if b.left is not none %}
          <span class="hole" style="left: {{ '%.3f' % b.left }}%; top: {{ '%.3f' % b.top }}%"><span class="hole-n">{{ b.rank }}</span></span>
          {% endfor %}
        </div>
      </figure>
      <div class="stats">
        <div class="stats-title">Group statistics (MPI)</div>
        {% if board.grouping.groups %}
        <table>
          <thead>
            <tr>
              <th>Target</th>
              <th class="num">Shots</th>
              <th class="num">MPI X (mm)</th>
              <th class="num">MPI Y (mm)</th>
              <th class="num">CEP (mm)</th>
              <th class="num">Mean R (mm)</th>
              <th class="num">RMS R (mm)</th>
              <th class="num">Ext. Spread (mm)</th>
            </tr>
          </thead>
          <tbody>
            {% for g in board.grouping.groups %}
            <tr>
              <td>Target {{ g.target_index + 1 }}</td>
              <td class="num">{{ g.n }}</td>
              <td class="num">{{ g.mpi_x_mm | mm }}</td>
              <td class="num">{{ g.mpi_y_mm | mm }}</td>
              <td class="num">{{ g.cep_mm | mm }}</td>
              <td class="num">{{ g.mean_radius_mm | mm }}</td>
              <td class="num">{{ g.rms_radius_mm | mm }}</td>
              <td class="num">{{ g.extreme_spread_mm | mm }}</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
        {% else %}
        <p class="muted">No group statistics: no positioned shots on a target.</p>
        {% endif %}
        <p class="note">
          Not in a group &mdash; Misses: <b>{{ board.grouping.misses }}</b>
          &nbsp;&nbsp; Without a position: <b>{{ board.grouping.without_position }}</b>
        </p>
      </div>
    </div>

    <div class="shotlog-title">Shot log</div>
    <table class="shotlog">
      <thead>
        <tr>
          <th class="num">#</th>
          <th>Detected at</th>
          <th class="num">Position X</th>
          <th class="num">Position Y</th>
        </tr>
      </thead>
      <tbody>
        {% for b in board.bullets %}
        <tr>
          <td class="num">{{ b.rank }}</td>
          <td>{{ b.ts }}</td>
          <td class="num">{{ '%.1f' % b.x }}</td>
          <td class="num">{{ '%.1f' % b.y }}</td>
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
    onto it; otherwise `uri` is the printed artwork and `frame` is None."""
    artwork = {"uri": _target_data_uri(), "frame": None}
    if db is None or alias is None:
        return artwork
    # One Run, read once: the image and the homography come from the same row
    run = runs_repo.latest(db, session_id, alias)
    path = baseline_image.absolute_path(run.baseline_image_path) if run and run.baseline_image_path else None
    if path is None:
        return artwork
    try:
        view = run.baseline_view
        frame = {
            "matrix": view["template_to_picture"],
            "width": float(view["picture"]["width"]),
            "height": float(view["picture"]["height"]),
        }
        if not (math.isfinite(frame["width"]) and math.isfinite(frame["height"])
                and frame["width"] > 0 and frame["height"] > 0):
            return artwork
        _project(frame["matrix"], 0.0, 0.0)  # a malformed matrix falls back too
        uri = f"data:{baseline_image.media_type(path)};base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    except (KeyError, IndexError, TypeError, ValueError, OSError):
        return artwork
    return {"uri": uri, "frame": frame}


def _project(matrix, x: float, y: float) -> tuple[float, float] | None:
    """A template point through a 3x3 homography, in picture px; None for a point
    on its line at infinity."""
    w = matrix[2][0] * x + matrix[2][1] * y + matrix[2][2]
    if abs(w) < 1e-9:
        return None
    return ((matrix[0][0] * x + matrix[0][1] * y + matrix[0][2]) / w,
            (matrix[1][0] * x + matrix[1][1] * y + matrix[1][2]) / w)


def _frame_canvas(frame: dict) -> dict:
    """The drawing area when the board is the baseline frame: the frame itself."""
    return {
        "pad_pct": frame["height"] / frame["width"] * 100,
        "img": {"left": 0.0, "top": 0.0, "width": 100.0, "height": 100.0},
        "clip": True,
    }


def _board_canvas(holes) -> dict:
    """The drawing area for a board: the artwork box (0..TEMPLATE) widened to
    hold every shot. A board can watch more than one printed Target, and every
    Target's shots are stored in the one reference Target's coordinates (the
    detection maps them through the same homography), so a shot on a neighbouring
    Target lies outside 0..TEMPLATE. Plotting against the artwork alone would push
    it off the edge and lose it; instead the canvas grows to cover it and the
    artwork sits in its place. With every shot inside the artwork (the usual, one
    Target per board) the canvas is exactly the artwork, unchanged."""
    xs = [h.position_x for h in holes]
    ys = [h.position_y for h in holes]
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
        if frame is None:
            canvas = _board_canvas(holes)
            place = lambda b: ((b.position_x - canvas["min_x"]) / canvas["cw"] * 100,
                               (b.position_y - canvas["min_y"]) / canvas["ch"] * 100)
        else:
            # One projection through the frozen baseline homography: template
            # coordinates are a space shared by every Run
            canvas = _frame_canvas(frame)

            def place(b, frame=frame):
                projected = _project(frame["matrix"], b.position_x, b.position_y)
                if projected is None:
                    return None
                return projected[0] / frame["width"] * 100, projected[1] / frame["height"] * 100
        boards.append({
            "alias": bg.camera_alias or "No board",
            "grouping": bg.grouping,
            "canvas": canvas,
            "image_uri": picture["uri"],
            # A shot that cannot be placed on the frame is left off the picture,
            # though it stays in the shot log
            "bullets": [{
                "rank": b.rank,
                "ts": _local_clock(b.first_seen_at),
                "x": b.position_x,
                "y": b.position_y,
                "left": at[0] if at else None,
                "top": at[1] if at else None,
            } for b in holes for at in [place(b)]],
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
# A Group's measure to 0.1 mm; a Group of one has no spread
_jinja_env.filters["mm"] = lambda v: "—" if v is None else f"{v:.1f}"


def _by_board_then_rank(bullets):
    """Holes grouped by board (alias order, no-board last), each board's in
    rank order: ranks run per board now."""
    return sorted(bullets, key=lambda b: (b.camera_alias is None, b.camera_alias or "", b.rank))


def generate_pdf(session: Session, db: DBSession | None = None) -> bytes:
    html = _render_report_html(session, db)
    # Imported here: WeasyPrint needs Pango's system libraries (GTK on
    # Windows), and a PC without them still runs everything but the PDF
    import weasyprint

    return weasyprint.HTML(string=html, base_url=None).write_pdf()


def generate_csv(session: Session) -> str:
    bullets = _by_board_then_rank(session.bullet_holes)
    output = io.StringIO()
    writer = csv.writer(output)
    # The shots, one per row (no Source column)
    writer.writerow(["board", "rank", "first_seen_at", "position_x", "position_y"])
    for b in bullets:
        writer.writerow([
            b.camera_alias or "",
            b.rank,
            _local_clock(b.first_seen_at),
            b.position_x,
            b.position_y,
        ])
    # The Group statistics (MPI), the same numbers as the detail response, the
    # PDF and the Excel Groups sheet. A blank row sets this second table apart.
    writer.writerow([])
    writer.writerow(["board", "target", "bullet_holes", "mpi_x_mm", "mpi_y_mm", "cep_mm",
                     "mean_radius_mm", "rms_radius_mm", "extreme_spread_mm"])
    for bg in groups.groupings(bullets):
        board = bg.camera_alias or ""
        for g in bg.grouping.groups:
            writer.writerow([board, f"Target {g.target_index + 1}", g.n, g.mpi_x_mm, g.mpi_y_mm,
                             g.cep_mm, g.mean_radius_mm, g.rms_radius_mm, g.extreme_spread_mm])
        writer.writerow([board, "Misses", bg.grouping.misses])
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
    _append_header(ws, ["Board", "#", "Detected At", "Position X", "Position Y"])

    for b in bullets:
        ws.append([
            b.camera_alias or "—",
            b.rank,
            _local_clock(b.first_seen_at),
            b.position_x,
            b.position_y,
        ])
    _fit_columns(ws)

    # The same rows and counts as the detail response's groupings, per board
    ws = wb.create_sheet("Groups")
    _append_header(ws, ["Board", "Target", "Bullet Holes", "MPI X (mm)", "MPI Y (mm)", "CEP (mm)",
                        "Mean Radius (mm)", "RMS Radius (mm)", "Extreme Spread (mm)"])
    for bg in groups.groupings(bullets):
        board = bg.camera_alias or "No board"
        for g in bg.grouping.groups:
            ws.append([board, f"Target {g.target_index + 1}", g.n, g.mpi_x_mm, g.mpi_y_mm, g.cep_mm,
                       g.mean_radius_mm, g.rms_radius_mm, g.extreme_spread_mm])
            for cell in ws[ws.max_row][3:]:
                cell.number_format = "0.0"
        ws.append([board, "Misses", bg.grouping.misses])
        ws.append([board, "Without a Position", bg.grouping.without_position])
        ws.append([])
    _fit_columns(ws)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
