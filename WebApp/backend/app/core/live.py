import asyncio
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator

from anyio import from_thread

from app.schemas.live import LiveEvent

# Events a subscriber may fall behind by before it is cut off. It reconnects
# and catches up from GET /sessions/{id}.
QUEUE_SIZE = 256
# A ping this often on an idle stream: a vanished frontend shows up as a failed
# write, and the frontend reconnects when pings stop (a frozen backend)
PING_S = 15
# How long the browser waits before reconnecting a dropped stream
RETRY_MS = 1000


class LiveHub:
    """One queue per frontend watching a Session, fed with that Session's events.

    It lives on the event loop. Route handlers are sync and run in the
    threadpool, so they publish through `publish_from_thread`.

    It lives in this process's memory, so uvicorn must run a single worker: with
    several, a bullet reported to one would never reach a frontend on another.
    """

    def __init__(self) -> None:
        self._subscribers: dict[uuid.UUID, set[asyncio.Queue[str | None]]] = defaultdict(set)

    def subscribe(self, session_id: uuid.UUID) -> asyncio.Queue[str | None]:
        queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._subscribers[session_id].add(queue)
        return queue

    def unsubscribe(self, session_id: uuid.UUID, queue: asyncio.Queue[str | None]) -> None:
        subscribers = self._subscribers.get(session_id)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            del self._subscribers[session_id]

    def publish(self, session_id: uuid.UUID, event: LiveEvent) -> None:
        message = event.model_dump_json()
        for queue in list(self._subscribers.get(session_id, ())):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # Cut it off rather than block the others: None ends its stream,
                # and the browser reconnects and catches up
                self.unsubscribe(session_id, queue)
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(None)

    def publish_from_thread(self, session_id: uuid.UUID, event: LiveEvent) -> None:
        from_thread.run_sync(self.publish, session_id, event)


async def event_stream(queue: asyncio.Queue[str | None]) -> AsyncIterator[str]:
    """A subscriber's queue as a Server-Sent Events stream."""
    yield f"retry: {RETRY_MS}\n\n"
    while True:
        try:
            message = await asyncio.wait_for(queue.get(), PING_S)
        except TimeoutError:
            # A named event, so it does not reach the frontend's onmessage
            yield "event: ping\ndata: ping\n\n"
            continue
        if message is None:
            return
        yield f"data: {message}\n\n"


hub = LiveHub()
