from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .botpress_gateway import BotpressGateway
from .openai_agents_gateway import OpenAIAgentsGateway


@dataclass(frozen=True)
class ReasoningGatewayStatus:
    provider: str
    configured: bool
    credential_configured: bool
    action: str
    model: str | None
    bot_id_configured: bool
    available_providers: tuple[str, ...]


class ReasoningGateway:
    """Select a real configured reasoning provider, preferring Agents SDK."""

    def __init__(
        self,
        *,
        openai_gateway: OpenAIAgentsGateway | None = None,
        botpress_gateway: BotpressGateway | None = None,
    ) -> None:
        self.openai = openai_gateway or OpenAIAgentsGateway()
        self.botpress = botpress_gateway or BotpressGateway()

    def _selected(self) -> OpenAIAgentsGateway | BotpressGateway | None:
        if self.openai.status().configured:
            return self.openai
        if self.botpress.status().configured:
            return self.botpress
        return None

    def status(self) -> ReasoningGatewayStatus:
        openai_status = self.openai.status()
        botpress_status = self.botpress.status()
        providers = tuple(
            provider
            for provider, configured in (
                (openai_status.provider, openai_status.configured),
                ("botpress", botpress_status.configured),
            )
            if configured
        )
        if openai_status.configured:
            return ReasoningGatewayStatus(
                provider=openai_status.provider,
                configured=True,
                credential_configured=True,
                action=openai_status.action,
                model=openai_status.model,
                bot_id_configured=botpress_status.bot_id_configured,
                available_providers=providers,
            )
        return ReasoningGatewayStatus(
            provider="botpress",
            configured=botpress_status.configured,
            credential_configured=botpress_status.credential_configured,
            action=botpress_status.action,
            model=None,
            bot_id_configured=botpress_status.bot_id_configured,
            available_providers=providers,
        )

    def think(self, *, objective: str, context: str = "", mode: str = "normal") -> dict[str, Any]:
        selected = self._selected()
        if selected is None:
            # Preserve the existing, well-defined unavailable exception contract.
            return self.botpress.think(objective=objective, context=context, mode=mode)
        return selected.think(objective=objective, context=context, mode=mode)
