from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import OperationalError
from starlette.requests import Request

from app.api.routes import (
    approval,
    assessment,
    audit,
    auth,
    engine,
    environment,
    evidence,
    mapping,
    od_registry,
    poc_requests,
    questionnaire,
)
from app.database import AsyncSessionLocal, engine as db_engine, init_models
from app.services.catalog_seed import seed_catalog_if_empty
from app.services.od_registry_seed import seed_od_registry_if_empty
from app.services.storage import StorageNotConfiguredError
from app.services.versioning import VersionConflictError


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_models()
    async with AsyncSessionLocal() as session:
        await seed_catalog_if_empty(session)
        await seed_od_registry_if_empty(session)
    yield


app = FastAPI(
    title="AI-Powered Security Assessment & POC Approval Workflow",
    version="0.1.0-phase1",
    description=(
        "Phase 1 vertical slice: Scope Submission -> AI Scope Analysis -> "
        "11-15 Questions -> Answer Submission -> Database Persistence. "
        "See IMPLEMENTATION-NOTES.md for what this phase does and does not implement."
    ),
    lifespan=lifespan,
)


@app.exception_handler(VersionConflictError)
async def _version_conflict_handler(_request: Request, exc: VersionConflictError):
    """Centralizes the one place every route that transitively calls
    app.services.versioning.bump_input_version needs to handle this --
    an optimistic-concurrency conflict (see VersionConflictError's
    docstring), surfaced as 409 Conflict rather than letting it escape
    as an unhandled 500. The client's correct response is to retry the
    request.
    """
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(OperationalError)
async def _sqlite_locked_handler(_request: Request, exc: OperationalError):
    """SQLite's OWN concurrency guarantee -- a second writer that
    genuinely collides with an in-progress transaction on a different
    connection gets `OperationalError: database is locked` straight
    from sqlite3, confirmed live by
    tests/test_evidence_concurrency.py (two real independent
    connections, not test_security.py's shared single-connection
    fixture). This is SQLite correctly refusing the second writer, not
    corruption -- surfaced as 409 Conflict (retry), same contract as
    VersionConflictError above, rather than an unhandled 500. A
    genuinely different OperationalError (not a locking message) is
    a real bug and is re-raised as the 500 it should be, never masked.
    """
    from fastapi.responses import JSONResponse

    if "locked" not in str(exc).lower():
        raise exc
    return JSONResponse(status_code=409, content={"detail": "Concurrent database write conflict; retry the request."})


@app.exception_handler(StorageNotConfiguredError)
async def _storage_not_configured_handler(_request: Request, exc: StorageNotConfiguredError):
    """Same fail-closed contract as the AI provider's 503
    (app/api/deps.py:model_client_dependency) -- an explicit refusal,
    never a fabricated or silently-degraded storage operation.
    """
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=503, content={"detail": str(exc)})


app.include_router(auth.router)
# assessment.router's literal "/queue" path must be registered BEFORE
# poc_requests.router's "/{poc_request_id}" -- both are single-segment
# paths under the same "/api/poc-requests" prefix, and FastAPI/Starlette
# resolves an ambiguous match by registration order, not by literal-vs-
# parameter specificity.
app.include_router(assessment.router)
app.include_router(poc_requests.router)
app.include_router(questionnaire.router)
app.include_router(mapping.router)
app.include_router(evidence.router)
app.include_router(environment.router)
app.include_router(engine.router)
app.include_router(approval.router)
app.include_router(audit.router)
app.include_router(od_registry.router)

templates = Jinja2Templates(directory="app/web/templates")
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")


PAGES = {
    "/login": "login.html",
    "/requester": "requester.html",
    "/queue": "queue.html",
    "/assessment": "assessment.html",
    "/compliance": "compliance.html",
    "/od-registry": "od_registry.html",
}
"""Server-rendered HTML + vanilla JS -- a declared stand-in for the
React SPA architecture/TASD-v1.0.md section 9.1 specifies (see
IMPLEMENTATION-NOTES.md). Every page calls the exact same JSON API a
future SPA would; no server-side logic is duplicated behind any of them.
Auth/role gating happens client-side in app/web/static/app.js for UX
only -- the real enforcement is server-side RBAC on every API call
(app/security.py), re-checked regardless of what a page shows or hides.
"""


@app.get("/", include_in_schema=False)
async def root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/login")


def _register_page(path: str, template_name: str) -> None:
    async def _handler(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, template_name, {})

    app.get(path, response_class=HTMLResponse, include_in_schema=False)(_handler)


for _path, _template in PAGES.items():
    _register_page(_path, _template)


@app.get("/healthz")
async def healthz() -> dict:
    """Liveness only -- the process is up and able to answer HTTP at
    all. Deliberately does NOT touch the database (a liveness probe
    that depends on a downstream dependency can cause an orchestrator
    to kill-loop a healthy process during a transient DB blip); that
    check is /readyz's job.
    """
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict:
    """Readiness: actually exercises the database connection (a real
    SELECT 1, not just "the engine object exists") so an orchestrator
    stops routing traffic here if the configured PostgreSQL/SQLite is
    unreachable -- the one dependency this app cannot function without.
    Returns 503 (via the exception below propagating as a 500 is wrong
    for a readiness probe) on failure rather than a fabricated "ok".
    """
    import logging

    from fastapi import HTTPException, status
    from sqlalchemy import text

    try:
        async with db_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 -- readiness probe: report, don't fabricate
        # Logged server-side, not returned in the response body -- a
        # DB connection error can embed the DSN (credentials included)
        # in some drivers' exception text.
        logging.getLogger(__name__).exception("readiness check: database unreachable")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unreachable")
    return {"status": "ready", "database": "ok"}
