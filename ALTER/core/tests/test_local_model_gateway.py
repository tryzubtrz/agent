from __future__ import annotations

import json
from io import BytesIO

import pytest

from alter_core import local_model_gateway as module
from alter_core.local_model_gateway import LocalModelGateway, LocalModelUnavailableError


class Response(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def test_local_runtime_status_and_reasoning_contract(monkeypatch):
    def fake_urlopen(request, timeout):
        assert request.headers["Authorization"] == "Bearer test-runtime-token"
        if request.full_url.endswith("/health"):
            payload = {
                "status": "ok",
                "installed_models": ["qwen3-8b", "not-allowlisted"],
                "active_jobs": 1,
            }
        else:
            payload = {"response": "Незалежний локальний висновок."}
        return Response(json.dumps(payload).encode())

    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    gateway = LocalModelGateway(
        base_url="https://models.example.test",
        token="test-runtime-token",
        default_model="qwen3-8b",
    )

    status = gateway.status()
    assert status.connected is True
    assert status.installed_models == ("qwen3-8b",)
    assert status.active_jobs == 1
    assert gateway.think(objective="Оціни ризик") == {
        "response": "Незалежний локальний висновок.",
        "sideEffectsPerformed": False,
        "boundary": "core-policy-required",
    }


def test_local_runtime_rejects_plaintext_public_url():
    gateway = LocalModelGateway(base_url="http://models.example.test", token="token")
    assert gateway.status().configured is False
    with pytest.raises(LocalModelUnavailableError):
        gateway.start_install(model_id="qwen3-8b", approval_digest="a" * 64)


def test_local_runtime_install_uses_allowlist_and_approval_digest(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode())
        return Response(json.dumps({
            "job_id": "job-1",
            "state": "queued",
            "model_id": "qwen3-8b",
            "secret_exposed": False,
        }).encode())

    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    gateway = LocalModelGateway(base_url="https://models.example.test", token="token")
    result = gateway.start_install(model_id="qwen3-8b", approval_digest="b" * 64)

    assert captured["url"].endswith("/v1/models/qwen3-8b/pull")
    assert captured["body"] == {"approval_digest": "b" * 64}
    assert result["secret_exposed"] is False
