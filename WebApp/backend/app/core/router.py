from fastapi import FastAPI

from app.routers import bullets, cameras, export, live, sessions


def include_routers(app: FastAPI) -> None:
    app.include_router(sessions.router)
    app.include_router(bullets.router)
    app.include_router(export.router)
    app.include_router(live.router)
    app.include_router(cameras.router)
