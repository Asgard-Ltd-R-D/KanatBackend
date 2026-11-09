"""Process-level write serialization, replacing SQLite's missing row locks.

`with_for_update()` (SELECT ... FOR UPDATE) is a no-op on SQLite, so the
read-modify-write sections that relied on a row lock — ranking a Session's
bullets, moving a Run's watched_until and places on — are no longer serialized by
the database. The backend is a single process (one uvicorn worker, plus its
threadpool and the background loops), so one lock held across each such section
restores that guarantee.

Write volume is low (bullets seconds apart, a tick every few seconds), so one
lock is enough. Hold it only around a read-modify-write on the database, never
across a network call, and never take it inside a section that already holds it
(no section here does), so it cannot deadlock.
"""
import threading

db_write = threading.Lock()
