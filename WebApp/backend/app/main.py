import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.core.router import include_routers
from app.services import camera_sync


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Keeps MediaMTX's camera paths in step with the database while the app runs
    task = asyncio.create_task(camera_sync.run_forever()) if settings.camera_sync_interval_s > 0 else None
    yield
    if task:
        task.cancel()


app = FastAPI(title=settings.app_title, version=settings.app_version, lifespan=lifespan)

# Electron renderer runs on a file:// origin in production and
# localhost in dev — allow both rather than locking to a specific port.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

include_routers(app)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
