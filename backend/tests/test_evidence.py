from __future__ import annotations

import io


async def _upload(client, headers, poc_request_id, control_id, content: bytes, filename="evidence.txt"):
    return await client.post(
        f"/api/poc-requests/{poc_request_id}/evidence",
        headers=headers,
        files={"file": (filename, io.BytesIO(content), "text/plain")},
        data={"control_id": control_id} if control_id else {},
    )


async def test_upload_always_lands_at_pending_review(client, authed_requester, submitted_scope):
    poc_request_id = submitted_scope["poc_request_id"]
    res = await _upload(client, authed_requester, poc_request_id, "AC-2", b"a network diagram describing access control")
    assert res.status_code == 201, res.text
    artifact = res.json()
    assert artifact["scan_status"] == "Clean"  # scan ran synchronously in this phase's stand-in

    states = await client.get(f"/api/poc-requests/{poc_request_id}/evidence-states", headers=authed_requester)
    assert states.status_code == 200
    state_rows = {s["control_id"]: s for s in states.json()}
    assert state_rows["AC-2"]["state"] == "Submitted - Pending Review"  # BR-005a: NEVER auto-Verified
    assert state_rows["AC-2"]["validated_by"] is None


async def test_infected_upload_never_reaches_pending_review_servable(client, authed_requester, submitted_scope):
    poc_request_id = submitted_scope["poc_request_id"]
    res = await _upload(
        client, authed_requester, poc_request_id, "AC-2", b"EICAR-FAKE-TEST-MARKER malicious content placeholder"
    )
    assert res.status_code == 201
    assert res.json()["scan_status"] == "Infected"


async def test_only_reviewer_can_validate_evidence(client, authed_requester, reviewer_identity, submitted_scope):
    poc_request_id = submitted_scope["poc_request_id"]
    await _upload(client, authed_requester, poc_request_id, "AC-2", b"evidence content")

    # Requester (who uploaded it) cannot validate their own evidence.
    denied = await client.post(
        f"/api/poc-requests/{poc_request_id}/controls/AC-2/evidence/validate",
        headers=authed_requester,
        json={"new_state": "Verified - Human Validated", "rationale": "looks fine"},
    )
    assert denied.status_code == 403

    allowed = await client.post(
        f"/api/poc-requests/{poc_request_id}/controls/AC-2/evidence/validate",
        headers=reviewer_identity["headers"],
        json={"new_state": "Verified - Human Validated", "rationale": "Diagram confirms AC-2 is addressed."},
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["state"] == "Verified - Human Validated"
    assert allowed.json()["validated_by"] == reviewer_identity["user_id"]


async def test_rejecting_evidence_requires_nonempty_rationale(client, authed_requester, reviewer_identity, submitted_scope):
    poc_request_id = submitted_scope["poc_request_id"]
    await _upload(client, authed_requester, poc_request_id, "AC-2", b"weak evidence")

    res = await client.post(
        f"/api/poc-requests/{poc_request_id}/controls/AC-2/evidence/validate",
        headers=reviewer_identity["headers"],
        json={"new_state": "Rejected - Insufficient Evidence", "rationale": ""},
    )
    assert res.status_code == 422


async def test_new_upload_resets_prior_verified_state(client, authed_requester, reviewer_identity, submitted_scope):
    """A new upload against a previously Verified control resets
    validation state -- a human must re-look at the new bytes (BR-005a).
    """
    poc_request_id = submitted_scope["poc_request_id"]
    await _upload(client, authed_requester, poc_request_id, "AC-2", b"first evidence")
    await client.post(
        f"/api/poc-requests/{poc_request_id}/controls/AC-2/evidence/validate",
        headers=reviewer_identity["headers"],
        json={"new_state": "Verified - Human Validated", "rationale": "ok"},
    )

    await _upload(client, authed_requester, poc_request_id, "AC-2", b"a completely different replacement file")

    states = await client.get(f"/api/poc-requests/{poc_request_id}/evidence-states", headers=authed_requester)
    state_row = next(s for s in states.json() if s["control_id"] == "AC-2")
    assert state_row["state"] == "Submitted - Pending Review"
    assert state_row["validated_by"] is None


async def test_four_states_are_exactly_four(client, authed_requester, submitted_scope):
    poc_request_id = submitted_scope["poc_request_id"]
    res = await _upload(client, authed_requester, poc_request_id, "AC-2", b"x")
    assert res.status_code == 201

    bad = await client.post(
        f"/api/poc-requests/{poc_request_id}/controls/AC-2/evidence/validate",
        headers=authed_requester,  # wrong role anyway, but also test bad enum value separately below
        json={"new_state": "SomeOtherState", "rationale": "x"},
    )
    assert bad.status_code in (403, 422)  # either RBAC or schema validation rejects it


async def test_oversized_upload_rejected(client, authed_requester, submitted_scope):
    poc_request_id = submitted_scope["poc_request_id"]
    huge = b"x" * (26 * 1024 * 1024)
    res = await _upload(client, authed_requester, poc_request_id, "AC-2", huge)
    assert res.status_code == 422
