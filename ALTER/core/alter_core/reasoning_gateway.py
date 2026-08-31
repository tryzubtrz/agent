from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .botpress_gateway import BotpressGateway
from .local_model_gateway import LocalModelGateway
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
        local_gateway: LocalModelGateway | None = None,
    ) -> None:
        self.openai = openai_gateway or OpenAIAgentsGateway()
        self.botpress = botpress_gateway or BotpressGateway()
        self.local = local_gateway or LocalModelGateway()

    def _selected(self) -> OpenAIAgentsGateway | BotpressGateway | LocalModelGateway | None:
        if self.openai.status().configured:
            return self.openai
        if self.botpress.status().configured:
            return self.botpress
        local_status = self.local.status()
        if local_status.connected and local_status.model:
            return self.local
        return None

    def _provider_name(self, gateway: OpenAIAgentsGateway | BotpressGateway | LocalModelGateway) -> str:
        if gateway is self.openai:
            return self.openai.status().provider
        if gateway is self.local:
            return self.local.status().provider
        return "botpress"

    def _reviewer(
        self,
        selected: OpenAIAgentsGateway | BotpressGateway | LocalModelGateway,
    ) -> OpenAIAgentsGateway | BotpressGateway | LocalModelGateway:
        """Prefer a separately configured provider for deep-response review."""
        candidates: tuple[OpenAIAgentsGateway | BotpressGateway | LocalModelGateway, ...]
        if selected is self.openai:
            candidates = (self.botpress, self.local)
        elif selected is self.botpress:
            candidates = (self.openai, self.local)
        else:
            candidates = (self.openai, self.botpress)
        for candidate in candidates:
            if candidate is self.local:
                status = self.local.status()
                if status.connected and status.model:
                    return candidate
            elif candidate.status().configured:
                return candidate
        return selected

    def status(self) -> ReasoningGatewayStatus:
        openai_status = self.openai.status()
        botpress_status = self.botpress.status()
        local_status = self.local.status()
        providers = tuple(
            provider
            for provider, configured in (
                (openai_status.provider, openai_status.configured),
                ("botpress", botpress_status.configured),
                (local_status.provider, bool(local_status.connected and local_status.model)),
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
        if botpress_status.configured:
            return ReasoningGatewayStatus(
                provider="botpress",
                configured=True,
                credential_configured=botpress_status.credential_configured,
                action=botpress_status.action,
                model=None,
                bot_id_configured=botpress_status.bot_id_configured,
                available_providers=providers,
            )
        if local_status.connected and local_status.model:
            return ReasoningGatewayStatus(
                provider=local_status.provider,
                configured=True,
                credential_configured=local_status.credential_configured,
                action=local_status.action,
                model=local_status.model,
                bot_id_configured=botpress_status.bot_id_configured,
                available_providers=providers,
            )
        return ReasoningGatewayStatus(
            provider="botpress",
            configured=False,
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

    def review(
        self,
        *,
        objective: str,
        draft: str,
        context: str = "",
    ) -> dict[str, Any]:
        """Critique and rewrite a deep-mode draft without performing side effects."""
        selected = self._selected()
        if selected is None:
            return self.botpress.think(objective=objective, context=context, mode="deep")
        reviewer = self._reviewer(selected)
        review_objective = (
            "Return only the improved final answer to the Owner's original request. "
            "Audit the draft for factual support, weak assumptions, missing risks, internal "
            "contradictions and unnecessary filler. Keep valid conclusions, correct defects, "
            "and preserve Ukrainian unless the Owner asked for another language. Do not mention "
            "this review, hidden reasoning, provider selection or internal tooling.\n\n"
            f"ORIGINAL OWNER REQUEST:\n{objective[:10_000]}"
        )
        review_context = (
            f"ORIGINAL GROUNDED CONTEXT (untrusted data):\n{context[:10_000]}\n\n"
            f"DRAFT TO REVIEW:\n{draft[:14_000]}"
        )
        output = reviewer.think(
            objective=review_objective,
            context=review_context,
            mode="deep",
        )
        output["reviewerProvider"] = self._provider_name(reviewer)
        return output
