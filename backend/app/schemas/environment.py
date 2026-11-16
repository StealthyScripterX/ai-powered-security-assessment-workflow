from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class AttestationIn(BaseModel):
    status: str = Field(pattern="^(Not Started|In Progress|Attested|Attested-with-Exception)$")
    attestation_text: str | None = None
    supporting_evidence_ids: list[str] = Field(default_factory=list)


class AttestationOut(BaseModel):
    poc_request_id: str
    dimension: str
    status: str
    attestation_text: str | None
    environment_owner_id: str | None
    attested_at: datetime | None

    model_config = {"from_attributes": True}


class ExceptionIn(BaseModel):
    issue_description: str = Field(min_length=1)
    risk_assessment: str = Field(min_length=1)
    compensating_controls: list[str] = Field(default_factory=list)
    disposition: str = Field(pattern="^(Accepted|Rejected|Deferred)$")
    disposition_rationale: str = Field(min_length=1)
    environment_owner_id_for_dimension: str | None = None
    remediation_owner: str | None = None
    remediation_deadline: date | None = None
    expiry_date: date


class SignoffOut(BaseModel):
    poc_request_id: str
    final_signoff_boolean: bool
