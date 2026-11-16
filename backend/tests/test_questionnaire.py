from __future__ import annotations

from app.api.deps import model_client_dependency
from app.main import app


async def test_generate_questionnaire_without_configured_ai_returns_503(client, authed_requester, submitted_scope):
    """No AI provider configured -> explicit refusal, never a fabricated
    question set (same philosophy as the Decision Engine's OD-gated
    refusal in architecture/TASD-v1.0.md section 14.7).
    """
    res = await client.post(
        f"/api/poc-requests/{submitted_scope['poc_request_id']}/questionnaire/generate",
        headers=authed_requester,
    )
    assert res.status_code == 503


async def test_generate_questionnaire_happy_path(client, authed_requester, submitted_scope, fake_ai_client):
    app.dependency_overrides[model_client_dependency] = lambda: fake_ai_client
    try:
        res = await client.post(
            f"/api/poc-requests/{submitted_scope['poc_request_id']}/questionnaire/generate",
            headers=authed_requester,
        )
    finally:
        del app.dependency_overrides[model_client_dependency]

    assert res.status_code == 200, res.text
    body = res.json()
    questions = body["questions"]
    # BR-008: identified gaps/assumptions are surfaced alongside the questions.
    assert body["identified_gaps"] == ["No mention of rollback plan."]
    assert body["identified_assumptions"] == ["Assuming a non-production test environment."]
    # BR-002: exactly 11-15 questions survive validation.
    assert 11 <= len(questions) <= 15
    assert len(questions) == 11  # the fixture's scripted response has exactly 11

    mandatory = [q for q in questions if q["is_mandatory_domain"]]
    conditional = [q for q in questions if not q["is_mandatory_domain"]]
    assert len(mandatory) == 9  # all 9 Mandatory domains covered (BR-003)
    assert all(q["trigger_basis"] is None for q in mandatory)
    assert len(conditional) == 2
    assert all(q["trigger_basis"] for q in conditional)

    # Prompt-injection resistance: requester scope text was passed as
    # labeled DATA, never concatenated into system instructions.
    assert fake_ai_client.last_payload is not None
    assert "AcmeCloud" in fake_ai_client.last_payload.requester_data["project_description"]
    assert "AcmeCloud" not in fake_ai_client.last_payload.system_instructions


async def test_list_questionnaire_after_generation(client, authed_requester, submitted_scope, fake_ai_client):
    app.dependency_overrides[model_client_dependency] = lambda: fake_ai_client
    try:
        await client.post(
            f"/api/poc-requests/{submitted_scope['poc_request_id']}/questionnaire/generate",
            headers=authed_requester,
        )
    finally:
        del app.dependency_overrides[model_client_dependency]

    listed = await client.get(
        f"/api/poc-requests/{submitted_scope['poc_request_id']}/questionnaire", headers=authed_requester
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 11


async def test_submit_answers_persists_with_provenance_and_version(
    client, authed_requester, submitted_scope, fake_ai_client
):
    app.dependency_overrides[model_client_dependency] = lambda: fake_ai_client
    try:
        gen = await client.post(
            f"/api/poc-requests/{submitted_scope['poc_request_id']}/questionnaire/generate",
            headers=authed_requester,
        )
    finally:
        del app.dependency_overrides[model_client_dependency]
    questions = gen.json()["questions"]

    answers_payload = {
        "answers": [{"question_id": q["id"], "answer_text": f"Answer for {q['domain_label']}"} for q in questions]
    }
    res = await client.post(
        f"/api/poc-requests/{submitted_scope['poc_request_id']}/answers",
        headers=authed_requester,
        json=answers_payload,
    )
    assert res.status_code == 201, res.text
    saved = res.json()
    assert len(saved) == len(questions)
    for a in saved:
        # D2 section 6: this table may never hold anything but REQUESTER_FACT.
        assert a["provenance_tag"] == "REQUESTER_FACT"
        assert a["input_version"] == 1
        assert a["usability"] == "Usable"


async def test_answer_for_blank_text_classified_not_usable(client, authed_requester, submitted_scope, fake_ai_client):
    app.dependency_overrides[model_client_dependency] = lambda: fake_ai_client
    try:
        gen = await client.post(
            f"/api/poc-requests/{submitted_scope['poc_request_id']}/questionnaire/generate",
            headers=authed_requester,
        )
    finally:
        del app.dependency_overrides[model_client_dependency]
    question_id = gen.json()["questions"][0]["id"]

    res = await client.post(
        f"/api/poc-requests/{submitted_scope['poc_request_id']}/answers",
        headers=authed_requester,
        json={"answers": [{"question_id": question_id, "answer_text": "   "}]},
    )
    assert res.status_code == 201
    assert res.json()[0]["usability"] == "Blank"


async def test_cannot_answer_question_from_another_poc_request(client, authed_requester, submitted_scope):
    res = await client.post(
        f"/api/poc-requests/{submitted_scope['poc_request_id']}/answers",
        headers=authed_requester,
        json={"answers": [{"question_id": "not-a-real-question-id", "answer_text": "x"}]},
    )
    assert res.status_code == 404
