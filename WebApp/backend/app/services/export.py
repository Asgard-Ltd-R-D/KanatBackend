import csv
import io
from datetime import datetime, timezone

import openpyxl
import weasyprint
from jinja2 import Template
from openpyxl.styles import Alignment, Font, PatternFill

from app.models import Session

_REPORT_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, Inter, system-ui, sans-serif; color: #1e293b; padding: 40px; font-size: 13px; }
    h1 { font-size: 20px; font-weight: 700; margin-bottom: 4px; }
    .subtitle { color: #64748b; font-size: 12px; margin-bottom: 28px; }
    .summary { display: flex; gap: 16px; margin-bottom: 32px; }
    .card { border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 20px; background: #f8fafc; }
    .card-label { font-size: 10px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 4px; }
    .card-value { font-size: 24px; font-weight: 700; color: #0f172a; }
    table { width: 100%; border-collapse: collapse; }
    thead tr { background: #1e293b; }
    th { text-align: left; padding: 9px 14px; color: #fff; font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; }
    td { padding: 8px 14px; border-bottom: 1px solid #f1f5f9; }
    tr:nth-child(even) td { background: #f8fafc; }
    .footer { margin-top: 28px; font-size: 10px; color: #94a3b8; text-align: right; }
  </style>
</head>
<body>
  <h1>{{ session.name }}</h1>
  <p class="subtitle">
    {{ session.started_at.strftime('%Y-%m-%d %H:%M') }} UTC
    &nbsp;&middot;&nbsp; Duration: {{ duration }}
    &nbsp;&middot;&nbsp; {{ session.status | capitalize }}
  </p>
  <div class="summary">
    <div class="card">
      <div class="card-label">Total Bullets</div>
      <div class="card-value">{{ bullets | length }}</div>
    </div>
  </div>
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>Detected At (UTC)</th>
        <th>Position X</th>
        <th>Position Y</th>
      </tr>
    </thead>
    <tbody>
      {% for b in bullets %}
      <tr>
        <td>{{ loop.index }}</td>
        <td>{{ b.first_seen_at.strftime('%H:%M:%S') }}</td>
        <td>{{ "%.1f" | format(b.position_x) }}</td>
        <td>{{ "%.1f" | format(b.position_y) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  <div class="footer">Generated {{ generated_at }}</div>
</body>
</html>"""


def _session_duration(session: Session) -> str:
    if session.ended_at and session.started_at:
        delta = session.ended_at - session.started_at
        total_s = int(delta.total_seconds())
        m, s = divmod(total_s, 60)
        return f"{m}m {s:02d}s"
    return "—"


def _session_filename(session: Session, ext: str) -> str:
    safe_name = session.name.replace(" ", "_")
    date_str = session.started_at.strftime("%Y%m%d")
    return f"session_{safe_name}_{date_str}.{ext}"


def generate_pdf(session: Session) -> bytes:
    bullets = session.bullet_holes
    html = Template(_REPORT_HTML).render(
        session=session,
        bullets=bullets,
        duration=_session_duration(session),
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )
    return weasyprint.HTML(string=html, base_url=None).write_pdf()


def generate_csv(session: Session) -> tuple[str, str]:
    bullets = session.bullet_holes
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["#", "first_seen_at", "position_x", "position_y", "source", "rank"])
    for b in bullets:
        writer.writerow([
            b.rank,
            b.first_seen_at.isoformat(),
            b.position_x,
            b.position_y,
            b.source,
            b.rank,
        ])
    return output.getvalue(), _session_filename(session, "csv")


def generate_excel(session: Session) -> tuple[bytes, str]:
    bullets = session.bullet_holes
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Bullet Holes"

    headers = ["#", "Detected At (UTC)", "Position X", "Position Y", "Source"]
    ws.append(headers)

    header_fill = PatternFill("solid", fgColor="1E293B")
    header_font = Font(bold=True, color="FFFFFF")
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    for b in bullets:
        ws.append([
            b.rank,
            b.first_seen_at.strftime("%Y-%m-%d %H:%M:%S"),
            b.position_x,
            b.position_y,
            b.source,
        ])

    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = max(max_len + 2, 12)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read(), _session_filename(session, "xlsx")
