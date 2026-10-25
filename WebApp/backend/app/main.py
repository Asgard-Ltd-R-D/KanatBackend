import asyncio
import math
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config.settings import settings
from app.core.router import include_routers
from app.services import camera_sync, detection_sync


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Keeps MediaMTX's camera paths in step with the database while the app
    # runs, and the Detection Service's Run on the Session to watch
    loops = [camera_sync.run_forever(), detection_sync.run_forever()] if settings.camera_sync_interval_s > 0 else []
    tasks = [asyncio.create_task(loop) for loop in loops]
    yield
    for task in tasks:
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


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # FastAPI's own 422, but a refused NaN or infinity is echoed back as text:
    # JSON cannot carry it, and the answer would fail as a 500
    non_finite_as_text = {float: lambda v: v if math.isfinite(v) else str(v)}
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors(), custom_encoder=non_finite_as_text)})


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
