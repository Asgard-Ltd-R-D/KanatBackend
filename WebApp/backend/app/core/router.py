from fastapi import FastAPI

from app.routers import bullets, export, sessions


def include_routers(app: FastAPI) -> None:
    app.include_router(sessions.router)
    app.include_router(bullets.router)
    app.include_router(export.router)
