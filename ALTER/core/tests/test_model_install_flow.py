from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from alter_core import executor_api, model_api
from alter_core.api import _memory_fallback
from alter_core.main import app
from alter_core.models import ActionRequest


def _configure_owner(monkeypatch) -> str:
    token = "test-owner-token-model-install"
    monkeypatch.setenv("ALTER_API_TOKEN", token)
    monkeypatch.setenv("ALTER_OWNER_USER_ID", str(uuid4()))
    monkeypatch.setenv("ALTER_OWNER_WORKSPACE_ID", str(uuid4()))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _memory_fallback.clear()
    return token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_model_install_requires_exact_owner_approval_and_queues_allowlisted_job(monkeypatch):
    token = _configure_owner(monkeypatch)
    monkeypatch.setattr(
        model_api.local_gateway,
        "status",
        lambda: SimpleNamespace(
            configured=True,
            connected=True,
            credential_configured=True,
            installed_models=(),
            active_jobs=0,
            model=None,
            provider="local-ollama",
            action="localReason",
        ),
    )
    monkeypatch.setattr(
        executor_api,
        "_run_model_install",
        lambda model_id, approval_digest: {
            "job_id": "runtime-job-1",
            "state": "queued",
            "model_id": model_id,
            "secret_exposed": False,
        },
    )
    client = TestClient(app)

    requested = client.post("/api/models/qwen3-8b/install-request", headers=_auth(token))
    assert requested.status_code == 200, requested.text
    task = requested.json()["task"]
    assert task["status"] == "awaiting_approval"
    assert task["pending_action"]["category"] == "model_install"
    assert task["pending_action"]["parameters"]["runtime_ref"] == "qwen3:8b"
    digest = ActionRequest.model_validate(task["pending_action"]).digest()

    missing = client.post(f"/api/tasks/{task['id']}/execute-pending", headers=_auth(token))
    assert missing.status_code == 409

    executed = client.post(
        f"/api/tasks/{task['id']}/execute-pending",
        headers=_auth(token),
        json={"approval_digest": digest},
    )
    assert executed.status_code == 200, executed.text
    body = executed.json()
    assert body["task"]["status"] == "ready"
    assert body["execution"]["operation"] == "pull_allowlisted_model"
    assert body["execution"]["tool_output"]["state"] == "queued"
    assert "policy_approval_recorded=true" in body["execution"]["verification_evidence"]
