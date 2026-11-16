from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AuditEntryOut(BaseModel):
    sequence_number: int
    entry_hash: str
    previous_entry_hash: str
    actor_id: str | None
    actor_kind: str
    action_type: str
    affected_object_type: str
    affected_object_id: str
    before_state: dict | None
    after_state: dict | None
    recorded_at: datetime

    model_config = {"from_attributes": True}


class ChainVerificationOut(BaseModel):
    ok: bool
    first_broken_sequence_number: int | None
    entries_checked: int
