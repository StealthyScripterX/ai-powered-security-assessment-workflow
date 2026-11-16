from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services import environment_service


async def _attest(client, headers, poc_request_id, dimension, status_value, text="attested"):
    return await client.put(
        f"/api/poc-requests/{poc_request_id}/environment-readiness/{dimension}",
        headers=headers,
        json={"status": status_value, "attestation_text": text, "supporting_evidence_ids": []},
    )


ALL_SEVEN = [
    "Isolation",
    "AccessControl",
    "TestData",
    "ConfigBaseline",
    "Logging",
    "BackupRollback",
    "Decommissioning",
]


async def test_requester_role_cannot_attest_environment(client, authed_requester, submitted_scope):
    """D4-Environment-Readiness.md section 7: the Requester is
    structurally not the Environment Owner -- RBAC blocks this before
    the deeper same-person separation-of-duties check in
    app/services/environment_service.py even runs.
    """
    poc_request_id = submitted_scope["poc_request_id"]
    res = await _attest(client, authed_requester, poc_request_id, "Isolation", "Attested")
    assert res.status_code == 403


async def test_full_sign_off_across_all_seven_dimensions(client, environment_owner_identity, submitted_scope):
    poc_request_id = submitted_scope["poc_request_id"]
    headers = environment_owner_identity["headers"]

    for dim in ALL_SEVEN:
        res = await _attest(client, headers, poc_request_id, dim, "Attested")
        assert res.status_code == 200, res.text

    signoff = await client.get(f"/api/poc-requests/{poc_request_id}/environment-readiness/signoff", headers=headers)
    assert signoff.status_code == 200
    assert signoff.json()["final_signoff_boolean"] is True


async def test_signoff_false_while_any_dimension_not_started(client, environment_owner_identity, submitted_scope):
    poc_request_id = submitted_scope["poc_request_id"]
    headers = environment_owner_identity["headers"]
    for dim in ALL_SEVEN[:-1]:  # leave Decommissioning untouched
        await _attest(client, headers, poc_request_id, dim, "Attested")

    signoff = await client.get(f"/api/poc-requests/{poc_request_id}/environment-readiness/signoff", headers=headers)
    assert signoff.json()["final_signoff_boolean"] is False


async def test_isolation_exception_can_never_be_accepted(
    client, environment_owner_identity, reviewer_identity, submitted_scope
):
    """D4-Environment-Readiness.md section 6: Isolation and AccessControl
    are non-waivable -- enforced at the data layer, not just a UI rule.
    """
    poc_request_id = submitted_scope["poc_request_id"]
    await _attest(client, environment_owner_identity["headers"], poc_request_id, "Isolation", "Attested-with-Exception")

    res = await client.post(
        f"/api/poc-requests/{poc_request_id}/environment-readiness/Isolation/exception",
        headers=reviewer_identity["headers"],
        json={
            "issue_description": "Network segmentation not fully verified yet.",
            "risk_assessment": "Could allow lateral movement.",
            "compensating_controls": ["firewall rule review pending"],
            "disposition": "Accepted",
            "disposition_rationale": "We'll allow it anyway.",
            "remediation_owner": reviewer_identity["user_id"],
            "remediation_deadline": str(date.today() + timedelta(days=7)),
            "expiry_date": str(date.today() + timedelta(days=30)),
        },
    )
    assert res.status_code == 422
    assert "non-waivable" in res.json()["detail"]


async def test_waivable_dimension_exception_accepted_counts_toward_signoff(
    client, environment_owner_identity, reviewer_identity, submitted_scope
):
    poc_request_id = submitted_scope["poc_request_id"]
    headers = environment_owner_identity["headers"]
    for dim in ALL_SEVEN:
        target_status = "Attested-with-Exception" if dim == "BackupRollback" else "Attested"
        await _attest(client, headers, poc_request_id, dim, target_status)

    res = await client.post(
        f"/api/poc-requests/{poc_request_id}/environment-readiness/BackupRollback/exception",
        headers=reviewer_identity["headers"],
        json={
            "issue_description": "Backup not yet tested end to end.",
            "risk_assessment": "Rollback might be slower than planned.",
            "compensating_controls": ["manual snapshot taken"],
            "disposition": "Accepted",
            "disposition_rationale": "Compensating controls are adequate for this scope.",
            "remediation_owner": reviewer_identity["user_id"],
            "remediation_deadline": str(date.today() + timedelta(days=7)),
            "expiry_date": str(date.today() + timedelta(days=30)),
        },
    )
    assert res.status_code == 200, res.text

    signoff = await client.get(f"/api/poc-requests/{poc_request_id}/environment-readiness/signoff", headers=headers)
    assert signoff.json()["final_signoff_boolean"] is True


async def test_expired_exception_forces_signoff_false(
    client, environment_owner_identity, reviewer_identity, submitted_scope
):
    poc_request_id = submitted_scope["poc_request_id"]
    headers = environment_owner_identity["headers"]
    for dim in ALL_SEVEN:
        target_status = "Attested-with-Exception" if dim == "BackupRollback" else "Attested"
        await _attest(client, headers, poc_request_id, dim, target_status)

    await client.post(
        f"/api/poc-requests/{poc_request_id}/environment-readiness/BackupRollback/exception",
        headers=reviewer_identity["headers"],
        json={
            "issue_description": "Backup not yet tested.",
            "risk_assessment": "Minor.",
            "compensating_controls": [],
            "disposition": "Accepted",
            "disposition_rationale": "Accepted with an already-expired window for this test.",
            "remediation_owner": reviewer_identity["user_id"],
            "remediation_deadline": str(date.today() - timedelta(days=1)),
            "expiry_date": str(date.today() - timedelta(days=1)),  # already expired
        },
    )

    signoff = await client.get(f"/api/poc-requests/{poc_request_id}/environment-readiness/signoff", headers=headers)
    assert signoff.json()["final_signoff_boolean"] is False


async def test_revoking_attested_dimension_reverts_to_in_progress_not_not_started(
    client, environment_owner_identity, submitted_scope
):
    poc_request_id = submitted_scope["poc_request_id"]
    headers = environment_owner_identity["headers"]
    await _attest(client, headers, poc_request_id, "Logging", "Attested")

    revoke = await client.post(
        f"/api/poc-requests/{poc_request_id}/environment-readiness/Logging/revoke", headers=headers
    )
    assert revoke.status_code == 204

    attestations = await client.get(f"/api/poc-requests/{poc_request_id}/environment-readiness", headers=headers)
    row = next(a for a in attestations.json() if a["dimension"] == "Logging")
    assert row["status"] == "In Progress"  # not "Not Started" -- the prior attempt is a fact, not erased


async def test_disposition_authorizer_cannot_be_the_environment_owner_who_raised_it(
    client, environment_owner_identity, submitted_scope
):
    poc_request_id = submitted_scope["poc_request_id"]
    headers = environment_owner_identity["headers"]
    # EnvironmentOwner role cannot even call the disposition endpoint
    # (RBAC requires SecurityReviewer or FinalApprover) -- confirms the
    # separation of duties at the route level, independent of the
    # service-layer same-person check.
    await _attest(client, headers, poc_request_id, "TestData", "Attested-with-Exception")
    res = await client.post(
        f"/api/poc-requests/{poc_request_id}/environment-readiness/TestData/exception",
        headers=headers,
        json={
            "issue_description": "x",
            "risk_assessment": "x",
            "compensating_controls": [],
            "disposition": "Accepted",
            "disposition_rationale": "x",
            "remediation_owner": environment_owner_identity["user_id"],
            "remediation_deadline": str(date.today() + timedelta(days=7)),
            "expiry_date": str(date.today() + timedelta(days=30)),
        },
    )
    assert res.status_code == 403


async def test_service_layer_blocks_self_attestation_even_if_role_somehow_matched(
    client, authed_requester, submitted_scope, db_engine
):
    """Defense in depth: even if a caller somehow held the EnvironmentOwner
    role AND were the Requester for this exact POC (RBAC already
    prevents this at the route in practice), the service function's own
    same-person check independently refuses it.
    """
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.models.poc_request import PocRequest

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        result = await session.execute(
            select(PocRequest).where(PocRequest.id == submitted_scope["poc_request_id"])
        )
        poc_request = result.scalar_one()
        requester_id = poc_request.requester_id

        with pytest.raises(environment_service.ValidationError):
            await environment_service.attest_dimension(
                session,
                poc_request_id=submitted_scope["poc_request_id"],
                dimension="Isolation",
                status="Attested",
                attestation_text="self-attesting",
                environment_owner_id=requester_id,  # same person as the requester
                requester_id_of_poc=requester_id,
            )
