from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db import init_db
from app.routers import dashboard, imports, planning, settings, transactions

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="Finanças Locais",
        description="Dashboard financeiro pessoal 100% local",
        lifespan=lifespan,
    )
    application.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    application.include_router(dashboard.router)
    application.include_router(transactions.router)
    application.include_router(imports.router)
    application.include_router(planning.router)
    application.include_router(settings.router)
    return application


app = create_app()
