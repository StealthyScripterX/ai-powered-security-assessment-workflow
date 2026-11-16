from __future__ import annotations


async def test_submit_scope_requires_no_prior_documentation(client, authed_requester):
    """BR-001: the only required fields are free-text scope fields --
    no attachment or prior security documentation field exists at all.
    """
    res = await client.post(
        "/api/poc-requests",
        headers=authed_requester,
        json={
            "project_description": "Testing a new internal tool.",
            "systems_in_scope": "tool.internal",
            "business_justification": "Pre-launch check.",
            "intake_form_data": {},
        },
    )
    assert res.status_code == 201
    body = res.json()
    assert body["version"] == 1
    assert body["project_description"] == "Testing a new internal tool."
    assert body["poc_request_id"]


async def test_scope_creates_poc_request_visible_to_owner_only(client, authed_requester, submitted_scope):
    poc_request_id = submitted_scope["poc_request_id"]

    mine = await client.get(f"/api/poc-requests/{poc_request_id}", headers=authed_requester)
    assert mine.status_code == 200
    assert mine.json()["id"] == poc_request_id
    assert mine.json()["status"] == "InProgress"
    assert mine.json()["current_input_version"] == 1


async def test_scope_not_visible_to_different_requester(client, authed_requester, submitted_scope):
    """T-04 (architecture/TASD-v1.0.md section 19): object-level
    authorization -- a different Requester cannot read someone else's
    POC request even with a valid session.
    """
    other_username = "other_requester_xyz"
    await client.post(
        "/api/auth/register",
        json={
            "username": other_username,
            "email": "other@example.com",
            "password": "password123456",
            "role": "Requester",
        },
    )
    login = await client.post("/api/auth/login", data={"username": other_username, "password": "password123456"})
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    res = await client.get(f"/api/poc-requests/{submitted_scope['poc_request_id']}", headers=other_headers)
    assert res.status_code == 403


async def test_missing_required_field_rejected(client, authed_requester):
    res = await client.post(
        "/api/poc-requests",
        headers=authed_requester,
        json={"project_description": "", "systems_in_scope": "x", "business_justification": "y"},
    )
    assert res.status_code == 422
