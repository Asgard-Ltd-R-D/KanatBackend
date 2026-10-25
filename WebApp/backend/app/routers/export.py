import io
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session as DBSession

from app.core.deps import get_db
from app.services import export as svc
from app.services.sessions import get_session_detail

router = APIRouter(prefix="/sessions/{session_id}/export", tags=["export"])
log = logging.getLogger(__name__)


def _log_export(session, kind: str, size: int) -> None:
    log.info(
        "Session '%s' exported as %s", session.name, kind,
        extra={"session_id": session.id, "session_name": session.name, "format": kind,
               "bullets": len(session.bullet_holes), "size_kb": round(size / 1024, 1)},
    )


def _require_completed(session_id: uuid.UUID, db: DBSession):
    session = get_session_detail(session_id, db)
    if session.status == "active":
        raise HTTPException(
            status_code=409,
            detail="Session is still active; close it before exporting",
        )
    return session


@router.get("/pdf")
def export_pdf(session_id: uuid.UUID, db: DBSession = Depends(get_db)):
    session = _require_completed(session_id, db)
    pdf_bytes = svc.generate_pdf(session)
    _log_export(session, "PDF", len(pdf_bytes))
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": svc._content_disposition(session, "pdf")},
    )


@router.get("/csv")
def export_csv(session_id: uuid.UUID, db: DBSession = Depends(get_db)):
    session = _require_completed(session_id, db)
    content = svc.generate_csv(session)
    _log_export(session, "CSV", len(content.encode()))
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": svc._content_disposition(session, "csv")},
    )


@router.get("/excel")
def export_excel(session_id: uuid.UUID, db: DBSession = Depends(get_db)):
    session = _require_completed(session_id, db)
    content = svc.generate_excel(session)
    _log_export(session, "Excel", len(content))
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": svc._content_disposition(session, "xlsx")},
    )
