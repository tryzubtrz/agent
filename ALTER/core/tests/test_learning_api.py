from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from alter_core import conversation_api
from api.index import app


def configure_owner(monkeypatch):
    token = "test-owner-token-learning"
    monkeypatch.setenv("ALTER_API_TOKEN", token)
    monkeypatch.setenv("ALTER_OWNER_USER_ID", str(uuid4()))
    monkeypatch.setenv("ALTER_OWNER_WORKSPACE_ID", str(uuid4()))
    monkeypatch.delenv("ALTER_MODEL_RUNTIME_URL", raising=False)
    monkeypatch.delenv("ALTER_MODEL_RUNTIME_TOKEN", raising=False)
    return token


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class CapturingGateway:
    def __init__(self):
        self.calls = []

    def status(self):
        return SimpleNamespace(configured=True, provider="test-reasoner")

    def think(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "response": "Зрозумів. Це моя аргументована відповідь.",
            "sideEffectsPerformed": False,
            "boundary": "core-policy-required",
        }


def test_conversation_queues_but_does_not_auto_commit_durable_fact(monkeypatch):
    token = configure_owner(monkeypatch)
    gateway = CapturingGateway()
    monkeypatch.setattr(conversation_api, "gateway", gateway)
    client = TestClient(app)

    response = client.post(
        "/api/conversation/respond",
        headers=auth(token),
        json={"text": "Я люблю малинові десерти, але не дуже солодкі.", "mode": "normal"},
    )
    assert response.status_code == 200
    assert response.json()["learning_candidates"] == 1

    candidates = client.get("/api/learning/candidates", headers=auth(token))
    assert candidates.status_code == 200
    assert len(candidates.json()) == 1
    candidate = candidates.json()[0]
    assert candidate["kind"] == "preference"

    before = client.get("/api/memory/items", headers=auth(token)).json()
    assert all(item.get("content") != candidate["content"] for item in before["items"])

    approved = client.post(
        f"/api/learning/candidates/{candidate['id']}/approve",
        headers=auth(token),
        json={"kind": "preference", "importance": 0.9},
    )
    assert approved.status_code == 200
    after = client.get("/api/memory/items", headers=auth(token)).json()
    assert any(item.get("content") == candidate["content"] for item in after["items"])


def test_lessons_triggers_and_preferences_are_injected_as_context(monkeypatch):
    token = configure_owner(monkeypatch)
    gateway = CapturingGateway()
    monkeypatch.setattr(conversation_api, "gateway", gateway)
    client = TestClient(app)

    assert client.post(
        "/api/learning/lessons",
        headers=auth(token),
        json={"situation": "Коли оцінюєш інвестицію", "lesson": "Назви ризик і не обіцяй гарантований прибуток", "tags": ["finance"]},
    ).status_code == 200
    assert client.post(
        "/api/learning/triggers",
        headers=auth(token),
        json={"when": "інвестиція в криптовалюту", "then": "порівняй максимальну просадку і ліквідність", "active": True},
    ).status_code == 200
    assert client.put(
        "/api/learning/preferences",
        headers=auth(token),
        json={"tone": "прямий і критичний", "length": "стисло", "language": "українська", "notes": "без зайвої води"},
    ).status_code == 200

    response = client.post(
        "/api/conversation/respond",
        headers=auth(token),
        json={"text": "Оціни інвестицію в криптовалюту", "mode": "normal"},
    )
    assert response.status_code == 200
    context = gateway.calls[-1]["context"]
    assert "прямий і критичний" in context
    assert "не обіцяй гарантований прибуток" in context
    assert "порівняй максимальну просадку" in context
    assert "learning.context" in {item["tool"] for item in response.json()["grounding"]}


def test_deep_mode_uses_optional_evaluator_and_keeps_no_side_effect_boundary(monkeypatch):
    token = configure_owner(monkeypatch)

    class ReviewedGateway(CapturingGateway):
        def review(self, **kwargs):
            self.calls.append({"review": kwargs})
            return {
                "response": "Перевірена фінальна відповідь з чітким висновком.",
                "sideEffectsPerformed": False,
                "boundary": "core-policy-required",
                "reviewerProvider": "independent-critic",
            }

    gateway = ReviewedGateway()
    monkeypatch.setattr(conversation_api, "gateway", gateway)
    response = TestClient(app).post(
        "/api/conversation/respond",
        headers=auth(token),
        json={"text": "Дай глибоку оцінку плану", "mode": "deep"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["reviewed"] is True
    assert body["reviewer_provider"] == "independent-critic"
    assert body["agent"]["text"].startswith("Перевірена")
    assert body["side_effects_performed"] is False
