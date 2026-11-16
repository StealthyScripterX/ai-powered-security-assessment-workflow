from __future__ import annotations

import os
import tempfile
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-do-not-use-in-production")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

# Test isolation from the developer's real backend/.env: pydantic-settings
# falls through to reading .env for any field not already present in the
# real process environment (app/config.py's `env_file=".env"`), so a
# real ANTHROPIC_API_KEY/GEMINI_API_KEY sitting in that file would
# otherwise leak into test runs and make them depend on, and attempt
# live network calls against, whatever the developer has configured
# locally -- exactly what happened once, caught by
# test_generate_questionnaire_without_configured_ai_returns_503 making a
# REAL Gemini API call instead of exercising the "unconfigured" path
# (see IMPLEMENTATION-NOTES.md). Force all three AI-provider fields to
# the unconfigured state here; tests that need a configured provider use
# FakeModelClient via an explicit dependency override instead, never the
# real .env file.
os.environ["AI_PROVIDER"] = "anthropic"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""

# Test runs must never write evidence files into the real working
# directory -- isolate to a session-scoped temp directory.
_TEST_VAR_DIR = tempfile.mkdtemp(prefix="poc_workflow_test_var_")
os.environ.setdefault("QUARANTINE_DIR", os.path.join(_TEST_VAR_DIR, "quarantine"))
os.environ.setdefault("EVIDENCE_DIR", os.path.join(_TEST_VAR_DIR, "evidence"))

from app.api.deps import model_client_dependency  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.ai.client import FakeModelClient  # noqa: E402
from app.services.catalog_seed import seed_catalog_if_empty  # noqa: E402
from app.services.od_registry_seed import seed_od_registry_if_empty  # noqa: E402


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(
        f"sqlite+aiosqlite:///file:{uuid.uuid4().hex}?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # The app's own lifespan (which seeds the catalog) does not run under
    # a raw ASGITransport test client, so seed explicitly here -- every
    # test gets the real D3-Catalog rows mapping/engine tests need.
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        await seed_catalog_if_empty(session)
        await seed_od_registry_if_empty(session)

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_engine):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


def default_questionnaire_payload() -> dict:
    """A scripted, schema-valid AI response covering all 9 Mandatory
    domains plus 2 triggered Conditional ones -- 11 questions exactly.
    """
    from app.services.ai.questionnaire import CONDITIONAL_DOMAINS, MANDATORY_DOMAINS

    questions = [
        {
            "domain_label": domain,
            "is_mandatory_domain": True,
            "trigger_basis": None,
            "question_text": f"Please describe your approach to {domain}.",
        }
        for domain in MANDATORY_DOMAINS
    ]
    questions.append(
        {
            "domain_label": CONDITIONAL_DOMAINS[0],
            "is_mandatory_domain": False,
            "trigger_basis": "scope mentions 'AcmeCloud' vendor",
            "question_text": "Which third-party vendors will have access?",
        }
    )
    questions.append(
        {
            "domain_label": CONDITIONAL_DOMAINS[1],
            "is_mandatory_domain": False,
            "trigger_basis": "scope mentions 'customer data'",
            "question_text": "What customer personal data will be processed?",
        }
    )
    return {
        "identified_gaps": ["No mention of rollback plan."],
        "identified_assumptions": ["Assuming a non-production test environment."],
        "questions": questions,
    }


@pytest.fixture
def fake_ai_client():
    return FakeModelClient(scripted_response=default_questionnaire_payload())


async def _register_and_login(client, role: str) -> dict:
    username = f"{role.lower()}_{uuid.uuid4().hex[:8]}"
    password = "correct-horse-battery-staple"
    res = await client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": password, "role": role},
    )
    assert res.status_code == 201, res.text
    user_id = res.json()["id"]
    login = await client.post("/api/auth/login", data={"username": username, "password": password})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {"headers": {"Authorization": f"Bearer {token}"}, "user_id": user_id, "username": username}


@pytest_asyncio.fixture
async def authed_requester(client):
    """Registers + logs in a fresh Requester, returns just the headers
    dict (kept backward-compatible with the Phase 1 tests).
    """
    identity = await _register_and_login(client, "Requester")
    return identity["headers"]


@pytest_asyncio.fixture
async def requester_identity(client):
    return await _register_and_login(client, "Requester")


@pytest_asyncio.fixture
async def reviewer_identity(client):
    return await _register_and_login(client, "SecurityReviewer")


@pytest_asyncio.fixture
async def environment_owner_identity(client):
    return await _register_and_login(client, "EnvironmentOwner")


@pytest_asyncio.fixture
async def approver_identity(client):
    return await _register_and_login(client, "FinalApprover")


@pytest_asyncio.fixture
async def platform_owner_identity(client):
    return await _register_and_login(client, "PlatformOwner")


def fake_mapping_client(mappings: list[dict]) -> FakeModelClient:
    """`mappings` is the scripted {"mappings": [...]} response every
    generate_mappings call will receive (same response for every answer
    in a test -- fine for exercising the persistence/validation path).
    """
    return FakeModelClient(scripted_response={"mappings": mappings})


class DynamicMappingFakeClient:
    """Mapping generation fans out one AI call per answer, each with a
    DIFFERENT closed candidate-control set (one per question's domain).
    A single scripted response can't satisfy every call, so this reads
    the actual candidate list out of each call's own prompt and proposes
    the first candidate it was given -- letting tests assert on real,
    per-domain-valid mappings without hardcoding which control belongs
    to which domain.
    """

    def __init__(self, confidence: str = "High", invent_control_id: str | None = None):
        self.confidence = confidence
        self.invent_control_id = invent_control_id  # for testing rejection of invented IDs
        self.calls: list = []

    async def complete_json(self, payload, *, max_tokens: int = 4096) -> dict:
        self.calls.append(payload)
        if self.invent_control_id:
            return {
                "mappings": [
                    {"control_id": self.invent_control_id, "confidence": self.confidence, "rationale": "x"}
                ]
            }
        import re

        match = re.search(r"- (\S+):", payload.task_instructions)
        if not match:
            return {"mappings": []}
        return {
            "mappings": [
                {"control_id": match.group(1), "confidence": self.confidence, "rationale": "Relates to this control."}
            ]
        }


@pytest_asyncio.fixture
async def submitted_scope(client, authed_requester):
    res = await client.post(
        "/api/poc-requests",
        headers=authed_requester,
        json={
            "project_description": "A pilot penetration test of our new customer portal, "
            "hosted with vendor AcmeCloud. The portal processes customer data.",
            "systems_in_scope": "customer-portal-staging.internal",
            "business_justification": "Validate security posture before GA launch.",
            "intake_form_data": {},
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


@pytest_asyncio.fixture
async def answered_questionnaire(client, authed_requester, submitted_scope, fake_ai_client):
    """Drives scope -> questions -> answers, returning the list of
    answered questions. Used by mapping/evidence/environment/engine/
    approval tests that need a POC request already past the intake
    stage.
    """
    app.dependency_overrides[model_client_dependency] = lambda: fake_ai_client
    try:
        gen = await client.post(
            f"/api/poc-requests/{submitted_scope['poc_request_id']}/questionnaire/generate",
            headers=authed_requester,
        )
    finally:
        del app.dependency_overrides[model_client_dependency]
    assert gen.status_code == 200, gen.text
    questions = gen.json()["questions"]

    answers_payload = {
        "answers": [{"question_id": q["id"], "answer_text": f"Detailed answer for {q['domain_label']}."} for q in questions]
    }
    res = await client.post(
        f"/api/poc-requests/{submitted_scope['poc_request_id']}/answers",
        headers=authed_requester,
        json=answers_payload,
    )
    assert res.status_code == 201, res.text
    return questions
