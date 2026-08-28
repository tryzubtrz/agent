from uuid import uuid4

from fastapi.testclient import TestClient

from alter_core.api import _memory_fallback
from alter_core.auth import issue_member_token
from alter_core.main import app


def configure_owner(monkeypatch):
    user_id = uuid4()
    workspace_id = uuid4()
    token = "test-owner-token-with-sufficient-entropy"
    monkeypatch.setenv("ALTER_API_TOKEN", token)
    monkeypatch.setenv("ALTER_MEMBER_TOKEN_SECRET", "test-member-signing-secret-32-bytes-minimum")
    monkeypatch.setenv("ALTER_OWNER_USER_ID", str(user_id))
    monkeypatch.setenv("ALTER_OWNER_WORKSPACE_ID", str(workspace_id))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _memory_fallback.clear()
    return user_id, workspace_id, token


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_member_session(client: TestClient, owner_token: str, *, role: str) -> dict:
    invite = client.post(
        "/api/access/invites",
        headers=bearer(owner_token),
        json={"label": f"{role}-test", "role": role},
    )
    assert invite.status_code == 200, invite.text
    redeemed = client.post(
        "/api/auth/redeem-invite",
        json={"code": invite.json()["code"]},
    )
    assert redeemed.status_code == 200, redeemed.text
    return redeemed.json()


def test_viewer_redeems_invite_without_owner_bearer_and_gets_scoped_session(monkeypatch):
    user_id, workspace_id, owner_token = configure_owner(monkeypatch)
    client = TestClient(app)

    session = create_member_session(client, owner_token, role="viewer")
    token = session["access_token"]
    assert session["token_type"] == "bearer"
    assert session["member"]["role"] == "viewer"

    me = client.get("/api/auth/me", headers=bearer(token))
    assert me.status_code == 200
    assert me.json()["user_id"] == str(user_id)
    assert me.json()["workspace_id"] == str(workspace_id)
    assert me.json()["actor_role"] == "viewer"
    assert "memory.read" in me.json()["capabilities"]


def test_viewer_can_read_memory_but_cannot_create_tasks_or_manage_access(monkeypatch):
    _user_id, _workspace_id, owner_token = configure_owner(monkeypatch)
    client = TestClient(app)
    token = create_member_session(client, owner_token, role="viewer")["access_token"]

    memory = client.get("/api/memory?namespace=profile", headers=bearer(token))
    assert memory.status_code == 200

    task = client.post("/tasks", headers=bearer(token), json={"objective": "must be denied"})
    assert task.status_code == 403
    assert "tasks.write" in task.json()["detail"]

    members = client.get("/api/access/members", headers=bearer(token))
    assert members.status_code == 403


def test_operator_can_create_task_but_cannot_open_owner_only_access_admin(monkeypatch):
    _user_id, _workspace_id, owner_token = configure_owner(monkeypatch)
    client = TestClient(app)
    token = create_member_session(client, owner_token, role="operator")["access_token"]

    task = client.post("/tasks", headers=bearer(token), json={"objective": "operator task"})
    assert task.status_code == 200, task.text

    members = client.get("/api/access/members", headers=bearer(token))
    assert members.status_code == 403


def test_member_token_tampering_is_rejected(monkeypatch):
    user_id, workspace_id, _owner_token = configure_owner(monkeypatch)
    token, _ttl = issue_member_token(
        member_id="member-test",
        user_id=user_id,
        workspace_id=workspace_id,
        role="viewer",
        capabilities=["tasks.read"],
    )
    head, payload, signature = token.split(".")
    tampered_payload = ("A" if payload[0] != "A" else "B") + payload[1:]
    tampered = f"{head}.{tampered_payload}.{signature}"

    response = TestClient(app).get("/api/auth/me", headers=bearer(tampered))
    assert response.status_code == 401
