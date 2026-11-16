"""Shared enums for the Decision Engine, kept in their own module so
app/models/engine.py and app/services/engine.py (which needs the same
enums plus the non-persisted REFUSED signal) don't have to import
model internals into each other.
"""
from __future__ import annotations

import enum


class EngineOutcome(str, enum.Enum):
    """The three BR-009 outcomes ONLY. 'REFUSED' is deliberately NOT a
    member of this enum -- it is a non-persisted, operational signal
    (see app/services/engine.py) and must never be written to the
    `recommendation` table, which is exactly why it is not a legal value
    here.
    """

    GO = "GO"
    NO_GO = "NO-GO"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"


class RiskTier(str, enum.Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
