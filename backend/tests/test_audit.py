"""Audit trail tests: hash-chain integrity (BR-017) and same-transaction
atomicity with the state change it describes (BR-019).
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.audit import ActorKind
from app.services import audit_service


async def test_hash_chain_verifies_after_several_entries(db_engine):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        for i in range(5):
            await audit_service.record_event(
                session,
                actor_id="user-1",
                actor_kind=ActorKind.REQUESTER,
                action_type=f"test_event_{i}",
                affected_object_type="poc_request",
                affected_object_id="poc-1",
                after_state={"n": i},
            )
        await session.commit()

        ok, break_point = await audit_service.verify_chain(session)
        assert ok is True
        assert break_point is None


async def test_tampering_with_an_entry_is_detected_at_exact_point(db_engine):
    from sqlalchemy import select

    from app.models.audit import AuditEntry

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        for i in range(4):
            await audit_service.record_event(
                session,
                actor_id="user-1",
                actor_kind=ActorKind.REQUESTER,
                action_type=f"event_{i}",
                affected_object_type="poc_request",
                affected_object_id="poc-1",
                after_state={"n": i},
            )
        await session.commit()

        # Simulate tampering (bypassing the INSERT-only convention this
        # phase enforces at the application layer -- a real deployment
        # with PostgreSQL role grants per TASD-v1.0.md section 11.10 would
        # reject this write outright; that grant-level enforcement is
        # deferred, per IMPLEMENTATION-NOTES.md, to the PostgreSQL phase).
        result = await session.execute(select(AuditEntry).where(AuditEntry.sequence_number == 2))
        entry = result.scalar_one()
        entry.after_state = {"n": "TAMPERED"}
        await session.commit()

        ok, break_point = await audit_service.verify_chain(session)
        assert ok is False
        assert break_point == 2


async def test_audit_entry_persists_atomically_with_scope_submission(client, authed_requester, db_engine):
    """BR-019: a successful scope submission produces exactly one
    matching audit entry, committed together with the state change.
    `db_engine` is the same engine the `client` fixture wired the app's
    `get_db` override to (pytest caches it once per test), so querying
    through it here sees exactly what the request committed.
    """
    res = await client.post(
        "/api/poc-requests",
        headers=authed_requester,
        json={
            "project_description": "desc",
            "systems_in_scope": "sys",
            "business_justification": "just",
            "intake_form_data": {},
        },
    )
    assert res.status_code == 201
    poc_request_id = res.json()["poc_request_id"]

    from sqlalchemy import select

    from app.models.audit import AuditEntry

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        result = await session.execute(
            select(AuditEntry).where(
                AuditEntry.affected_object_id == poc_request_id,
                AuditEntry.action_type == "scope_submitted",
            )
        )
        entries = result.scalars().all()
        assert len(entries) == 1
        assert entries[0].actor_kind == ActorKind.REQUESTER
