import logging
import uuid

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session as DBSession
from starlette.background import BackgroundTask

from app.core.deps import get_db
from app.core.live import event_stream, hub
from app.services import sessions as svc

router = APIRouter(prefix="/sessions/{session_id}/live", tags=["live"])
log = logging.getLogger(__name__)


@router.get("")
async def session_live(session_id: uuid.UUID, db: DBSession = Depends(get_db)):
    """Stream a Session's changes (schemas/live.py) to the frontend as Server-Sent Events."""
    try:
        # An unknown Session answers 404, and the browser does not reconnect
        await run_in_threadpool(svc.get_session_or_404, session_id, db)
    finally:
        # Give the connection back now, not when the stream closes hours later
        db.close()

    # Subscribed before the response starts, so the frontend's catch-up fetch
    # when the stream opens cannot miss an event published in between
    queue = hub.subscribe(session_id)
    # Its end is logged with the request (core/request_log.py), with how long it lasted
    log.info("A window started following session %s live", session_id, extra={"session_id": session_id})

    # Async so Starlette runs it on the event loop, which owns the hub; a sync
    # function would run in the threadpool, racing subscribe and publish
    async def unsubscribe() -> None:
        hub.unsubscribe(session_id, queue)

    return StreamingResponse(
        event_stream(queue),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
        # Runs however the stream ends, the frontend disconnecting included
        background=BackgroundTask(unsubscribe),
    )
