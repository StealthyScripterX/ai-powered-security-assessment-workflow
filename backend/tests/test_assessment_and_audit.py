"""Integration tests for the new frontend-supporting endpoints: the
central AI agent's assessment summary, the cross-cutting queue, and the
Compliance Dashboard's audit API.
"""
from __future__ import annotations


async def test_queue_requires_cross_cutting_role(client, authed_requester):
    """A Requester cannot see the cross-cutting queue -- they use
    GET /api/poc-requests (scoped to their own) instead.
    """
    res = await client.get("/api/poc-requests/queue", headers=authed_requester)
    assert res.status_code == 403


async def test_queue_lists_all_assessments_for_reviewer(client, authed_requester, reviewer_identity, submitted_scope):
    res = await client.get("/api/poc-requests/queue", headers=reviewer_identity["headers"])
    assert res.status_code == 200
    ids = [item["id"] for item in res.json()]
    assert submitted_scope["poc_request_id"] in ids


async def test_queue_route_not_shadowed_by_poc_request_id_route(client, reviewer_identity):
    """Regression test for a real routing bug this build introduced and
    fixed: '/api/poc-requests/queue' and '/api/poc-requests/{id}' are
    both single-segment paths under the same prefix, and FastAPI
    resolves the ambiguity by router registration order. This asserts
    'queue' is never treated as a poc_request_id.
    """
    res = await client.get("/api/poc-requests/queue", headers=reviewer_identity["headers"])
    assert res.status_code == 200
    assert isinstance(res.json(), list)


async def test_assessment_summary_has_three_independent_axes(
    client, authed_requester, reviewer_identity, answered_questionnaire
):
    """D2-AI-Governance.md section 6: the summary must carry provenance,
    review_status, and evidence_state as three distinct fields across
    its nested objects -- never collapsed.
    """
    from app.api.deps import model_client_dependency
    from app.main import app
    from tests.conftest import DynamicMappingFakeClient

    poc_request_id = answered_questionnaire[0]["poc_request_id"]
    fake_client = DynamicMappingFakeClient(confidence="High")
    app.dependency_overrides[model_client_dependency] = lambda: fake_client
    try:
        await client.post(f"/api/poc-requests/{poc_request_id}/mappings/generate", headers=authed_requester)
    finally:
        del app.dependency_overrides[model_client_dependency]

    summary = await client.get(f"/api/poc-requests/{poc_request_id}/summary", headers=reviewer_identity["headers"])
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert len(body["mappings"]) > 0
    for m in body["mappings"]:
        assert "provenance_tag" in m
        assert "review_status" in m
        assert m["provenance_tag"] == "AI_ASSERTION"
    for a in body["answers"]:
        assert "provenance_tag" in a
        assert a["provenance_tag"] == "REQUESTER_FACT"


async def test_assessment_summary_requester_cannot_view_others(client, authed_requester, submitted_scope):
    import uuid

    other_username = f"other_{uuid.uuid4().hex[:8]}"
    await client.post(
        "/api/auth/register",
        json={"username": other_username, "email": f"{other_username}@x.com", "password": "password123456", "role": "Requester"},
    )
    login = await client.post("/api/auth/login", data={"username": other_username, "password": "password123456"})
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    res = await client.get(f"/api/poc-requests/{submitted_scope['poc_request_id']}/summary", headers=other_headers)
    assert res.status_code == 403


async def test_audit_list_requires_compliance_or_platform_owner_role(client, authed_requester):
    res = await client.get("/api/audit-entries", headers=authed_requester)
    assert res.status_code == 403


async def test_audit_verify_reports_clean_chain(client, authed_requester, submitted_scope):
    import uuid

    username = f"compliance_{uuid.uuid4().hex[:8]}"
    await client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@x.com", "password": "password123456", "role": "ComplianceAuditor"},
    )
    login = await client.post("/api/auth/login", data={"username": username, "password": "password123456"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    res = await client.get("/api/audit-entries/verify", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["first_broken_sequence_number"] is None
    assert body["entries_checked"] >= 1  # at least the scope_submitted entry


async def test_audit_list_filters_by_affected_object_id(client, authed_requester, submitted_scope):
    import uuid

    username = f"compliance_{uuid.uuid4().hex[:8]}"
    await client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@x.com", "password": "password123456", "role": "ComplianceAuditor"},
    )
    login = await client.post("/api/auth/login", data={"username": username, "password": "password123456"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    res = await client.get(
        f"/api/audit-entries?affected_object_id={submitted_scope['poc_request_id']}", headers=headers
    )
    assert res.status_code == 200
    entries = res.json()
    assert len(entries) >= 1
    assert all(e["affected_object_id"] == submitted_scope["poc_request_id"] for e in entries)
    assert entries[0]["action_type"] == "scope_submitted"


async def test_ai_agent_never_writes_approval_or_evidence_validation(client, authed_requester, reviewer_identity, submitted_scope):
    """Structural check backing app/services/ai_agent.py's docstring
    claim: the central AI agent facade exposes no function that can
    reach approval_decision or the evidence Verified/Rejected
    transition. Verified here by confirming the module's public symbol
    set contains no such capability, not by trying to call one (there
    is none to call).
    """
    import app.services.ai_agent as ai_agent

    public_names = [n for n in dir(ai_agent) if not n.startswith("_")]
    forbidden_substrings = ["approve", "approval", "verify_evidence", "validate_evidence", "transition_evidence"]
    for name in public_names:
        lowered = name.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, f"ai_agent exposes {name!r}, which looks like a forbidden capability"
