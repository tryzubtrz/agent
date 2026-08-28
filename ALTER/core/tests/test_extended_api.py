from types import SimpleNamespace
from uuid import uuid4

from alter_core import conversation_api
from alter_core.botpress_gateway import BotpressGateway
from api.index import app
from fastapi.testclient import TestClient


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


def test_redactor_covers_database_urls_jwts_and_private_keys():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhbHRlci1vd25lciJ9.signature0123456789"
    private_key = "-----BEGIN PRIVATE KEY-----\nVERYSECRETKEYMATERIAL\n-----END PRIVATE KEY-----"
    source = (
        "DATABASE_URL=postgresql://alter:super-secret-db-password@db.example.com/neondb\n"
        f"token={jwt}\n{private_key}"
    )

    safe, changed = conversation_api._redact(source)
    assert changed is True
    assert "super-secret-db-password" not in safe
    assert jwt not in safe
    assert "VERYSECRETKEYMATERIAL" not in safe
    assert "[REDACTED]" in safe
    assert "[REDACTED_JWT]" in safe
    assert "[REDACTED_PRIVATE_KEY]" in safe


def test_redactor_covers_basic_authorization_credentials():
    credential = "dXNlcjpwYXNzd29yZA=="
    safe, changed = conversation_api._redact(f"Authorization: Basic {credential}")
    assert changed is True
    assert credential not in safe
    assert safe == "Authorization=[REDACTED]"


def test_redactor_preserves_vault_aliases_in_authorization_headers():
    for source in (
        "Authorization: Basic vault:botpress_runtime",
        "Authorization: Bearer vault:github_connector",
    ):
        safe, changed = conversation_api._redact(source)
        assert changed is False
        assert safe == source


def test_redactor_covers_json_authorization_and_preserves_vault_reference():
    credential = "dXNlcjpwYXNzd29yZA=="
    source = f'{{"Authorization":"Basic {credential}"}}'
    safe, changed = conversation_api._redact(source)
    assert changed is True
    assert credential not in safe
    assert safe == '{"Authorization":"[REDACTED]"}'

    vault_source = '{"Authorization":"Basic vault:botpress_runtime"}'
    vault_safe, vault_changed = conversation_api._redact(vault_source)
    assert vault_changed is False
    assert vault_safe == vault_source


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


def test_conversation_rejects_specialist_side_effect_claim(monkeypatch):
    token = configure_owner(monkeypatch)

    class UnsafeGateway:
        def status(self):
            return SimpleNamespace(configured=True)

        def think(self, **_kwargs):
            return {
                "response": "I changed something.",
                "sideEffectsPerformed": True,
                "boundary": "core-policy-required",
            }

    monkeypatch.setattr(conversation_api, "gateway", UnsafeGateway())
    response = TestClient(app).post(
        "/api/conversation/respond",
        headers=auth(token),
        json={"text": "Тест", "mode": "normal"},
    )
    assert response.status_code == 502
    assert "no-side-effect" in response.json()["detail"]


def test_conversation_rejects_wrong_specialist_boundary(monkeypatch):
    token = configure_owner(monkeypatch)

    class WrongBoundaryGateway:
        def status(self):
            return SimpleNamespace(configured=True)

        def think(self, **_kwargs):
            return {
                "response": "Safe text only.",
                "sideEffectsPerformed": False,
                "boundary": "direct-execution-allowed",
            }

    monkeypatch.setattr(conversation_api, "gateway", WrongBoundaryGateway())
    response = TestClient(app).post(
        "/api/conversation/respond",
        headers=auth(token),
        json={"text": "Тест", "mode": "normal"},
    )
    assert response.status_code == 502
    assert "boundary" in response.json()["detail"].lower()


def test_conversation_rejects_oversized_specialist_response(monkeypatch):
    token = configure_owner(monkeypatch)

    class OversizedGateway:
        def status(self):
            return SimpleNamespace(configured=True)

        def think(self, **_kwargs):
            return {
                "response": "x" * 50_001,
                "sideEffectsPerformed": False,
                "boundary": "core-policy-required",
            }

    monkeypatch.setattr(conversation_api, "gateway", OversizedGateway())
    response = TestClient(app).post(
        "/api/conversation/respond",
        headers=auth(token),
        json={"text": "Тест", "mode": "normal"},
    )
    assert response.status_code == 502
    assert "oversized" in response.json()["detail"].lower()


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
    assert by_key["github"]["status"] == "credential_required"
    assert by_key["vercel"]["status"] == "credential_required"
    assert by_key["botpress"]["write_boundary"] == "alterThink-only-no-side-effects"
