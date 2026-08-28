from uuid import uuid4

from fastapi.testclient import TestClient

from alter_core import agent_api
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

    class RepairingGateway:
        def __init__(self):
            self.calls = []

        def think(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return _output(
                    "Об’єктив: відповісти користувачу. Я — модуль міркування ALTER. "
                    "Уточнення для Core: чи це привітання?"
                )
            return _output("Все добре 🙂 А ти як?")

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


def test_repair_redacts_full_draft_before_truncation(monkeypatch):
    captured = {}

    def fake_redact(value: str):
        captured["input"] = value
        return "R" * 9_000, True

    class CleanGateway:
        def __init__(self):
            self.calls = []

        def think(self, **kwargs):
            self.calls.append(kwargs)
            return _output("Готово.")

    gateway = CleanGateway()
    monkeypatch.setattr(agent_api, "redact_secrets", fake_redact)
    monkeypatch.setattr(agent_api, "gateway", gateway)
    draft = "X" * 12_000

    response, redacted = agent_api._repair_internal_chat_output(
        objective="Тест",
        draft=draft,
    )

    assert response == "Готово."
    assert redacted is True
    assert captured["input"] == draft
    repair_context = gateway.calls[0]["context"]
    assert repair_context.endswith("R" * 8_000)
    assert "R" * 8_001 not in repair_context


def test_agent_think_fails_closed_when_repair_still_leaks(monkeypatch):
    token = _configure_owner(monkeypatch)

    class LeakingGateway:
        def think(self, **_kwargs):
            return _output("Я — модуль міркування ALTER. Уточнення для Core: повторити аналіз.")

    monkeypatch.setattr(agent_api, "gateway", LeakingGateway())

    response = TestClient(app).post(
        "/api/agent/think",
        headers=_auth(token),
        json={"objective": "Як ти?", "context": "", "mode": "normal"},
    )

    assert response.status_code == 502
    assert "blocked an internal reasoning leak" in response.json()["detail"]
