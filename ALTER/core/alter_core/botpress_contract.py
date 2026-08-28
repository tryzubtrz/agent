from __future__ import annotations

from typing import Any, Literal

REQUIRED_SPECIALIST_BOUNDARY = "core-policy-required"
MAX_SPECIALIST_TEXT_LENGTH = 50_000

# Strong, user-inappropriate markers that indicate the specialist returned
# internal orchestration/scratchpad text instead of a final chat answer.
# Keep this list narrow to avoid blocking legitimate technical discussion.
_INTERNAL_REASONING_MARKERS = (
    "уточнення для core",
    "я — модуль міркування alter",
    "я - модуль міркування alter",
    "notes for core",
    "redacted context:",
    "tools were not invoked",
    "інструменти/виконавці не викликані",
)


class BotpressContractError(ValueError):
    pass


class BotpressInternalLeakError(BotpressContractError):
    """Raised when a user-facing response contains internal reasoning markers."""


def contains_internal_reasoning_leak(text: str) -> bool:
    normalized = text.casefold()
    return any(marker in normalized for marker in _INTERNAL_REASONING_MARKERS)


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
    if content_kind == "response" and contains_internal_reasoning_leak(cleaned):
        raise BotpressInternalLeakError(
            "Botpress specialist returned internal reasoning instead of a user-facing response."
        )
    return cleaned
