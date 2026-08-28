from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from alter_core import agent_api, conversation_api, user_facing_response
from alter_core.botpress_contract import (
    BotpressInternalLeakError,
    contains_internal_reasoning_leak,
    validate_specialist_output,
)
from api.index import app


def _configure_owner(monkeypatch) -> str:
    token = "test-owner-token-output-guard"
    monkeypatch.setenv("ALTER_API_TOKEN", token)
    monkeypatch.setenv("ALTER_OWNER_USER_ID", str(uuid4()))
    monkeypatch.setenv("ALTER_OWNER_WORKSPACE_ID", str(uuid4()))
    return token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _output(response: str) -> dict[str, object]:
    return {
        "response": response,
        "sideEffectsPerformed": False,
        "boundary": "core-policy-required",
    }


class RepairingGateway:
    def __init__(self):
        self.calls = []

    def status(self):
        return SimpleNamespace(configured=True)

    def think(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return _output(
                "Об’єктив: відповісти користувачу. Я — модуль міркування ALTER. "
                "Уточнення для Core: чи це привітання?"
            )
        return _output("Все добре 🙂 А ти як?")


class LeakingGateway:
    def status(self):
        return SimpleNamespace(configured=True)

    def think(self, **_kwargs):
        return _output("Я — модуль міркування ALTER. Уточнення для Core: повторити аналіз.")


def test_contract_allows_normal_user_facing_response():
    response = "Все добре 🙂 А ти як?"
    assert contains_internal_reasoning_leak(response) is False
    assert validate_specialist_output(_output(response)) == response


def test_contract_rejects_internal_reasoning_leak():
    leaked = "Я — модуль міркування ALTER. Уточнення для Core: підтвердити інтерпретацію."
    assert contains_internal_reasoning_leak(leaked) is True
    try:
        validate_specialist_output(_output(leaked))
    except BotpressInternalLeakError:
        pass
    else:
        raise AssertionError("Internal reasoning leak should have been rejected")


def test_agent_think_repairs_internal_reasoning_once(monkeypatch):
    token = _configure_owner(monkeypatch)
    gateway = RepairingGateway()
    monkeypatch.setattr(agent_api, "gateway", gateway)

    response = TestClient(app).post(
        "/api/agent/think",
        headers=_auth(token),
        json={"objective": "Як. Ти", "context": "Conversation from ALTER web cockpit", "mode": "normal"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "Все добре 🙂 А ти як?"
    assert body["recovered_internal_leak"] is True
    assert len(gateway.calls) == 2
    assert "ORIGINAL USER MESSAGE" in gateway.calls[1]["objective"]


def test_persistent_conversation_repairs_leak_and_never_stores_rejected_draft(monkeypatch):
    token = _configure_owner(monkeypatch)
    gateway = RepairingGateway()
    monkeypatch.setattr(conversation_api, "gateway", gateway)
    client = TestClient(app)

    response = client.post(
        "/api/conversation/respond",
        headers=_auth(token),
        json={"text": "Як. Ти", "mode": "normal"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["agent"]["text"] == "Все добре 🙂 А ти як?"
    assert body["recovered_internal_leak"] is True

    persisted = client.get("/api/conversation", headers=_auth(token)).json()["messages"]
    persisted_text = "\n".join(item["text"] for item in persisted)
    assert "модуль міркування" not in persisted_text.casefold()
    assert "уточнення для core" not in persisted_text.casefold()
    assert persisted[-1]["text"] == "Все добре 🙂 А ти як?"


def test_repair_redacts_full_draft_before_truncation(monkeypatch):
    captured = {}

    def fake_redact(value: str):
        captured["input"] = value
        return "R" * 9_000, True

    class DraftThenCleanGateway:
        def __init__(self):
            self.calls = []

        def think(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return _output("Я — модуль міркування ALTER. " + "X" * 12_000)
            return _output("Готово.")

    gateway = DraftThenCleanGateway()
    monkeypatch.setattr(user_facing_response, "redact_secrets", fake_redact)

    result = user_facing_response.generate_user_facing_response(
        gateway,
        objective="Тест",
        context="",
        mode="normal",
    )

    assert result.text == "Готово."
    assert result.repair_redacted is True
    assert len(captured["input"]) > 8_000
    repair_context = gateway.calls[1]["context"]
    assert repair_context.endswith("R" * 8_000)
    assert "R" * 8_001 not in repair_context


def test_agent_think_fails_closed_when_repair_still_leaks(monkeypatch):
    token = _configure_owner(monkeypatch)
    monkeypatch.setattr(agent_api, "gateway", LeakingGateway())

    response = TestClient(app).post(
        "/api/agent/think",
        headers=_auth(token),
        json={"objective": "Як ти?", "context": "", "mode": "normal"},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "ALTER could not produce a safe user-facing response."


def test_persistent_conversation_fails_closed_without_storing_leak(monkeypatch):
    token = _configure_owner(monkeypatch)
    monkeypatch.setattr(conversation_api, "gateway", LeakingGateway())
    client = TestClient(app)

    response = client.post(
        "/api/conversation/respond",
        headers=_auth(token),
        json={"text": "Як ти?", "mode": "normal"},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "ALTER could not produce a safe user-facing response."
    persisted = client.get("/api/conversation", headers=_auth(token)).json()["messages"]
    assert persisted == []
