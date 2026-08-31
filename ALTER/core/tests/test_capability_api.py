from uuid import uuid4

from api.index import app
from fastapi.testclient import TestClient


def configure_owner(monkeypatch):
    token = "test-owner-token-capabilities"
    monkeypatch.setenv("ALTER_API_TOKEN", token)
    monkeypatch.setenv("ALTER_OWNER_USER_ID", str(uuid4()))
    monkeypatch.setenv("ALTER_OWNER_WORKSPACE_ID", str(uuid4()))
    return token


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_capability_audit_requires_owner(monkeypatch):
    configure_owner(monkeypatch)
    response = TestClient(app).get("/api/system/capabilities")
    assert response.status_code == 401


def test_capability_audit_is_complete_and_truthful(monkeypatch):
    token = configure_owner(monkeypatch)
    response = TestClient(app).get("/api/system/capabilities", headers=auth(token))
    assert response.status_code == 200

    body = response.json()
    assert body["spec_version"] == "1.0"
    assert body["runtime_truth_contract"] is True
    assert len(body["capabilities"]) == 30

    by_key = {item["key"]: item for item in body["capabilities"]}
    assert by_key["self_audit"]["status"] == "ready"
    assert by_key["remote_pc"]["status"] == "waiting"
    assert by_key["browser"]["status"] == "deferred"
    assert by_key["android"]["status"] == "deferred"
    assert by_key["model_install"]["status"] == "waiting"
    assert by_key["hard_stop"]["status"] == "planned"

    serialized = str(body)
    assert "ALTER_API_TOKEN" not in serialized
    assert "DATABASE_URL=" not in serialized
