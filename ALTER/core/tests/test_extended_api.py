from uuid import uuid4

from fastapi.testclient import TestClient

from api.index import app
from alter_core import conversation_api
from alter_core.botpress_gateway import BotpressGateway


def configure_owner(monkeypatch):
    token = "test-owner-token-extended"
    monkeypatch.setenv("ALTER_API_TOKEN", token)
    monkeypatch.setenv("ALTER_OWNER_USER_ID", str(uuid4()))
    monkeypatch.setenv("ALTER_OWNER_WORKSPACE_ID", str(uuid4()))
    return token


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_conversation_requires_owner(monkeypatch):
    configure_owner(monkeypatch)
    response = TestClient(app).get("/api/conversation")
    assert response.status_code == 401


def test_conversation_redacts_secret_before_persistence(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    secret = "this-is-a-secret-password"

    saved = client.post(
        "/api/conversation/messages",
        headers=auth(token),
        json={"role": "user", "text": f"password={secret}"},
    )
    assert saved.status_code == 200
    assert saved.json()["redacted"] is True
    assert secret not in saved.json()["text"]
    assert "REDACTED" in saved.json()["text"]

    history = client.get("/api/conversation", headers=auth(token))
    assert history.status_code == 200
    serialized = str(history.json())
    assert secret not in serialized
    assert "REDACTED" in serialized


def test_conversation_ai_is_fail_closed_without_runtime_credential(monkeypatch):
    token = configure_owner(monkeypatch)
    monkeypatch.setattr(
        conversation_api,
        "gateway",
        BotpressGateway(token="", bot_id=BotpressGateway.DEFAULT_BOT_ID),
    )

    response = TestClient(app).post(
        "/api/conversation/respond",
        headers=auth(token),
        json={"text": "Привіт", "mode": "normal"},
    )
    assert response.status_code == 503
    assert "credential" in response.json()["detail"].lower()


def test_system_status_is_truthful_and_secret_safe(monkeypatch):
    token = configure_owner(monkeypatch)
    response = TestClient(app).get("/api/system/status", headers=auth(token))
    assert response.status_code == 200
    body = response.json()
    assert "components" in body
    assert body["vault"]["raw_secret_exposure"] is False
    assert "DATABASE_URL" not in str(body)
    assert "ALTER_API_TOKEN" not in str(body)


def test_connector_gateway_is_owner_only(monkeypatch):
    configure_owner(monkeypatch)
    response = TestClient(app).get("/api/gateway/connectors")
    assert response.status_code == 401


def test_connector_gateway_reports_real_boundaries(monkeypatch):
    token = configure_owner(monkeypatch)
    monkeypatch.delenv("GITHUB_CONNECTOR_TOKEN", raising=False)
    monkeypatch.delenv("VERCEL_CONNECTOR_TOKEN", raising=False)

    response = TestClient(app).get("/api/gateway/connectors", headers=auth(token))
    assert response.status_code == 200
    by_key = {item["key"]: item for item in response.json()}
    assert by_key["posthog"]["status"] == "connected"
    assert by_key["github"]["status"] == "not_configured"
    assert by_key["vercel"]["status"] == "not_configured"
    assert by_key["botpress"]["write_boundary"] == "alterThink-only-no-side-effects"
