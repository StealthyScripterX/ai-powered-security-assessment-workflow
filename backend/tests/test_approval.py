"""Integration tests driving the full pipeline through to approval --
the P1-P4 preconditions (D5-Approval-Audit.md section 6) are the single
most safety-critical mechanism in this codebase.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.api.deps import model_client_dependency
from app.main import app

ALL_SEVEN = [
    "Isolation",
    "AccessControl",
    "TestData",
    "ConfigBaseline",
    "Logging",
    "BackupRollback",
    "Decommissioning",
]


async def _publish_policy(client, platform_owner_headers):
    return await client.post(
        "/api/admin/policy-config",
        headers=platform_owner_headers,
        json={
            "layer1_completeness_threshold": 0.5,
            "layer2_policy_hooks": [],
            "layer3_weights": {"f1_pending_review_discount": 0.5, "overall_multiplier": 1.0},
            "layer3_thresholds": {"low_max": 33, "medium_max": 66},
        },
    )


async def _sign_off_everything(client, env_headers, poc_request_id):
    for dim in ALL_SEVEN:
        res = await client.put(
            f"/api/poc-requests/{poc_request_id}/environment-readiness/{dim}",
            headers=env_headers,
            json={"status": "Attested", "attestation_text": "ok", "supporting_evidence_ids": []},
        )
        assert res.status_code == 200, res.text


@pytest.fixture
def fake_mapping_client():
    from tests.conftest import DynamicMappingFakeClient

    return DynamicMappingFakeClient(confidence="High")


async def test_engine_refuses_without_policy_config(client, authed_requester, answered_questionnaire):
    """With nothing configured at all, OD-10 (Layer 1) is the FIRST
    thing missing -- the engine terminal-fails at Layer 1 with
    Insufficient Information (a real, persisted outcome; this is BR-009a
    working as designed, not an engine refusal) before Layer 3's OD-15/
    OD-16 would even be reached. Fixed order, BR-016.
    """
    poc_request_id = answered_questionnaire[0]["poc_request_id"]
    res = await client.post(
        f"/api/poc-requests/{poc_request_id}/recommendation/recompute", headers=authed_requester
    )
    assert res.status_code == 200
    assert res.json()["outcome"] == "INSUFFICIENT_INFORMATION"


async def test_engine_refuses_at_layer3_when_only_od15_16_unconfigured(
    client, authed_requester, answered_questionnaire, environment_owner_identity, platform_owner_identity
):
    """Layer 1 (OD-10) and Layer 2 (structural, no OD needed) both pass
    here; the engine still cannot produce GO/NO-GO because OD-15/OD-16
    are unconfigured -- the REFUSED signal, never a fabricated outcome.
    """
    poc_request_id = answered_questionnaire[0]["poc_request_id"]
    publish = await client.post(
        "/api/admin/policy-config",
        headers=platform_owner_identity["headers"],
        json={"layer1_completeness_threshold": 0.5, "layer2_policy_hooks": []},
    )
    assert publish.status_code == 201
    await _sign_off_everything(client, environment_owner_identity["headers"], poc_request_id)

    res = await client.post(
        f"/api/poc-requests/{poc_request_id}/recommendation/recompute", headers=authed_requester
    )
    assert res.status_code == 503
    assert "OD-15" in str(res.json()["detail"])
    assert "OD-16" in str(res.json()["detail"])


async def test_full_happy_path_to_approved(
    client,
    authed_requester,
    answered_questionnaire,
    environment_owner_identity,
    approver_identity,
    platform_owner_identity,
    fake_mapping_client,
    submitted_scope,
):
    poc_request_id = answered_questionnaire[0]["poc_request_id"]

    policy = await _publish_policy(client, platform_owner_identity["headers"])
    assert policy.status_code == 201, policy.text

    app.dependency_overrides[model_client_dependency] = lambda: fake_mapping_client
    try:
        mapped = await client.post(f"/api/poc-requests/{poc_request_id}/mappings/generate", headers=authed_requester)
    finally:
        del app.dependency_overrides[model_client_dependency]
    assert mapped.status_code == 200, mapped.text

    await _sign_off_everything(client, environment_owner_identity["headers"], poc_request_id)

    rec = await client.post(
        f"/api/poc-requests/{poc_request_id}/recommendation/recompute", headers=authed_requester
    )
    assert rec.status_code == 200, rec.text
    recommendation = rec.json()
    assert recommendation["outcome"] == "GO"

    decide = await client.post(
        f"/api/poc-requests/{poc_request_id}/approval-request/decisions",
        headers=approver_identity["headers"],
        json={"decision": "Approved", "rationale": "All mandatory controls covered, environment signed off clean."},
    )
    assert decide.status_code == 200, decide.text
    decision = decide.json()
    assert decision["decision"] == "Approved"
    assert decision["matched_ai_recommendation"] is True
    assert decision["recommendation_was_stale"] is False


async def test_approval_blocked_by_p1_incomplete_signoff(
    client,
    authed_requester,
    answered_questionnaire,
    environment_owner_identity,
    approver_identity,
    platform_owner_identity,
    fake_mapping_client,
):
    """GO must remain impossible without complete Environment Owner
    sign-off -- here the engine would still say NO-GO (B-01), and even if
    it somehow didn't, P1 is re-checked independently at commit time.
    """
    poc_request_id = answered_questionnaire[0]["poc_request_id"]
    await _publish_policy(client, platform_owner_identity["headers"])

    # Sign off only 6 of 7 dimensions -- environment_readiness_submitted
    # is True (at least one dimension touched) but final_signoff_boolean
    # stays False, so B-01 fires (NO-GO), not Layer 1's "not started" gap.
    for dim in ALL_SEVEN[:-1]:
        await client.put(
            f"/api/poc-requests/{poc_request_id}/environment-readiness/{dim}",
            headers=environment_owner_identity["headers"],
            json={"status": "Attested", "attestation_text": "ok", "supporting_evidence_ids": []},
        )

    rec = await client.post(
        f"/api/poc-requests/{poc_request_id}/recommendation/recompute", headers=authed_requester
    )
    assert rec.json()["outcome"] == "NO-GO"  # B-01 fired

    decide = await client.post(
        f"/api/poc-requests/{poc_request_id}/approval-request/decisions",
        headers=approver_identity["headers"],
        json={"decision": "Approved", "rationale": "Trying to approve anyway."},
    )
    assert decide.status_code == 409
    assert "P1" in decide.json()["detail"]["failed_preconditions"] or "P2" in decide.json()["detail"]["failed_preconditions"]


async def test_rejected_and_more_info_requested_are_unconditional(
    client,
    authed_requester,
    answered_questionnaire,
    environment_owner_identity,
    approver_identity,
    platform_owner_identity,
):
    """D5-Approval-Audit.md section 6: Rejected/MoreInfoRequested are
    always permitted regardless of staleness or unresolved blockers --
    rejecting a request never needs any precondition to pass.
    """
    poc_request_id = answered_questionnaire[0]["poc_request_id"]
    await _publish_policy(client, platform_owner_identity["headers"])
    # Touch one dimension (environment_readiness_submitted=True) but
    # leave sign-off incomplete -- B-01 fires, engine says NO-GO.
    await client.put(
        f"/api/poc-requests/{poc_request_id}/environment-readiness/Isolation",
        headers=environment_owner_identity["headers"],
        json={"status": "In Progress", "attestation_text": "started", "supporting_evidence_ids": []},
    )
    rec = await client.post(
        f"/api/poc-requests/{poc_request_id}/recommendation/recompute", headers=authed_requester
    )
    assert rec.json()["outcome"] == "NO-GO"

    rejected = await client.post(
        f"/api/poc-requests/{poc_request_id}/approval-request/decisions",
        headers=approver_identity["headers"],
        json={"decision": "Rejected", "rationale": "Environment not ready; declining this request."},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["decision"] == "Rejected"


async def test_insufficient_information_cannot_be_approved(
    client, authed_requester, submitted_scope, platform_owner_identity, approver_identity
):
    """P3: Insufficient Information can never be Approved -- there is no
    path to approving an assessment the engine itself said was inadequate.
    """
    poc_request_id = submitted_scope["poc_request_id"]
    await _publish_policy(client, platform_owner_identity["headers"])
    # No questionnaire generated at all -> Mandatory domains unaddressed -> Layer 1 terminal.
    rec = await client.post(
        f"/api/poc-requests/{poc_request_id}/recommendation/recompute", headers=authed_requester
    )
    assert rec.json()["outcome"] == "INSUFFICIENT_INFORMATION"

    decide = await client.post(
        f"/api/poc-requests/{poc_request_id}/approval-request/decisions",
        headers=approver_identity["headers"],
        json={"decision": "Approved", "rationale": "Approving anyway."},
    )
    assert decide.status_code == 409
    assert "P3" in decide.json()["detail"]["failed_preconditions"]


async def test_p4_stale_recommendation_triggers_synchronous_rerun(
    client,
    authed_requester,
    answered_questionnaire,
    environment_owner_identity,
    approver_identity,
    platform_owner_identity,
    fake_mapping_client,
):
    """D5-Approval-Audit.md section 6 / TASD-v1.0.md section 17.5: a
    stale Approved attempt is rejected AND the server synchronously
    re-runs the engine, handing back a fresh recommendation in the SAME
    response -- never a bare error.
    """
    poc_request_id = answered_questionnaire[0]["poc_request_id"]
    await _publish_policy(client, platform_owner_identity["headers"])

    app.dependency_overrides[model_client_dependency] = lambda: fake_mapping_client
    try:
        await client.post(f"/api/poc-requests/{poc_request_id}/mappings/generate", headers=authed_requester)
    finally:
        del app.dependency_overrides[model_client_dependency]

    await _sign_off_everything(client, environment_owner_identity["headers"], poc_request_id)
    rec1 = await client.post(
        f"/api/poc-requests/{poc_request_id}/recommendation/recompute", headers=authed_requester
    )
    assert rec1.json()["outcome"] == "GO"
    stale_version = rec1.json()["input_version"]

    # Invalidating change AFTER the recommendation was produced: revoke
    # one dimension (D4 section 8.3 -- itself an invalidating change).
    await client.post(
        f"/api/poc-requests/{poc_request_id}/environment-readiness/Logging/revoke",
        headers=environment_owner_identity["headers"],
    )

    decide = await client.post(
        f"/api/poc-requests/{poc_request_id}/approval-request/decisions",
        headers=approver_identity["headers"],
        json={"decision": "Approved", "rationale": "Acting on what I believe is still the current recommendation."},
    )
    assert decide.status_code == 409
    body = decide.json()["detail"]
    assert "P4" in body["failed_preconditions"] or "P1" in body["failed_preconditions"]
    if "P4" in body["failed_preconditions"]:
        assert body["fresh_recommendation"] is not None
        assert body["fresh_recommendation"]["input_version"] > stale_version


async def test_disagreement_rationale_required_when_rejecting_a_go(
    client,
    authed_requester,
    answered_questionnaire,
    environment_owner_identity,
    approver_identity,
    platform_owner_identity,
    fake_mapping_client,
):
    poc_request_id = answered_questionnaire[0]["poc_request_id"]
    await _publish_policy(client, platform_owner_identity["headers"])
    app.dependency_overrides[model_client_dependency] = lambda: fake_mapping_client
    try:
        await client.post(f"/api/poc-requests/{poc_request_id}/mappings/generate", headers=authed_requester)
    finally:
        del app.dependency_overrides[model_client_dependency]
    await _sign_off_everything(client, environment_owner_identity["headers"], poc_request_id)
    rec = await client.post(
        f"/api/poc-requests/{poc_request_id}/recommendation/recompute", headers=authed_requester
    )
    assert rec.json()["outcome"] == "GO"

    without_disagreement = await client.post(
        f"/api/poc-requests/{poc_request_id}/approval-request/decisions",
        headers=approver_identity["headers"],
        json={"decision": "Rejected", "rationale": "I disagree with the AI's GO recommendation."},
    )
    assert without_disagreement.status_code == 422

    with_disagreement = await client.post(
        f"/api/poc-requests/{poc_request_id}/approval-request/decisions",
        headers=approver_identity["headers"],
        json={
            "decision": "Rejected",
            "rationale": "I disagree with the AI's GO recommendation.",
            "disagreement_rationale": "The business justification is too thin for the systems in scope.",
        },
    )
    assert with_disagreement.status_code == 200, with_disagreement.text


async def test_no_override_endpoint_exists(client):
    """D5-Approval-Audit.md section 7: no override mechanism exists.
    There is no route anywhere that bypasses P1-P4.
    """
    for path in ["/api/override", "/api/admin/override", "/api/poc-requests/x/approval-request/override"]:
        res = await client.post(path)
        assert res.status_code == 404


async def test_requester_cannot_approve(client, authed_requester, answered_questionnaire):
    poc_request_id = answered_questionnaire[0]["poc_request_id"]
    res = await client.post(
        f"/api/poc-requests/{poc_request_id}/approval-request/decisions",
        headers=authed_requester,
        json={"decision": "Approved", "rationale": "x"},
    )
    assert res.status_code == 403
