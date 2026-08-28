import os
from types import SimpleNamespace
from uuid import UUID, uuid4

from alter_core import agent_api, conversation_api, productivity_api
from alter_core import api as core_api
from alter_core.auth import Principal
from alter_core.models import ActionRequest
from alter_core.secret_safety import contains_high_confidence_secret
from api.index import app
from fastapi.testclient import TestClient


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


def test_task_accepts_vault_alias_embedded_in_objective(monkeypatch):
    token = configure_owner(monkeypatch)
    response = TestClient(app).post(
        "/api/tasks",
        headers=auth(token),
        json={"objective": "Deploy using password=vault:botpress_runtime"},
    )
    assert response.status_code == 200
    assert response.json()["objective"] == "Deploy using password=vault:botpress_runtime"


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


def test_second_action_cannot_replace_active_action(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    task = create_task(client, token)
    assert client.post(f"/api/tasks/{task['id']}/ready", headers=auth(token)).status_code == 200
    first = {
        "workspace_id": task["workspace_id"],
        "task_id": task["id"],
        "category": "files",
        "operation": "create_report",
        "risk": "reversible",
        "target": "artifact:first",
        "parameters": {},
        "requires_human_auth": False,
    }
    started = client.post("/api/actions/evaluate", headers=auth(token), json={"action": first})
    assert started.status_code == 200

    second = client.post(
        "/api/actions/evaluate",
        headers=auth(token),
        json={"action": {**first, "operation": "delete_report", "target": "artifact:second"}},
    )
    assert second.status_code == 409

    retained = client.get(f"/api/tasks/{task['id']}", headers=auth(token)).json()
    assert retained["pending_action"]["operation"] == "create_report"
    assert retained["pending_action"]["target"] == "artifact:first"


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
        "attempt_id": digest["attempt_id"],
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
    action_result = inspector.json()["action_results"][-1]
    assert UUID(action_result.pop("execution_id"))
    assert action_result == {
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
    pending = ActionRequest.model_validate(executing["pending_action"])
    digest = pending.digest()
    failed = client.post(
        f"/api/tasks/{task['id']}/action-result",
        headers=auth(token),
        json={
            "action_digest": digest,
            "attempt_id": str(pending.attempt_id),
            "succeeded": False,
            "result_summary": "The report generator returned an error.",
            "verification_evidence": ["Executor exit status was non-zero"],
            "artifact_refs": [],
        },
    )
    assert failed.status_code == 200
    assert failed.json()["status"] == "recovering"
    assert "returned an error" in failed.json()["blocker"]


def test_retried_identical_action_keeps_both_execution_results(monkeypatch):
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

    first = client.post("/api/actions/evaluate", headers=auth(token), json={"action": action}).json()
    first_pending = ActionRequest.model_validate(first["pending_action"])
    digest = first_pending.digest()
    failed = client.post(
        f"/api/tasks/{task['id']}/action-result",
        headers=auth(token),
        json={
            "action_digest": digest,
            "attempt_id": str(first_pending.attempt_id),
            "succeeded": False,
            "result_summary": "First attempt failed.",
            "verification_evidence": ["Executor returned non-zero"],
            "artifact_refs": [],
        },
    )
    assert failed.status_code == 200
    assert client.post(
        f"/api/tasks/{task['id']}/control",
        headers=auth(token),
        json={"action": "retry"},
    ).status_code == 200

    second = client.post("/api/actions/evaluate", headers=auth(token), json={"action": action})
    assert second.status_code == 200
    second_pending = ActionRequest.model_validate(second.json()["pending_action"])

    delayed_first_result = client.post(
        f"/api/tasks/{task['id']}/action-result",
        headers=auth(token),
        json={
            "action_digest": digest,
            "attempt_id": str(first_pending.attempt_id),
            "succeeded": True,
            "result_summary": "Delayed result from the first attempt.",
            "verification_evidence": ["Late executor callback"],
            "artifact_refs": [],
        },
    )
    assert delayed_first_result.status_code == 409
    still_active = client.get(f"/api/tasks/{task['id']}", headers=auth(token)).json()
    assert still_active["status"] == "executing"
    assert still_active["pending_action"]["attempt_id"] == str(second_pending.attempt_id)

    succeeded = client.post(
        f"/api/tasks/{task['id']}/action-result",
        headers=auth(token),
        json={
            "action_digest": second_pending.digest(),
            "attempt_id": str(second_pending.attempt_id),
            "succeeded": True,
            "result_summary": "Second attempt succeeded.",
            "verification_evidence": ["Artifact opened"],
            "artifact_refs": ["artifact:audit-report"],
        },
    )
    assert succeeded.status_code == 200

    results = client.get(
        f"/api/tasks/{task['id']}/inspector",
        headers=auth(token),
    ).json()["action_results"]
    matching = [item for item in results if item["operation"] == "create_report"]
    assert len(matching) == 2
    assert {item["succeeded"] for item in matching} == {False, True}
    assert len({item["execution_id"] for item in matching}) == 2
    assert len({item["attempt_id"] for item in matching}) == 2


def test_pause_resume_restores_active_action_to_attestable_state(monkeypatch):
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
    pending = ActionRequest.model_validate(executing["pending_action"])
    digest = pending.digest()

    paused = client.post(
        f"/api/tasks/{task['id']}/control",
        headers=auth(token),
        json={"action": "pause"},
    )
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    assert paused.json()["pending_action"] is not None

    resumed = client.post(
        f"/api/tasks/{task['id']}/control",
        headers=auth(token),
        json={"action": "resume"},
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "executing"

    verified = client.post(
        f"/api/tasks/{task['id']}/action-result",
        headers=auth(token),
        json={
            "action_digest": digest,
            "attempt_id": str(pending.attempt_id),
            "succeeded": True,
            "result_summary": "Report created.",
            "verification_evidence": ["Artifact opened"],
            "artifact_refs": ["artifact:audit-report"],
        },
    )
    assert verified.status_code == 200
    assert verified.json()["status"] == "ready"


def test_resume_rechecks_policy_added_while_action_is_paused(monkeypatch):
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
    executing = client.post("/api/actions/evaluate", headers=auth(token), json={"action": action})
    assert executing.status_code == 200
    assert client.post(
        f"/api/tasks/{task['id']}/control",
        headers=auth(token),
        json={"action": "pause"},
    ).status_code == 200
    denied = client.post(
        "/api/policies",
        headers=auth(token),
        json={
            "original_text": "Do not run file actions",
            "category": "files",
            "effect": "deny",
            "priority": 1,
        },
    )
    assert denied.status_code == 200

    resumed = client.post(
        f"/api/tasks/{task['id']}/control",
        headers=auth(token),
        json={"action": "resume"},
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "blocked_by_rule"
    assert resumed.json()["pending_action"] is None


def test_owner_can_resume_action_after_completing_human_auth(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    task = create_task(client, token)
    assert client.post(f"/api/tasks/{task['id']}/ready", headers=auth(token)).status_code == 200
    action = {
        "workspace_id": task["workspace_id"],
        "task_id": task["id"],
        "category": "files",
        "operation": "read_authenticated_file",
        "risk": "read",
        "target": "owner:file",
        "parameters": {},
        "requires_human_auth": True,
    }
    waiting = client.post("/api/actions/evaluate", headers=auth(token), json={"action": action})
    assert waiting.status_code == 200
    assert waiting.json()["status"] == "awaiting_login"

    operator = client.post(
        f"/api/tasks/{task['id']}/control",
        headers={**auth(token), "X-ALTER-Actor-Role": "operator"},
        json={"action": "authentication_complete"},
    )
    assert operator.status_code == 403

    resumed = client.post(
        f"/api/tasks/{task['id']}/control",
        headers=auth(token),
        json={"action": "authentication_complete"},
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "executing"
    assert resumed.json()["pending_action"]["operation"] == "read_authenticated_file"


def test_completion_rolls_back_when_evidence_persistence_fails(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    task = create_task(client, token)
    assert client.post(f"/api/tasks/{task['id']}/ready", headers=auth(token)).status_code == 200

    class FailingMemoryStore:
        def upsert(self, **_kwargs):
            raise RuntimeError("simulated memory outage")

    monkeypatch.setattr(core_api, "memory_store", FailingMemoryStore())
    failed = TestClient(app, raise_server_exceptions=False).post(
        f"/api/tasks/{task['id']}/complete",
        headers=auth(token),
        json={
            "result_summary": "Result exists.",
            "verification_evidence": ["Verification passed"],
            "artifact_refs": [],
            "acceptance_criteria_met": True,
        },
    )
    assert failed.status_code == 500
    unchanged = client.get(f"/api/tasks/{task['id']}", headers=auth(token)).json()
    assert unchanged["status"] == "ready"


def test_action_result_rolls_back_when_evidence_persistence_fails(monkeypatch):
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
    pending = ActionRequest.model_validate(executing["pending_action"])
    digest = pending.digest()

    class FailingMemoryStore:
        def upsert(self, **_kwargs):
            raise RuntimeError("simulated memory outage")

    monkeypatch.setattr(core_api, "memory_store", FailingMemoryStore())
    failed = TestClient(app, raise_server_exceptions=False).post(
        f"/api/tasks/{task['id']}/action-result",
        headers=auth(token),
        json={
            "action_digest": digest,
            "attempt_id": str(pending.attempt_id),
            "succeeded": True,
            "result_summary": "Report created.",
            "verification_evidence": ["Artifact opened"],
            "artifact_refs": [],
        },
    )
    assert failed.status_code == 500
    unchanged = client.get(f"/api/tasks/{task['id']}", headers=auth(token)).json()
    assert unchanged["status"] == "executing"
    assert unchanged["pending_action"]["operation"] == "create_report"


def test_typed_memory_validates_every_field_and_delete_route_is_reachable(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)

    rejected = client.post(
        "/api/memory/items",
        headers=auth(token),
        json={
            "key": "typed-secret",
            "kind": "fact",
            "content": "Public documentation note",
            "source": "https://user:password@example.com",
            "tags": ["docs"],
        },
    )
    assert rejected.status_code == 422

    created = client.post(
        "/api/memory/items",
        headers=auth(token),
        json={
            "key": "typed-one",
            "kind": "fact",
            "content": "Safe typed memory",
            "source": "owner",
            "tags": ["docs"],
        },
    )
    assert created.status_code == 200
    deleted = client.delete("/api/memory/items/typed-one", headers=auth(token))
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "key": "typed-one"}
    listed = client.get("/api/memory/items", headers=auth(token)).json()
    assert all(item["key"] != "typed-one" for item in listed["items"])


def test_task_inspector_filters_evidence_before_applying_limits(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    task = create_task(client, token)
    workspace_id = UUID(task["workspace_id"])
    user_id = UUID(os.environ["ALTER_OWNER_USER_ID"])
    monkeypatch.setattr(productivity_api, "memory_store", None)

    for index in range(260):
        core_api._memory_fallback[
            (workspace_id, user_id, "task.plan", f"unrelated-{index}")
        ] = {"plan": f"unrelated {index}"}
    core_api._memory_fallback[
        (workspace_id, user_id, "task.plan", task["id"])
    ] = {"plan": "target plan", "provider": "test"}
    core_api._memory_fallback[
        (workspace_id, user_id, "task.action_result", f"{task['id']}:attempt-1")
    ] = {"execution_id": "attempt-1", "succeeded": False}
    core_api._memory_fallback[
        (workspace_id, user_id, "task.action_result", f"{task['id']}:attempt-2")
    ] = {"execution_id": "attempt-2", "succeeded": True}

    inspector = client.get(f"/api/tasks/{task['id']}/inspector", headers=auth(token))
    assert inspector.status_code == 200
    assert inspector.json()["plan"]["plan"] == "target plan"
    assert inspector.json()["action_results"] == [
        {"execution_id": "attempt-2", "succeeded": True},
        {"execution_id": "attempt-1", "succeeded": False},
    ]


def test_fallback_memory_update_moves_existing_key_to_newest_position(monkeypatch):
    principal = Principal(user_id=uuid4(), workspace_id=uuid4())
    monkeypatch.setattr(productivity_api, "memory_store", None)
    first_key = (principal.workspace_id, principal.user_id, "automation", "first")
    second_key = (principal.workspace_id, principal.user_id, "automation", "second")
    core_api._memory_fallback[first_key] = {"version": 1}
    core_api._memory_fallback[second_key] = {"version": 1}
    core_api._memory_fallback[first_key] = {"version": 2}

    rows = productivity_api._memory_list(principal, "automation", 2)
    assert [row["key"] for row in rows] == ["first", "second"]
    assert rows[0]["value"] == {"version": 2}


def test_compound_secret_field_names_are_rejected_but_vault_aliases_are_allowed():
    for field_name in (
        "client_secret",
        "secret_key",
        "api_token",
        "private_key",
        "refresh_secret",
    ):
        assert contains_high_confidence_secret({field_name: "high-confidence-secret-value"}) is True
        assert contains_high_confidence_secret({field_name: "vault:approved_alias"}) is False
    assert contains_high_confidence_secret({"ghp_" + "A" * 30: "credential"}) is True


def test_rag_paths_exclude_normalized_runtime_vault_namespaces(monkeypatch):
    token = configure_owner(monkeypatch)
    workspace_id = UUID(os.environ["ALTER_OWNER_WORKSPACE_ID"])
    user_id = UUID(os.environ["ALTER_OWNER_USER_ID"])
    core_api._memory_fallback[(workspace_id, user_id, " VAULT_SECURE ", "runtime")] = {
        "note": "purple elephant runtime credential"
    }
    core_api._memory_fallback[(workspace_id, user_id, " _VaUlT.Runtime ", "runtime-two")] = {
        "note": "purple elephant second credential"
    }
    core_api._memory_fallback[(workspace_id, user_id, "knowledge", "safe")] = {
        "note": "purple elephant documentation"
    }

    response = TestClient(app).post(
        "/api/rag/search",
        headers=auth(token),
        json={"query": "purple elephant", "limit": 10},
    )
    assert response.status_code == 200
    assert [item["namespace"] for item in response.json()["hits"]] == ["knowledge"]

    principal = Principal(user_id=user_id, workspace_id=workspace_id)
    conversation_hits = conversation_api._rag(principal, "purple elephant")
    assert [item["namespace"] for item in conversation_hits] == ["knowledge"]


def test_policy_denied_stale_approval_is_audited(monkeypatch):
    token = configure_owner(monkeypatch)
    events: list[dict] = []

    class CapturingAuditStore:
        def write(self, **kwargs):
            events.append(kwargs)

    monkeypatch.setattr(core_api, "audit_store", CapturingAuditStore())
    client = TestClient(app)
    task = create_task(client, token)
    assert client.post(f"/api/tasks/{task['id']}/ready", headers=auth(token)).status_code == 200
    action = {
        "workspace_id": task["workspace_id"],
        "task_id": task["id"],
        "category": "social_publish",
        "operation": "publish_post",
        "risk": "public",
        "target": "social:post",
        "parameters": {},
        "requires_human_auth": False,
    }
    waiting = client.post("/api/actions/evaluate", headers=auth(token), json={"action": action}).json()
    digest = ActionRequest.model_validate(waiting["pending_action"]).digest()
    denied = client.post(
        "/api/policies",
        headers=auth(token),
        json={
            "original_text": "Do not publish",
            "category": "social_publish",
            "effect": "deny",
            "priority": 1,
        },
    )
    assert denied.status_code == 200

    approval = client.post(
        f"/api/tasks/{task['id']}/approve",
        headers=auth(token),
        json={"action_digest": digest},
    )
    assert approval.status_code == 409
    assert any(event["event_type"] == "action.approval_blocked_by_policy" for event in events)
