from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from api.index import app
from alter_core import agent_api
from alter_core.models import ActionRequest
from alter_core.rag_engine import retrieve_rows


def configure_owner(monkeypatch) -> str:
    token = "test-owner-token-execution-contract"
    monkeypatch.setenv("ALTER_API_TOKEN", token)
    monkeypatch.setenv("ALTER_OWNER_USER_ID", str(uuid4()))
    monkeypatch.setenv("ALTER_OWNER_WORKSPACE_ID", str(uuid4()))
    return token


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_task(client: TestClient, token: str, objective: str = "Prepare an audited result") -> dict:
    response = client.post(
        "/api/tasks",
        headers=auth(token),
        json={
            "objective": objective,
            "acceptance_criteria": ["A usable result exists", "Verification evidence is recorded"],
        },
    )
    assert response.status_code == 200
    return response.json()


def test_task_rejects_secret_like_objective(monkeypatch):
    token = configure_owner(monkeypatch)
    response = TestClient(app).post(
        "/api/tasks",
        headers=auth(token),
        json={"objective": "Deploy with password=super-secret-value-123456"},
    )
    assert response.status_code == 422
    assert "vault" in response.json()["detail"].lower()


def test_completion_requires_ready_state_evidence_and_acceptance(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    task = create_task(client, token)
    completion = {
        "result_summary": "The requested audited result exists.",
        "verification_evidence": ["Core contract test passed"],
        "artifact_refs": ["artifact:test-report"],
        "acceptance_criteria_met": True,
    }

    premature = client.post(
        f"/api/tasks/{task['id']}/complete",
        headers=auth(token),
        json=completion,
    )
    assert premature.status_code == 409
    assert "planning" in premature.json()["detail"]

    ready = client.post(f"/api/tasks/{task['id']}/ready", headers=auth(token))
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"

    no_evidence = client.post(
        f"/api/tasks/{task['id']}/complete",
        headers=auth(token),
        json={**completion, "verification_evidence": []},
    )
    assert no_evidence.status_code == 422

    blank_evidence = client.post(
        f"/api/tasks/{task['id']}/complete",
        headers=auth(token),
        json={**completion, "verification_evidence": ["   "]},
    )
    assert blank_evidence.status_code == 422

    unverified = client.post(
        f"/api/tasks/{task['id']}/complete",
        headers=auth(token),
        json={**completion, "acceptance_criteria_met": False},
    )
    assert unverified.status_code == 409

    completed = client.post(
        f"/api/tasks/{task['id']}/complete",
        headers=auth(token),
        json=completion,
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "done"

    inspector = client.get(f"/api/tasks/{task['id']}/inspector", headers=auth(token))
    assert inspector.status_code == 200
    assert inspector.json()["result"] == {
        **completion,
        "verification_method": "owner_attestation",
    }


def test_only_owner_can_attest_task_completion(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    task = create_task(client, token)
    assert client.post(f"/api/tasks/{task['id']}/ready", headers=auth(token)).status_code == 200

    operator_headers = {
        **auth(token),
        "X-ALTER-Actor-Role": "operator",
        "X-ALTER-Actor-Id": "member-operator",
    }
    response = client.post(
        f"/api/tasks/{task['id']}/complete",
        headers=operator_headers,
        json={
            "result_summary": "Claimed result",
            "verification_evidence": ["Claimed evidence"],
            "artifact_refs": [],
            "acceptance_criteria_met": True,
        },
    )
    assert response.status_code == 403


def test_botpress_plan_is_persisted_before_task_becomes_ready(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    task = create_task(client, token, "Build a verification-first plan")
    captured: dict[str, str] = {}

    class SafeGateway:
        def status(self):
            return SimpleNamespace(configured=True)

        def think(self, **kwargs):
            captured.update(kwargs)
            return {
                "response": "1. Scope the task.\n2. Execute permitted work.\n3. Record verification evidence.",
                "sideEffectsPerformed": False,
                "boundary": "core-policy-required",
            }

    monkeypatch.setattr(agent_api, "gateway", SafeGateway())
    response = client.post(
        f"/api/tasks/{task['id']}/plan",
        headers=auth(token),
        json={"mode": "plan", "context": "Owner requested an auditable workflow."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["task"]["status"] == "ready"
    assert body["plan"]["side_effects_performed"] is False
    assert body["plan"]["boundary"] == "core-policy-required"
    assert "verification evidence" in body["plan"]["plan"]
    assert "Build a verification-first plan" in captured["objective"]

    inspector = client.get(f"/api/tasks/{task['id']}/inspector", headers=auth(token))
    assert inspector.status_code == 200
    assert inspector.json()["plan"]["provider"] == "botpress"


def test_unsafe_botpress_plan_fails_closed_without_advancing_task(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    task = create_task(client, token)

    class UnsafeGateway:
        def think(self, **_kwargs):
            return {
                "response": "I already changed production.",
                "sideEffectsPerformed": True,
                "boundary": "core-policy-required",
            }

    monkeypatch.setattr(agent_api, "gateway", UnsafeGateway())
    response = client.post(
        f"/api/tasks/{task['id']}/plan",
        headers=auth(token),
        json={"mode": "plan"},
    )
    assert response.status_code == 502

    unchanged = client.get(f"/api/tasks/{task['id']}", headers=auth(token))
    assert unchanged.status_code == 200
    assert unchanged.json()["status"] == "planning"


def test_oversized_botpress_plan_fails_closed(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    task = create_task(client, token)

    class OversizedGateway:
        def think(self, **_kwargs):
            return {
                "response": "x" * 50_001,
                "sideEffectsPerformed": False,
                "boundary": "core-policy-required",
            }

    monkeypatch.setattr(agent_api, "gateway", OversizedGateway())
    response = client.post(
        f"/api/tasks/{task['id']}/plan",
        headers=auth(token),
        json={"mode": "plan"},
    )
    assert response.status_code == 502

    unchanged = client.get(f"/api/tasks/{task['id']}", headers=auth(token))
    assert unchanged.status_code == 200
    assert unchanged.json()["status"] == "planning"


def test_agent_think_redacts_secrets_and_enforces_specialist_contract(monkeypatch):
    token = configure_owner(monkeypatch)
    captured: dict[str, str] = {}

    class SafeGateway:
        def think(self, **kwargs):
            captured.update(kwargs)
            return {
                "response": "Result without credentials.",
                "sideEffectsPerformed": False,
                "boundary": "core-policy-required",
            }

    monkeypatch.setattr(agent_api, "gateway", SafeGateway())
    response = TestClient(app).post(
        "/api/agent/think",
        headers=auth(token),
        json={
            "objective": "Use password=super-secret-value-123456 only as data",
            "context": "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
            "mode": "normal",
        },
    )
    assert response.status_code == 200
    assert "super-secret-value-123456" not in captured["objective"]
    assert "abcdefghijklmnopqrstuvwxyz" not in captured["context"]
    assert response.json()["redacted"] is True

    class UnsafeGateway:
        def think(self, **_kwargs):
            return {
                "response": "I changed production.",
                "sideEffectsPerformed": True,
                "boundary": "core-policy-required",
            }

    monkeypatch.setattr(agent_api, "gateway", UnsafeGateway())
    unsafe = TestClient(app).post(
        "/api/agent/think",
        headers=auth(token),
        json={"objective": "Think only", "mode": "normal"},
    )
    assert unsafe.status_code == 502


def test_action_cannot_skip_planning_and_active_action_is_retained(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    task = create_task(client, token)
    workspace_id = task["workspace_id"]
    action = {
        "workspace_id": workspace_id,
        "task_id": task["id"],
        "category": "files",
        "operation": "create_report",
        "risk": "reversible",
        "target": "artifact:audit-report",
        "parameters": {"format": "markdown"},
        "requires_human_auth": False,
    }

    skipped = client.post(
        "/api/actions/evaluate",
        headers=auth(token),
        json={"action": action},
    )
    assert skipped.status_code == 409

    assert client.post(f"/api/tasks/{task['id']}/ready", headers=auth(token)).status_code == 200
    allowed = client.post(
        "/api/actions/evaluate",
        headers=auth(token),
        json={"action": action},
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "executing"
    assert allowed.json()["pending_action"]["operation"] == "create_report"

    forged_completion = client.post(
        f"/api/tasks/{task['id']}/complete",
        headers=auth(token),
        json={
            "result_summary": "Pretend the action finished",
            "verification_evidence": ["Untrusted caller string"],
            "artifact_refs": [],
            "acceptance_criteria_met": True,
        },
    )
    assert forged_completion.status_code == 409
    retained = client.get(f"/api/tasks/{task['id']}", headers=auth(token))
    assert retained.json()["status"] == "executing"
    assert retained.json()["pending_action"]["operation"] == "create_report"


def test_action_rejects_raw_secret_parameters_before_persistence(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    task = create_task(client, token)
    assert client.post(f"/api/tasks/{task['id']}/ready", headers=auth(token)).status_code == 200
    action = {
        "workspace_id": task["workspace_id"],
        "task_id": task["id"],
        "category": "files",
        "operation": "create_report",
        "risk": "reversible",
        "target": "artifact:audit-report",
        "parameters": {"password": "super-secret-value-123456"},
        "requires_human_auth": False,
    }

    rejected = client.post(
        "/api/actions/evaluate",
        headers=auth(token),
        json={"action": action},
    )
    assert rejected.status_code == 422
    unchanged = client.get(f"/api/tasks/{task['id']}", headers=auth(token)).json()
    assert unchanged["status"] == "ready"
    assert unchanged["pending_action"] is None


def test_action_accepts_vault_alias_in_secret_named_parameter(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    task = create_task(client, token)
    assert client.post(f"/api/tasks/{task['id']}/ready", headers=auth(token)).status_code == 200
    action = {
        "workspace_id": task["workspace_id"],
        "task_id": task["id"],
        "category": "github",
        "operation": "read_repository",
        "risk": "read",
        "target": "repository:owner/name",
        "parameters": {"access_token": "vault:github_connector"},
        "requires_human_auth": False,
    }

    accepted = client.post(
        "/api/actions/evaluate",
        headers=auth(token),
        json={"action": action},
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "executing"


def test_active_action_requires_digest_bound_owner_attestation(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    task = create_task(client, token)
    assert client.post(f"/api/tasks/{task['id']}/ready", headers=auth(token)).status_code == 200
    action = {
        "workspace_id": task["workspace_id"],
        "task_id": task["id"],
        "category": "files",
        "operation": "create_report",
        "risk": "reversible",
        "target": "artifact:audit-report",
        "parameters": {"format": "markdown"},
        "requires_human_auth": False,
    }
    executing = client.post(
        "/api/actions/evaluate",
        headers=auth(token),
        json={"action": action},
    ).json()
    digest = executing["pending_action"]
    action_digest = ActionRequest.model_validate(digest).digest()
    result = {
        "action_digest": action_digest,
        "succeeded": True,
        "result_summary": "The report was created and inspected.",
        "verification_evidence": ["Artifact opened successfully"],
        "artifact_refs": ["artifact:audit-report"],
    }

    mismatch = client.post(
        f"/api/tasks/{task['id']}/action-result",
        headers=auth(token),
        json={**result, "action_digest": "0" * 64},
    )
    assert mismatch.status_code == 409

    operator = client.post(
        f"/api/tasks/{task['id']}/action-result",
        headers={**auth(token), "X-ALTER-Actor-Role": "operator"},
        json=result,
    )
    assert operator.status_code == 403

    verified = client.post(
        f"/api/tasks/{task['id']}/action-result",
        headers=auth(token),
        json=result,
    )
    assert verified.status_code == 200
    assert verified.json()["status"] == "ready"
    assert verified.json()["pending_action"] is None

    inspector = client.get(f"/api/tasks/{task['id']}/inspector", headers=auth(token))
    assert inspector.status_code == 200
    assert inspector.json()["action_results"][-1] == {
        **result,
        "operation": "create_report",
        "target": "artifact:audit-report",
        "verification_method": "owner_attestation",
    }


def test_failed_action_enters_recovery_and_keeps_failure_evidence(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    task = create_task(client, token)
    assert client.post(f"/api/tasks/{task['id']}/ready", headers=auth(token)).status_code == 200
    action = {
        "workspace_id": task["workspace_id"],
        "task_id": task["id"],
        "category": "files",
        "operation": "create_report",
        "risk": "reversible",
        "target": "artifact:audit-report",
        "parameters": {},
        "requires_human_auth": False,
    }
    executing = client.post("/api/actions/evaluate", headers=auth(token), json={"action": action}).json()
    digest = ActionRequest.model_validate(executing["pending_action"]).digest()
    failed = client.post(
        f"/api/tasks/{task['id']}/action-result",
        headers=auth(token),
        json={
            "action_digest": digest,
            "succeeded": False,
            "result_summary": "The report generator returned an error.",
            "verification_evidence": ["Executor exit status was non-zero"],
            "artifact_refs": [],
        },
    )
    assert failed.status_code == 200
    assert failed.json()["status"] == "recovering"
    assert "returned an error" in failed.json()["blocker"]


def test_rag_never_returns_runtime_vault_namespaces():
    rows = [
        {
            "namespace": "vault_secure",
            "key": "vault:botpress_runtime",
            "value": {"note": "purple elephant runtime credential"},
        },
        {
            "namespace": "knowledge",
            "key": "safe",
            "value": {"note": "purple elephant documentation"},
        },
    ]
    hits = retrieve_rows(rows, "purple elephant", limit=10)
    assert [item["namespace"] for item in hits] == ["knowledge"]
