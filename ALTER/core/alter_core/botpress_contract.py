from __future__ import annotations

from typing import Any, Literal

REQUIRED_SPECIALIST_BOUNDARY = "core-policy-required"
MAX_SPECIALIST_TEXT_LENGTH = 50_000


class BotpressContractError(ValueError):
    pass


def validate_specialist_output(
    output: dict[str, Any],
    *,
    content_kind: Literal["response", "plan"] = "response",
) -> str:
    """Validate the shared no-side-effect Botpress response contract."""
    if output.get("sideEffectsPerformed") is not False:
        raise BotpressContractError(
            "ALTER specialist violated the no-side-effect response contract."
        )
    if output.get("boundary") != REQUIRED_SPECIALIST_BOUNDARY:
        raise BotpressContractError(
            "ALTER specialist returned an invalid execution boundary."
        )
    response = output.get("response")
    if not isinstance(response, str) or not response.strip():
        raise BotpressContractError(
            f"Botpress specialist returned no usable {content_kind}."
        )
    cleaned = response.strip()
    if len(cleaned) > MAX_SPECIALIST_TEXT_LENGTH:
        raise BotpressContractError(
            f"Botpress specialist returned an oversized {content_kind}."
        )
    return cleaned
