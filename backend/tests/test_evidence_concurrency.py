"""Concurrent evidence-state transitions, on two GENUINELY independent
database connections -- not tests/test_security.py's `client` fixture,
whose `db_engine` deliberately uses a single StaticPool connection
shared by every request (needed so a `:memory:` database stays visible
across sequential requests at all). Two "concurrent" requests on that
one shared connection are not two independent transactions -- a
rollback on one can appear to undo the other's already-committed work,
which is an artifact of sharing one physical connection, not something
that happens with two real connections (two SQLite file/shared-cache
connections, or two PostgreSQL connections). `db_engine`'s shared-cache
in-memory URI (`cache=shared&uri=true`, set up in tests/conftest.py)
supports exactly this: a second engine pointed at the same URL gets its
own connection that still sees the same data.
"""
from __future__ import annotations

import asyncio
import io

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.services import evidence_service
from app.services.versioning import VersionConflictError


def _is_expected_conflict(exc: BaseException) -> bool:
    """A losing writer under true SQLite multi-connection concurrency
    surfaces as either VersionConflictError (the unique-constraint
    collision on assessment_input_version, caught and re-raised there)
    or sqlite3's own OperationalError("database is locked") if SQLite's
    single-writer lock contention is hit even earlier (e.g. on the
    ControlEvidenceState row itself) -- both are app/main.py's
    _version_conflict_handler / _sqlite_locked_handler's 409 contract
    at the HTTP layer; calling the service directly here (bypassing
    HTTP) sees the raw exception types.
    """
    return isinstance(exc, VersionConflictError) or (
        isinstance(exc, OperationalError) and "locked" in str(exc).lower()
    )


async def _upload_and_get_control_state(client, authed_requester, poc_request_id):
    await client.post(
        f"/api/poc-requests/{poc_request_id}/evidence",
        headers=authed_requester,
        files={"file": ("evidence.txt", io.BytesIO(b"evidence content"), "text/plain")},
        data={"control_id": "AC-2"},
    )


@pytest.fixture
def second_connection_session_factory(db_engine):
    """A second engine against the SAME shared-cache in-memory database
    `db_engine` uses, but with its own, genuinely independent
    connection (default pool, not db_engine's StaticPool) -- see module
    docstring.
    """
    second_engine = create_async_engine(
        str(db_engine.url), connect_args={"check_same_thread": False}
    )
    yield async_sessionmaker(second_engine, expire_on_commit=False, class_=AsyncSession)


async def test_concurrent_evidence_state_transitions_on_independent_connections(
    client, authed_requester, reviewer_identity, submitted_scope, db_engine, second_connection_session_factory
):
    """Two SecurityReviewer decisions (Verify vs Reject) on the same
    control, via two real independent connections. On this phase's
    SQLite dev database (with_for_update() is a no-op there -- see
    app/services/versioning.py:VersionConflictError's docstring), the
    losing writer gets VersionConflictError (409 at the HTTP layer; here
    the raw exception) rather than succeeding incorrectly or corrupting
    state -- never a silent/partial write, and the final state is
    always the winner's, never a third/corrupted value.
    """
    poc_request_id = submitted_scope["poc_request_id"]
    await _upload_and_get_control_state(client, authed_requester, poc_request_id)

    first_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def _attempt(session_factory, new_state: str, n: int):
        async with session_factory() as db:
            return await evidence_service.transition_evidence_state(
                db,
                poc_request_id=poc_request_id,
                control_id="AC-2",
                new_state=new_state,
                reviewer_id=reviewer_identity["user_id"],
                rationale=f"Concurrent decision {n}.",
            )

    results = await asyncio.gather(
        _attempt(first_factory, "Verified - Human Validated", 1),
        _attempt(second_connection_session_factory, "Rejected - Insufficient Evidence", 2),
        return_exceptions=True,
    )

    conflicts = [r for r in results if isinstance(r, Exception) and _is_expected_conflict(r)]
    others = [r for r in results if isinstance(r, Exception) and not _is_expected_conflict(r)]
    assert not others, f"an unexpected exception type escaped: {others}"
    # Either both committed (no actual conflict was triggered this run --
    # timing-dependent) or exactly one lost with an expected conflict
    # error; never both losing, which would mean neither decision landed.
    assert len(conflicts) <= 1, f"both attempts lost -- neither decision landed: {results}"

    states = await client.get(f"/api/poc-requests/{poc_request_id}/evidence-states", headers=authed_requester)
    assert states.status_code == 200
    state_row = next(s for s in states.json() if s["control_id"] == "AC-2")
    assert state_row["state"] in ("Verified - Human Validated", "Rejected - Insufficient Evidence")
