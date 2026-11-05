"""FastAPI application: JSON API under /api and the built React app at /."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from . import __version__
from .api import api_router
from .config import FRONTEND_DIST
from .database import SessionLocal, init_db
from .models import Run
from .seed import seed_if_empty

MISSING_FRONTEND = """<!doctype html><html><head><title>AgentProof</title></head>
<body style="font-family:system-ui;padding:40px;max-width:640px">
<h1>AgentProof API is running</h1>
<p>The web UI has not been built (<code>frontend/dist</code> is missing).
Run <code>npm install && npm run build</code> inside <code>frontend/</code>, then restart.</p>
<p>The API is available at <a href="/docs">/docs</a>.</p></body></html>"""


def _recover_interrupted_runs() -> None:
    """Runs that were in progress when the server stopped can never finish – mark them failed."""
    with SessionLocal() as db:
        for run in db.scalars(select(Run).where(Run.status.in_(("queued", "running")))):
            run.status = "failed"
            run.error = "Interrupted: the server was stopped while this run was in progress. Start it again."
        db.commit()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    _recover_interrupted_runs()
    seed_if_empty()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="AgentProof", version=__version__, lifespan=lifespan,
                  description="Multi-turn LLM virtual agent evaluator for contact-centre QA.")
    app.include_router(api_router)

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": f"Unexpected server error: {exc.__class__.__name__}: {exc}"})

    assets = FRONTEND_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    def spa(full_path: str) -> FileResponse | HTMLResponse | JSONResponse:
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        candidate = (FRONTEND_DIST / full_path).resolve()
        if full_path and candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        index = FRONTEND_DIST / "index.html"
        return FileResponse(index) if index.is_file() else HTMLResponse(MISSING_FRONTEND)

    return app


app = create_app()
