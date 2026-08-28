from uuid import uuid4

from fastapi.testclient import TestClient

from alter_core import executor_api
from alter_core.api import _memory_fallback
from alter_core.main import app
from alter_core.models import ActionRequest


def configure_owner(monkeypatch) -> str:
    token = "test-owner-token-executor-approval"
    monkeypatch.setenv("ALTER_API_TOKEN", token)
    monkeypatch.setenv("ALTER_OWNER_USER_ID", str(uuid4()))
    monkeypatch.setenv("ALTER_OWNER_WORKSPACE_ID", str(uuid4()))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _memory_fallback.clear()
    return token


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_executor_can_satisfy_current_require_approval_with_exact_action_digest(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    created = client.post(
        "/api/tasks",
        headers=auth(token),
        json={"objective": "Verify GitHub connector with explicit approval"},
    ).json()
    assert client.post(f"/api/tasks/{created['id']}/ready", headers=auth(token)).status_code == 200

    rule = client.post(
        "/api/policies",
        headers=auth(token),
        json={
            "original_text": "Require my approval before connector checks",
            "category": "connector",
            "effect": "require_approval",
            "priority": 1,
        },
    )
    assert rule.status_code == 200, rule.text

    evaluated = client.post(
        "/api/actions/evaluate",
        headers=auth(token),
        json={
            "action": {
                "workspace_id": created["workspace_id"],
                "task_id": created["id"],
                "category": "connector",
                "operation": "self_test",
                "risk": "read",
                "target": "github",
                "parameters": {},
            }
        },
    )
    assert evaluated.status_code == 200, evaluated.text
    assert evaluated.json()["status"] == "awaiting_approval"
    action = ActionRequest.model_validate(evaluated.json()["pending_action"])
    digest = action.digest()

    called = {"count": 0}

    def succeed(connector, _principal):
        called["count"] += 1
        return {
            "connector": connector,
            "ok": True,
            "repository": "tryzubtrz/agent",
            "private": True,
            "default_branch": "main",
            "secret_exposed": False,
        }

    monkeypatch.setattr(executor_api, "_run_connector_self_test", succeed)

    missing = client.post(f"/api/tasks/{created['id']}/execute-pending", headers=auth(token))
    assert missing.status_code == 409
    assert called["count"] == 0

    approved = client.post(
        f"/api/tasks/{created['id']}/execute-pending",
        headers=auth(token),
        json={"approval_digest": digest},
    )
    assert approved.status_code == 200, approved.text
    assert called["count"] == 1
    assert approved.json()["task"]["status"] == "ready"
    assert approved.json()["execution"]["verification_method"] == "tool_executor"


def test_executor_rejects_wrong_inline_approval_digest_without_tool_call(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    created = client.post(
        "/api/tasks",
        headers=auth(token),
        json={"objective": "Reject mismatched execution approval"},
    ).json()
    client.post(f"/api/tasks/{created['id']}/ready", headers=auth(token))

    called = {"value": False}

    def should_not_run(_connector, _principal):
        called["value"] = True
        return {"connector": "github", "ok": True, "secret_exposed": False}

    monkeypatch.setattr(executor_api, "_run_connector_self_test", should_not_run)
    evaluated = client.post(
        "/api/actions/evaluate",
        headers=auth(token),
        json={
            "action": {
                "workspace_id": created["workspace_id"],
                "task_id": created["id"],
                "category": "connector",
                "operation": "self_test",
                "risk": "read",
                "target": "github",
                "parameters": {},
            }
        },
    )
    assert evaluated.status_code == 200
    wrong_digest = "0" * 64
    response = client.post(
        f"/api/tasks/{created['id']}/execute-pending",
        headers=auth(token),
        json={"approval_digest": wrong_digest},
    )
    assert response.status_code == 409
    assert called["value"] is False
    current = client.get(f"/api/tasks/{created['id']}", headers=auth(token)).json()
    assert current["pending_action"] is not None
