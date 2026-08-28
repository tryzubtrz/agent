from __future__ import annotations

from dataclasses import dataclass

from .botpress_contract import BotpressInternalLeakError, validate_specialist_output
from .botpress_gateway import BotpressGateway
from .secret_safety import redact_secrets


@dataclass(frozen=True)
class UserFacingResponse:
    text: str
    recovered_internal_leak: bool = False
    repair_redacted: bool = False


def generate_user_facing_response(
    gateway: BotpressGateway,
    *,
    objective: str,
    context: str = "",
    mode: str = "normal",
) -> UserFacingResponse:
    """Generate one final user-facing response with one safe repair attempt.

    Botpress remains a reasoning specialist, but this boundary is shared by every
    ALTER chat surface. If a draft contains known internal orchestration markers,
    it is never returned directly to the user. The rejected draft is fully
    secret-redacted before it is truncated and sent for a single rewrite.
    """
    output = gateway.think(objective=objective, context=context, mode=mode)
    try:
        return UserFacingResponse(text=validate_specialist_output(output))
    except BotpressInternalLeakError:
        raw_draft = output.get("response")
        draft = raw_draft if isinstance(raw_draft, str) else ""
        safe_draft, draft_redacted = redact_secrets(draft)
        safe_draft = safe_draft[:8_000]

        repair_objective = (
            "Answer the user's original message directly and naturally. "
            "The previous draft was rejected because it exposed internal ALTER reasoning. "
            "Return only the final user-facing answer. Do not mention Core, orchestration, "
            "preflight, hidden reasoning, tools not being invoked, redacted context, or the repair.\n\n"
            f"ORIGINAL USER MESSAGE:\n{objective}"
        )
        repair_context = f"REJECTED DRAFT (rewrite, do not describe):\n{safe_draft}"
        repaired_output = gateway.think(
            objective=repair_objective,
            context=repair_context,
            mode="quick",
        )
        repaired = validate_specialist_output(repaired_output)
        return UserFacingResponse(
            text=repaired,
            recovered_internal_leak=True,
            repair_redacted=draft_redacted,
        )
