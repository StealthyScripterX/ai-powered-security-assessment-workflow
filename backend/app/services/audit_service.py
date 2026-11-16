"""Audit writer: canonical serialization + SHA-256 hash chaining +
same-transaction persistence.

architecture/TASD-v1.0.md section 18.2 / section 18.3. `record_event` must be
called with the SAME `AsyncSession` the caller's state-changing write
used, and BEFORE that session is committed -- the audit row and the
state-changing row then commit or roll back together as one database
transaction, which is the literal mechanism behind BR-019 ("workflow
transition and its audit event persist atomically; failed audit write
blocks the transition"). There is deliberately no `try/except` around
the audit insert anywhere this is called: if it raises, the caller's
whole transaction is expected to roll back.

Concurrency note: architecture/TASD-v1.0.md section 18.2 requires the chain
tail to be read-and-advanced under a lock so two concurrent writers can
never race on `previous_entry_hash`. This phase's SQLite dev database
has no meaningful concurrent-writer scenario (SQLite serializes writers
at the file level) and no FOR UPDATE row-lock support in the TASD sense,
so that specific guarantee is NOT yet implemented as a real row lock --
flagged in IMPLEMENTATION-NOTES.md as a genuine gap to close when this
moves to PostgreSQL (section 18.2's `audit_chain_tail FOR UPDATE` design is
already specified and ready to implement there).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import ActorKind, AuditEntry

GENESIS_HASH = "0" * 64


def _canonical_serialize(entry_content: dict[str, Any]) -> bytes:
    """Fixed field order, UTF-8, no non-significant whitespace.

    architecture/TASD-v1.0.md section 18.2's `canonical_serialize`.
    """
    ordered_fields = [
        "actor_id",
        "actor_kind",
        "action_type",
        "affected_object_type",
        "affected_object_id",
        "before_state",
        "after_state",
    ]
    ordered = {k: entry_content.get(k) for k in ordered_fields}
    return json.dumps(ordered, separators=(",", ":"), sort_keys=False, default=str).encode("utf-8")


async def record_event(
    session: AsyncSession,
    *,
    actor_id: str | None,
    actor_kind: ActorKind,
    action_type: str,
    affected_object_type: str,
    affected_object_id: str,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
) -> AuditEntry:
    """Append one hash-chained audit entry inside the caller's transaction.

    Does NOT commit -- the caller commits once, after this call, so the
    audit row and the state-changing row(s) land atomically.
    """
    # FOR UPDATE: locks the tail row so two concurrent writers can never
    # both read the same previous_hash and compute two entries that
    # claim the same predecessor -- the real row lock section 18.2 asks
    # for (no-op under SQLite; a real lock under PostgreSQL, same code
    # path). Only locks when a tail row exists -- the very first entry
    # in the chain has no predecessor row to lock.
    result = await session.execute(
        select(AuditEntry.entry_hash)
        .order_by(AuditEntry.sequence_number.desc())
        .limit(1)
        .with_for_update()
    )
    previous_hash = result.scalar_one_or_none() or GENESIS_HASH

    entry_content = {
        "actor_id": actor_id,
        "actor_kind": actor_kind.value,
        "action_type": action_type,
        "affected_object_type": affected_object_type,
        "affected_object_id": affected_object_id,
        "before_state": before_state,
        "after_state": after_state,
    }
    serialized = _canonical_serialize(entry_content)
    entry_hash = hashlib.sha256(serialized + previous_hash.encode("utf-8")).hexdigest()

    entry = AuditEntry(
        entry_hash=entry_hash,
        previous_entry_hash=previous_hash,
        actor_id=actor_id,
        actor_kind=actor_kind,
        action_type=action_type,
        affected_object_type=affected_object_type,
        affected_object_id=affected_object_id,
        before_state=before_state,
        after_state=after_state,
    )
    session.add(entry)
    await session.flush()
    return entry


async def verify_chain(session: AsyncSession) -> tuple[bool, int | None]:
    """Recompute the chain from genesis and confirm every hash still matches.

    Returns (ok, first_broken_sequence_number_or_None). Mirrors
    architecture/TASD-v1.0.md section 18.4's `fn_verify_audit_chain`.
    """
    result = await session.execute(select(AuditEntry).order_by(AuditEntry.sequence_number.asc()))
    entries = result.scalars().all()

    expected_previous = GENESIS_HASH
    for entry in entries:
        content = {
            "actor_id": entry.actor_id,
            "actor_kind": entry.actor_kind.value,
            "action_type": entry.action_type,
            "affected_object_type": entry.affected_object_type,
            "affected_object_id": entry.affected_object_id,
            "before_state": entry.before_state,
            "after_state": entry.after_state,
        }
        recomputed = hashlib.sha256(
            _canonical_serialize(content) + expected_previous.encode("utf-8")
        ).hexdigest()
        if recomputed != entry.entry_hash:
            return False, entry.sequence_number
        expected_previous = entry.entry_hash

    return True, None
