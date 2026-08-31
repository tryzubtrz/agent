from __future__ import annotations

from fastapi.testclient import TestClient

from alter_model_runtime import app as module


def _auth() -> dict[str, str]:
    return {"Authorization": "Bearer runtime-test-token"}


def test_runtime_requires_auth_and_rejects_arbitrary_model(monkeypatch):
    monkeypatch.setenv("ALTER_MODEL_RUNTIME_TOKEN", "runtime-test-token")
    client = TestClient(module.app)

    assert client.get("/health").status_code == 401
    response = client.post(
        "/v1/models/arbitrary-shell-model/pull",
        headers=_auth(),
        json={"approval_digest": "a" * 64},
    )
    assert response.status_code == 404


def test_runtime_reports_installed_allowlisted_models_only(monkeypatch):
    monkeypatch.setenv("ALTER_MODEL_RUNTIME_TOKEN", "runtime-test-token")
    monkeypatch.setattr(module, "_installed_ids", lambda: ["qwen3-8b"])
    client = TestClient(module.app)

    response = client.get("/health", headers=_auth())
    assert response.status_code == 200
    assert response.json()["installed_models"] == ["qwen3-8b"]
    assert response.json()["arbitrary_install"] is False


def test_runtime_chat_preserves_no_side_effect_contract(monkeypatch):
    monkeypatch.setenv("ALTER_MODEL_RUNTIME_TOKEN", "runtime-test-token")
    monkeypatch.setattr(module, "_installed_ids", lambda: ["qwen3-8b"])
    monkeypatch.setattr(
        module,
        "_ollama",
        lambda *args, **kwargs: {"message": {"content": "Перевірений локальний висновок."}},
    )
    client = TestClient(module.app)

    response = client.post(
        "/v1/chat",
        headers=_auth(),
        json={"model_id": "qwen3-8b", "objective": "Оціни план", "mode": "deep"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["response"] == "Перевірений локальний висновок."
    assert response.json()["side_effects_performed"] is False
    assert response.json()["secret_exposed"] is False
