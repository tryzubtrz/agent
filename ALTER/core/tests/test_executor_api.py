from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient

from alter_core import executor_api
from alter_core.api import _memory_fallback
from alter_core.main import app


def configure_owner(monkeypatch) -> str:
    token = "test-owner-token-executor"
    monkeypatch.setenv("ALTER_API_TOKEN", token)
    monkeypatch.setenv("ALTER_OWNER_USER_ID", str(uuid4()))
    monkeypatch.setenv("ALTER_OWNER_WORKSPACE_ID", str(uuid4()))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _memory_fallback.clear()
    return token


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_executing_connector_task(client: TestClient, token: str, connector: str = "github") -> dict:
    created = client.post(
        "/api/tasks",
        headers=auth(token),
        json={"objective": f"Verify {connector} connector"},
    )
    assert created.status_code == 200, created.text
    task = created.json()
    assert client.post(f"/api/tasks/{task['id']}/ready", headers=auth(token)).status_code == 200
    evaluated = client.post(
        "/api/actions/evaluate",
        headers=auth(token),
        json={
            "action": {
                "workspace_id": task["workspace_id"],
                "task_id": task["id"],
                "category": "connector",
                "operation": "self_test",
                "risk": "read",
                "target": connector,
                "parameters": {},
                "requires_human_auth": False,
            }
        },
    )
    assert evaluated.status_code == 200, evaluated.text
    assert evaluated.json()["status"] == "executing"
    return evaluated.json()


def test_executor_records_tool_verified_success_without_owner_attestation(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    task = create_executing_connector_task(client, token)

    monkeypatch.setattr(
        executor_api,
        "_run_connector_self_test",
        lambda connector, principal: {
            "connector": connector,
            "ok": True,
            "repository": "tryzubtrz/agent",
            "private": True,
            "default_branch": "main",
            "secret_exposed": False,
        },
    )

    response = client.post(f"/api/tasks/{task['id']}/execute-pending", headers=auth(token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["task"]["status"] == "ready"
    assert body["task"]["pending_action"] is None
    assert body["execution"]["succeeded"] is True
    assert body["execution"]["verification_method"] == "tool_executor"
    assert body["execution"]["tool_output"]["repository"] == "tryzubtrz/agent"
    assert body["execution"]["tool_output"]["secret_exposed"] is False

    saved = [
        value
        for (_workspace, _user, namespace, _key), value in _memory_fallback.items()
        if namespace == "task.action_result"
    ]
    assert saved
    assert saved[-1]["verification_method"] == "tool_executor"
    assert saved[-1]["action_digest"] == body["execution"]["action_digest"]


def test_executor_persists_provider_failure_and_enters_recovery(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    task = create_executing_connector_task(client, token, "vercel")

    def fail(_connector, _principal):
        raise HTTPException(status_code=503, detail="Vercel connector credential was rejected")

    monkeypatch.setattr(executor_api, "_run_connector_self_test", fail)
    response = client.post(f"/api/tasks/{task['id']}/execute-pending", headers=auth(token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["execution"]["succeeded"] is False
    assert body["execution"]["verification_method"] == "tool_executor"
    assert body["task"]["status"] == "recovering"
    assert body["task"]["pending_action"] is None
    assert "credential was rejected" in body["task"]["blocker"]


def test_executor_rechecks_latest_policy_before_tool_call(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    task = create_executing_connector_task(client, token)
    called = {"value": False}

    def should_not_run(_connector, _principal):
        called["value"] = True
        return {"connector": "github", "ok": True, "secret_exposed": False}

    monkeypatch.setattr(executor_api, "_run_connector_self_test", should_not_run)
    policy = client.post(
        "/api/policies",
        headers=auth(token),
        json={
            "original_text": "Block connector execution during maintenance",
            "category": "connector",
            "effect": "deny",
            "priority": 1,
        },
    )
    assert policy.status_code == 200, policy.text

    response = client.post(f"/api/tasks/{task['id']}/execute-pending", headers=auth(token))
    assert response.status_code == 409
    assert called["value"] is False

    current = client.get(f"/api/tasks/{task['id']}", headers=auth(token))
    assert current.status_code == 200
    assert current.json()["status"] == "blocked_by_rule"
    assert current.json()["pending_action"] is None


def test_executor_rejects_non_read_or_unsupported_action(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    created = client.post(
        "/api/tasks",
        headers=auth(token),
        json={"objective": "Unsafe executor attempt"},
    ).json()
    client.post(f"/api/tasks/{created['id']}/ready", headers=auth(token))
    evaluated = client.post(
        "/api/actions/evaluate",
        headers=auth(token),
        json={
            "action": {
                "workspace_id": created["workspace_id"],
                "task_id": created["id"],
                "category": "connector",
                "operation": "self_test",
                "risk": "reversible",
                "target": "github",
                "parameters": {},
            }
        },
    )
    assert evaluated.status_code == 200
    assert evaluated.json()["status"] == "executing"

    response = client.post(f"/api/tasks/{created['id']}/execute-pending", headers=auth(token))
    assert response.status_code == 422
    current = client.get(f"/api/tasks/{created['id']}", headers=auth(token)).json()
    assert current["pending_action"] is not None


def test_operator_cannot_execute_external_connector_even_with_owner_token_downgrade(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    task = create_executing_connector_task(client, token)
    response = client.post(
        f"/api/tasks/{task['id']}/execute-pending",
        headers={**auth(token), "X-ALTER-Actor-Role": "operator"},
    )
    assert response.status_code == 403
