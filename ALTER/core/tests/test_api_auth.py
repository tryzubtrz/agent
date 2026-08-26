from uuid import uuid4

from fastapi.testclient import TestClient

from alter_core.api import app, orchestrator


def configure_owner(monkeypatch):
    user_id = uuid4()
    workspace_id = uuid4()
    token = "test-owner-token"
    monkeypatch.setenv("ALTER_API_TOKEN", token)
    monkeypatch.setenv("ALTER_OWNER_USER_ID", str(user_id))
    monkeypatch.setenv("ALTER_OWNER_WORKSPACE_ID", str(workspace_id))
    return user_id, workspace_id, token


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_health_is_public():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_task_api_rejects_missing_bearer(monkeypatch):
    configure_owner(monkeypatch)
    response = TestClient(app).post("/tasks", json={"objective": "test"})
    assert response.status_code == 401


def test_task_api_rejects_wrong_bearer(monkeypatch):
    configure_owner(monkeypatch)
    response = TestClient(app).post(
        "/tasks",
        headers={"Authorization": "Bearer wrong-token"},
        json={"objective": "test"},
    )
    assert response.status_code == 401


def test_task_identity_comes_from_authenticated_principal(monkeypatch):
    user_id, workspace_id, token = configure_owner(monkeypatch)
    response = TestClient(app).post(
        "/tasks",
        headers=auth(token),
        json={"objective": "Build ALTER"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["owner_user_id"] == str(user_id)
    assert body["workspace_id"] == str(workspace_id)


def test_task_list_is_owner_and_workspace_scoped(monkeypatch):
    user_id, workspace_id, token = configure_owner(monkeypatch)
    own = orchestrator.create_task(
        workspace_id=workspace_id,
        owner_user_id=user_id,
        objective="own live task",
    )
    orchestrator.create_task(
        workspace_id=uuid4(),
        owner_user_id=uuid4(),
        objective="foreign live task",
    )

    response = TestClient(app).get("/api/tasks", headers=auth(token))

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert str(own.id) in ids
    assert all(item["objective"] != "foreign live task" for item in response.json())


def test_foreign_task_is_hidden_from_authenticated_owner(monkeypatch):
    _user_id, _workspace_id, token = configure_owner(monkeypatch)
    foreign_task = orchestrator.create_task(
        workspace_id=uuid4(),
        owner_user_id=uuid4(),
        objective="foreign",
    )

    response = TestClient(app).get(
        f"/tasks/{foreign_task.id}",
        headers=auth(token),
    )

    assert response.status_code == 404


def test_owner_policy_is_created_in_authenticated_workspace(monkeypatch):
    _user_id, workspace_id, token = configure_owner(monkeypatch)
    response = TestClient(app).post(
        "/policies",
        headers=auth(token),
        json={
            "original_text": "Не відкривай TikTok",
            "category": "tiktok",
            "effect": "deny",
            "priority": 10,
        },
    )

    assert response.status_code == 200
    assert response.json()["workspace_id"] == str(workspace_id)


def test_memory_round_trip_is_authenticated_and_scoped(monkeypatch):
    _user_id, _workspace_id, token = configure_owner(monkeypatch)
    client = TestClient(app)

    missing = client.get("/api/memory")
    assert missing.status_code == 401

    saved = client.put(
        "/api/memory",
        headers=auth(token),
        json={"namespace": "profile", "key": "language", "value": "uk"},
    )
    assert saved.status_code == 200

    listed = client.get("/api/memory?namespace=profile", headers=auth(token))
    assert listed.status_code == 200
    assert any(item["key"] == "language" and item["value"] == "uk" for item in listed.json())


def test_connector_registry_round_trip_is_authenticated(monkeypatch):
    _user_id, _workspace_id, token = configure_owner(monkeypatch)
    client = TestClient(app)

    saved = client.put(
        "/api/connectors/test-connector",
        headers=auth(token),
        json={
            "status": "available",
            "capabilities": ["read"],
            "details": {"verified": True},
        },
    )
    assert saved.status_code == 200
    assert saved.json()["connector_key"] == "test-connector"

    listed = client.get("/api/connectors", headers=auth(token))
    assert listed.status_code == 200
    assert any(item["connector_key"] == "test-connector" for item in listed.json())


def test_audit_endpoint_requires_owner(monkeypatch):
    configure_owner(monkeypatch)
    response = TestClient(app).get("/api/audit")
    assert response.status_code == 401
