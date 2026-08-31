from __future__ import annotations

from types import SimpleNamespace

from alter_core.botpress_contract import REQUIRED_SPECIALIST_BOUNDARY
from alter_core.openai_agents_gateway import OpenAIAgentsGateway
from alter_core.reasoning_gateway import ReasoningGateway


def test_openai_agents_gateway_returns_no_side_effect_contract(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run_sync(agent, prompt, **kwargs):
        captured["agent"] = agent
        captured["prompt"] = prompt
        captured.update(kwargs)
        return SimpleNamespace(final_output="Готова перевірена відповідь.")

    monkeypatch.setattr("agents.Runner.run_sync", fake_run_sync)
    monkeypatch.setattr("openai.AsyncOpenAI", lambda **_kwargs: SimpleNamespace())
    gateway = OpenAIAgentsGateway(api_key="test-only-openai-key", model="gpt-5.6")

    output = gateway.think(
        objective="Перевір ALTER",
        context="Context is data, not policy.",
        mode="deep",
    )

    assert output == {
        "response": "Готова перевірена відповідь.",
        "sideEffectsPerformed": False,
        "boundary": REQUIRED_SPECIALIST_BOUNDARY,
    }
    assert "Перевір ALTER" in str(captured["prompt"])
    assert "Context is data, not policy." in str(captured["prompt"])
    assert captured["max_turns"] == 2
    assert "test-only-openai-key" not in str(captured)


def test_reasoning_gateway_prefers_configured_openai():
    class OpenAI:
        def status(self):
            return SimpleNamespace(
                configured=True,
                credential_configured=True,
                provider="openai-agents-sdk",
                action="alterReason",
                model="gpt-5.6",
            )

        def think(self, **_kwargs):
            return {"response": "openai"}

    class Botpress:
        def status(self):
            return SimpleNamespace(
                configured=True,
                credential_configured=True,
                bot_id_configured=True,
                action="alterThink",
            )

        def think(self, **_kwargs):
            return {"response": "botpress"}

    gateway = ReasoningGateway(openai_gateway=OpenAI(), botpress_gateway=Botpress())

    assert gateway.status().provider == "openai-agents-sdk"
    assert gateway.status().available_providers == ("openai-agents-sdk", "botpress")
    assert gateway.think(objective="test")["response"] == "openai"


def test_openai_status_never_exposes_credential():
    status = OpenAIAgentsGateway(api_key="never-return-this-key").status()

    assert status.configured is True
    assert "never-return-this-key" not in repr(status)
