from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.core.router import include_routers

app = FastAPI(title=settings.app_title, version=settings.app_version)

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
