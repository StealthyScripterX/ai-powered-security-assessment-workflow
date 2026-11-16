from __future__ import annotations

from app.api.deps import model_client_dependency
from app.main import app
from tests.conftest import DynamicMappingFakeClient


async def test_generate_mappings_persists_catalog_constrained_drafts(
    client, authed_requester, answered_questionnaire
):
    poc_request_id = answered_questionnaire[0]["poc_request_id"]
    fake_client = DynamicMappingFakeClient(confidence="High")
    app.dependency_overrides[model_client_dependency] = lambda: fake_client
    try:
        res = await client.post(f"/api/poc-requests/{poc_request_id}/mappings/generate", headers=authed_requester)
    finally:
        del app.dependency_overrides[model_client_dependency]

    assert res.status_code == 200, res.text
    mappings = res.json()
    assert len(mappings) > 0
    for m in mappings:
        assert m["provenance_tag"] == "AI_ASSERTION"  # D2 section 6: AI proposed it
        assert m["review_status"] == "PendingReview"
        assert m["confidence"] == "High"


async def test_invented_control_identifier_rejected(client, authed_requester, answered_questionnaire):
    """Non-negotiable: never invent ISO/NIST control mappings. If the AI
    proposes an identifier outside the candidate set it was given, the
    whole mapping generation call fails rather than persisting it.
    """
    poc_request_id = answered_questionnaire[0]["poc_request_id"]
    fake_client = DynamicMappingFakeClient(invent_control_id="Z.99.99-NOT-REAL")
    app.dependency_overrides[model_client_dependency] = lambda: fake_client
    try:
        res = await client.post(f"/api/poc-requests/{poc_request_id}/mappings/generate", headers=authed_requester)
    finally:
        del app.dependency_overrides[model_client_dependency]
    assert res.status_code == 502
    assert "invented control identifier" in res.json()["detail"]


async def _generate_one_mapping(client, authed_requester, poc_request_id) -> dict:
    fake_client = DynamicMappingFakeClient(confidence="Medium")
    app.dependency_overrides[model_client_dependency] = lambda: fake_client
    try:
        gen = await client.post(f"/api/poc-requests/{poc_request_id}/mappings/generate", headers=authed_requester)
    finally:
        del app.dependency_overrides[model_client_dependency]
    assert gen.status_code == 200, gen.text
    assert len(gen.json()) > 0
    return gen.json()[0]


async def test_reviewer_confirm_creates_new_row_not_edit(
    client, authed_requester, reviewer_identity, answered_questionnaire
):
    poc_request_id = answered_questionnaire[0]["poc_request_id"]
    mapping = await _generate_one_mapping(client, authed_requester, poc_request_id)
    mapping_id = mapping["id"]

    res = await client.post(
        f"/api/poc-requests/{poc_request_id}/mappings/{mapping_id}/review",
        headers=reviewer_identity["headers"],
        json={"action": "Confirm"},
    )
    assert res.status_code == 200, res.text
    confirmed = res.json()
    assert confirmed["id"] != mapping_id  # a NEW row, not an edit
    assert confirmed["supersedes_id"] == mapping_id
    assert confirmed["review_status"] == "Confirmed"
    assert confirmed["provenance_tag"] == "AI_ASSERTION"  # never changes, even after review

    listed = await client.get(f"/api/poc-requests/{poc_request_id}/mappings", headers=reviewer_identity["headers"])
    current_ids = [m["id"] for m in listed.json()]
    assert mapping_id not in current_ids  # superseded row is not in the "current" view
    assert confirmed["id"] in current_ids


async def test_adjust_changes_fields_but_not_provenance(
    client, authed_requester, reviewer_identity, answered_questionnaire
):
    poc_request_id = answered_questionnaire[0]["poc_request_id"]
    mapping = await _generate_one_mapping(client, authed_requester, poc_request_id)

    res = await client.post(
        f"/api/poc-requests/{poc_request_id}/mappings/{mapping['id']}/review",
        headers=reviewer_identity["headers"],
        json={"action": "Adjust", "confidence": "Low", "rationale": "Reviewer judges this weaker than AI stated."},
    )
    assert res.status_code == 200, res.text
    adjusted = res.json()
    assert adjusted["review_status"] == "Adjusted"
    assert adjusted["confidence"] == "Low"
    assert adjusted["provenance_tag"] == "AI_ASSERTION"


async def test_reject_requires_reason(client, authed_requester, reviewer_identity, answered_questionnaire):
    poc_request_id = answered_questionnaire[0]["poc_request_id"]
    mapping = await _generate_one_mapping(client, authed_requester, poc_request_id)

    res = await client.post(
        f"/api/poc-requests/{poc_request_id}/mappings/{mapping['id']}/review",
        headers=reviewer_identity["headers"],
        json={"action": "Reject"},
    )
    assert res.status_code == 422

    res2 = await client.post(
        f"/api/poc-requests/{poc_request_id}/mappings/{mapping['id']}/review",
        headers=reviewer_identity["headers"],
        json={"action": "Reject", "reject_reason": "Does not actually relate to this control."},
    )
    assert res2.status_code == 200
    assert res2.json()["review_status"] == "Rejected"


async def test_requester_cannot_review_mapping(client, authed_requester, answered_questionnaire):
    """Server-side RBAC: only SecurityReviewer may review a mapping."""
    poc_request_id = answered_questionnaire[0]["poc_request_id"]
    mapping = await _generate_one_mapping(client, authed_requester, poc_request_id)

    res = await client.post(
        f"/api/poc-requests/{poc_request_id}/mappings/{mapping['id']}/review",
        headers=authed_requester,
        json={"action": "Confirm"},
    )
    assert res.status_code == 403
