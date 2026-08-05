"""FastAPI application entry point.

Run with:  uvicorn app.main:app --reload    (from the backend/ directory)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import (
    accounts,
    budgets,
    categories,
    dashboard,
    health,
    portfolio,
    recurring,
    reports,
    transactions,
)
from app.config import settings
from app.db import SessionLocal
from app.seed import run_seed
from app.services.scheduler import (
    run_recurring_generation,
    shutdown_scheduler,
    start_scheduler,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("finance_app")

FRONTEND_DIST = settings.data_dir.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    with SessionLocal() as session:
        result = run_seed(session)
    if result["categories_created"] or result["accounts_created"]:
        logger.info(
            "Seeded %s categories and %s accounts",
            result["categories_created"],
            result["accounts_created"],
        )
    logger.info("Database: %s", settings.db_path)

    # Catch up on anything that fell due while the app was closed, then keep
    # it current on a daily schedule. Both paths are idempotent.
    run_recurring_generation()
    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()


app = FastAPI(
    title="Finance App",
    description="Personal income, expense, and stock portfolio tracker.",
    version="0.1.0",
    lifespan=lifespan,
)

# Only needed for the Vite dev server on :5173; in production the frontend is
# served from this same origin as static files.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(accounts.router)
app.include_router(categories.router)
app.include_router(transactions.router)
app.include_router(recurring.router)
app.include_router(budgets.router)
app.include_router(portfolio.router)
app.include_router(dashboard.router)
app.include_router(reports.router)


class SPAStaticFiles(StaticFiles):
    """Static files with a single-page-app fallback.

    A hard refresh on a client-side route like /transactions asks the server
    for a file that doesn't exist. Serving index.html instead lets the router
    take over.

    Unknown /api/* paths must NOT get that treatment: this mount sits at "/"
    and therefore receives anything the API routers didn't match, so without
    the explicit check below a typo'd endpoint would return 200 with an HTML
    body instead of a 404, which is baffling to debug from the client side.
    """

    async def get_response(self, path: str, scope):
        # Tested against scope["path"], not `path`: StaticFiles runs the URL
        # through os.path.normpath, so on Windows `path` comes through as
        # "api\nope" and a "api/" prefix check would silently never match.
        if scope.get("path", "").startswith("/api/"):
            raise StarletteHTTPException(status_code=404, detail="Not Found")
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


def _mount_frontend(path: Path) -> None:
    """Serve the built SPA at / when it exists (after `npm run build`)."""
    if path.is_dir():
        app.mount("/", SPAStaticFiles(directory=path, html=True), name="frontend")
        logger.info("Serving frontend from %s", path)
    else:
        logger.info(
            "No frontend build at %s — run `npm run build` in frontend/, "
            "or use the Vite dev server on :5173",
            path,
        )


_mount_frontend(FRONTEND_DIST)
