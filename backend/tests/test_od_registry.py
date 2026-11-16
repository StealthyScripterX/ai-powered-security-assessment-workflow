"""Organizational Decision Registry tests: propose -> approve/reject ->
activate, PlatformOwner-only writes, fail-closed dependent engine
behavior until an OD is both Approved and Activated.
"""
from __future__ import annotations


async def test_registry_seeds_six_blocking_decisions(client, authed_requester):
    res = await client.get("/api/organizational-decisions", headers=authed_requester)
    assert res.status_code == 200
    ids = {od["id"] for od in res.json()}
    assert ids == {"OD-01", "OD-06", "OD-07", "OD-10", "OD-15", "OD-16"}
    assert all(od["current_status"] == "Open" for od in res.json())
    assert all(od["is_blocking"] for od in res.json())


async def test_only_platform_owner_can_propose(client, authed_requester, reviewer_identity):
    for headers in (authed_requester, reviewer_identity["headers"]):
        res = await client.post(
            "/api/organizational-decisions/OD-10/propose",
            headers=headers,
            json={"value": {"layer1_completeness_threshold": 0.3}, "rationale": "Trying as the wrong role."},
        )
        assert res.status_code == 403


async def test_propose_requires_nonempty_value_and_rationale(client, platform_owner_identity):
    headers = platform_owner_identity["headers"]
    missing_rationale = await client.post(
        "/api/organizational-decisions/OD-10/propose", headers=headers, json={"value": {"x": 1}, "rationale": ""}
    )
    assert missing_rationale.status_code == 422

    missing_value = await client.post(
        "/api/organizational-decisions/OD-10/propose", headers=headers, json={"value": {}, "rationale": "A reason."}
    )
    assert missing_value.status_code == 422


async def test_approve_requires_a_pending_proposal(client, platform_owner_identity):
    res = await client.post(
        "/api/organizational-decisions/OD-10/approve",
        headers=platform_owner_identity["headers"],
        json={"rationale": "Nothing was proposed yet."},
    )
    assert res.status_code == 422


async def test_full_propose_approve_activate_cycle_for_od10(client, platform_owner_identity):
    headers = platform_owner_identity["headers"]

    proposed = await client.post(
        "/api/organizational-decisions/OD-10/propose",
        headers=headers,
        json={"value": {"layer1_completeness_threshold": 0.35}, "rationale": "Moderate threshold for v1."},
    )
    assert proposed.status_code == 200, proposed.text
    assert proposed.json()["action"] == "Proposed"

    od = await client.get("/api/organizational-decisions/OD-10", headers=headers)
    assert od.json()["current_status"] == "Proposed"

    approved = await client.post(
        "/api/organizational-decisions/OD-10/approve",
        headers=headers,
        json={"rationale": "GRC owner concurs with 0.35."},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["value"] == {"layer1_completeness_threshold": 0.35}

    od2 = await client.get("/api/organizational-decisions/OD-10", headers=headers)
    assert od2.json()["current_status"] == "Approved"

    activated = await client.post("/api/organizational-decisions/OD-10/activate", headers=headers)
    assert activated.status_code == 200, activated.text
    assert activated.json()["action"] == "Activated"
    policy_version = activated.json()["activated_policy_config_version"]
    assert policy_version is not None

    policy = await client.get("/api/admin/policy-config/current", headers=headers)
    assert policy.json()["layer1_completeness_threshold"] == 0.35
    assert policy.json()["version"] == policy_version

    history = await client.get("/api/organizational-decisions/OD-10/history", headers=headers)
    actions = [h["action"] for h in history.json()]
    assert actions == ["Proposed", "Approved", "Activated"]


async def test_cannot_activate_non_engine_od(client, platform_owner_identity):
    """OD-01/OD-06/OD-07 have no PolicyConfig field -- activation is
    refused even if somehow Approved, rather than silently no-op'ing.
    """
    headers = platform_owner_identity["headers"]
    await client.post(
        "/api/organizational-decisions/OD-01/propose",
        headers=headers,
        json={"value": {"tier_model": "single_tier"}, "rationale": "Keep the placeholder model for now."},
    )
    await client.post(
        "/api/organizational-decisions/OD-01/approve", headers=headers, json={"rationale": "Confirmed by leadership."}
    )
    res = await client.post("/api/organizational-decisions/OD-01/activate", headers=headers)
    assert res.status_code == 422
    assert "cannot be activated" in res.json()["detail"]


async def test_cannot_activate_before_approval(client, platform_owner_identity):
    headers = platform_owner_identity["headers"]
    await client.post(
        "/api/organizational-decisions/OD-15/propose",
        headers=headers,
        json={"value": {"weights": {"f1_pending_review_discount": 0.5, "overall_multiplier": 1.0}}, "rationale": "Draft weights."},
    )
    res = await client.post("/api/organizational-decisions/OD-15/activate", headers=headers)
    assert res.status_code == 422
    assert "must be Approved" in res.json()["detail"]


async def test_rejected_decision_can_be_revised_and_reproposed(client, platform_owner_identity):
    headers = platform_owner_identity["headers"]
    await client.post(
        "/api/organizational-decisions/OD-16/propose",
        headers=headers,
        json={"value": {"thresholds": {"low_max": 10, "medium_max": 20}}, "rationale": "Very conservative first draft."},
    )
    rejected = await client.post(
        "/api/organizational-decisions/OD-16/reject", headers=headers, json={"rationale": "Too conservative, revise."}
    )
    assert rejected.status_code == 200

    revised = await client.post(
        "/api/organizational-decisions/OD-16/revise",
        headers=headers,
        json={"value": {"thresholds": {"low_max": 33, "medium_max": 66}}, "rationale": "Revised to even thirds."},
    )
    assert revised.status_code == 200
    assert revised.json()["action"] == "Revised"

    od = await client.get("/api/organizational-decisions/OD-16", headers=headers)
    assert od.json()["current_status"] == "Proposed"


async def test_engine_stays_fail_closed_until_od15_and_od16_both_activated(
    client, authed_requester, reviewer_identity, environment_owner_identity, platform_owner_identity, answered_questionnaire
):
    """The registry's own activation gate, end to end: approving and
    activating OD-10 alone is not enough -- the engine still refuses
    (OD-15/OD-16 still NULL) until all three are activated.
    """
    headers = platform_owner_identity["headers"]
    poc_request_id = answered_questionnaire[0]["poc_request_id"]

    await client.post(
        "/api/organizational-decisions/OD-10/propose",
        headers=headers,
        json={"value": {"layer1_completeness_threshold": 0.5}, "rationale": "Moderate."},
    )
    await client.post("/api/organizational-decisions/OD-10/approve", headers=headers, json={"rationale": "ok"})
    await client.post("/api/organizational-decisions/OD-10/activate", headers=headers)

    for dim in ["Isolation", "AccessControl", "TestData", "ConfigBaseline", "Logging", "BackupRollback", "Decommissioning"]:
        await client.put(
            f"/api/poc-requests/{poc_request_id}/environment-readiness/{dim}",
            headers=environment_owner_identity["headers"],
            json={"status": "Attested", "attestation_text": "ok", "supporting_evidence_ids": []},
        )

    rec = await client.post(f"/api/poc-requests/{poc_request_id}/recommendation/recompute", headers=authed_requester)
    assert rec.status_code == 503
    detail = rec.json()["detail"]
    assert any("OD-15" in m for m in detail["missing_configuration"])
    assert any("OD-16" in m for m in detail["missing_configuration"])

    # Now activate OD-15 and OD-16 too.
    for od_id, value in [
        ("OD-15", {"weights": {"f1_pending_review_discount": 0.5, "overall_multiplier": 1.0}}),
        ("OD-16", {"thresholds": {"low_max": 33, "medium_max": 66}}),
    ]:
        await client.post(f"/api/organizational-decisions/{od_id}/propose", headers=headers, json={"value": value, "rationale": "Final."})
        await client.post(f"/api/organizational-decisions/{od_id}/approve", headers=headers, json={"rationale": "ok"})
        await client.post(f"/api/organizational-decisions/{od_id}/activate", headers=headers)

    rec2 = await client.post(f"/api/poc-requests/{poc_request_id}/recommendation/recompute", headers=authed_requester)
    assert rec2.status_code == 200, rec2.text
    assert rec2.json()["outcome"] in ("GO", "NO-GO", "INSUFFICIENT_INFORMATION")
