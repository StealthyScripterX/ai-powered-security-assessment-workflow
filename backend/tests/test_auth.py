from __future__ import annotations

import pytest


async def test_register_and_login(client):
    res = await client.post(
        "/api/auth/register",
        json={"username": "alice", "email": "alice@example.com", "password": "hunter2hunter2", "role": "Requester"},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["username"] == "alice"
    assert body["role"] == "Requester"
    assert "hashed_password" not in body  # never leak the hash

    login = await client.post("/api/auth/login", data={"username": "alice", "password": "hunter2hunter2"})
    assert login.status_code == 200
    assert "access_token" in login.json()


async def test_login_wrong_password_rejected(client):
    await client.post(
        "/api/auth/register",
        json={"username": "bob", "email": "bob@example.com", "password": "correctpassword", "role": "Requester"},
    )
    login = await client.post("/api/auth/login", data={"username": "bob", "password": "wrongpassword"})
    assert login.status_code == 401


async def test_duplicate_username_rejected(client):
    payload = {"username": "carol", "email": "carol@example.com", "password": "password123", "role": "Requester"}
    first = await client.post("/api/auth/register", json=payload)
    assert first.status_code == 201
    second = await client.post("/api/auth/register", json=payload)
    assert second.status_code == 409


async def test_protected_endpoint_requires_token(client):
    res = await client.get("/api/poc-requests")
    assert res.status_code == 401


async def test_role_not_permitted_is_403(client):
    """Server-side RBAC: a SecurityReviewer cannot use the Requester-only
    scope-submission endpoint, even with a valid token -- enforced on the
    server, not merely hidden in a UI (non-negotiable: "Enforce
    authorization on the server, not just the UI.").
    """
    await client.post(
        "/api/auth/register",
        json={
            "username": "dana_reviewer",
            "email": "dana@example.com",
            "password": "password123",
            "role": "SecurityReviewer",
        },
    )
    login = await client.post("/api/auth/login", data={"username": "dana_reviewer", "password": "password123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    res = await client.post(
        "/api/poc-requests",
        headers=headers,
        json={
            "project_description": "x",
            "systems_in_scope": "y",
            "business_justification": "z",
            "intake_form_data": {},
        },
    )
    assert res.status_code == 403
