from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .api import _audit, _memory_fallback, memory_store
from .auth import Principal, require_owner
from .botpress_gateway import BotpressGateway, BotpressRuntimeError, BotpressUnavailableError

router = APIRouter()
gateway = BotpressGateway()

_MAX_MESSAGES = 60
_CONTEXT_MESSAGES = 16
_REQUIRED_SPECIALIST_BOUNDARY = "core-policy-required"

_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"(?s)-----BEGIN ([A-Z0-9 ]*PRIVATE KEY)-----.*?-----END \1-----"),
        "[REDACTED_PRIVATE_KEY]",
    ),
    (
        re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^:\s/@]+:)([^@\s/]+)(@)"),
        r"\1[REDACTED]\3",
    ),
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
        "[REDACTED_JWT]",
    ),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/=]{8,}"), "Bearer [REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\b(?:bp|bpt|botpress)_[A-Za-z0-9_-]{16,}\b", re.IGNORECASE), "[REDACTED_BOTPRESS_TOKEN]"),
    (
        re.compile(
            r"(?i)\b(api[_ -]?key|access[_ -]?token|refresh[_ -]?token|auth(?:orization)?|password|passwd|secret|cookie|session[_ -]?token|pat)\s*[:=]\s*([^\s,;]{6,})"
        ),
        r"\1=[REDACTED]",
    ),
)


class AppendMessageBody(BaseModel):
    role: Literal["user", "agent"]
    text: str = Field(min_length=1, max_length=10_000)


class ChatBody(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)
    mode: Literal["quick", "normal", "deep", "plan"] = "normal"


def _redact(text: str) -> tuple[str, bool]:
    safe = text
    changed = False
    for pattern, replacement in _SECRET_PATTERNS:
        updated = pattern.sub(replacement, safe)
        if updated != safe:
            changed = True
            safe = updated
    return safe, changed


def _load_messages(principal: Principal) -> list[dict[str, Any]]:
    value: Any = None
    if memory_store is not None:
        rows = memory_store.list_for_user(
            workspace_id=principal.workspace_id,
            user_id=principal.user_id,
            namespace="conversation",
            limit=10,
        )
        for row in rows:
            if row.get("key") == "main":
                value = row.get("value")
                break
    else:
        value = _memory_fallback.get(
            (principal.workspace_id, principal.user_id, "conversation", "main")
        )

    if not isinstance(value, dict):
        return []
    messages = value.get("messages")
    if not isinstance(messages, list):
        return []

    clean: list[dict[str, Any]] = []
    for item in messages[-_MAX_MESSAGES:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        text = item.get("text")
        if role not in {"user", "agent"} or not isinstance(text, str):
            continue
        clean.append(
            {
                "role": role,
                "text": text,
                "created_at": item.get("created_at"),
                "redacted": bool(item.get("redacted", False)),
            }
        )
    return clean


def _save_messages(principal: Principal, messages: list[dict[str, Any]]) -> None:
    value = {"messages": messages[-_MAX_MESSAGES:]}
    if memory_store is not None:
        memory_store.upsert(
            workspace_id=principal.workspace_id,
            user_id=principal.user_id,
            namespace="conversation",
            key="main",
            value=value,
        )
    else:
        _memory_fallback[
            (principal.workspace_id, principal.user_id, "conversation", "main")
        ] = value


def _append_message(
    principal: Principal,
    *,
    role: Literal["user", "agent"],
    text: str,
) -> dict[str, Any]:
    safe_text, redacted = _redact(text.strip())
    item = {
        "role": role,
        "text": safe_text,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "redacted": redacted,
    }
    messages = _load_messages(principal)
    messages.append(item)
    _save_messages(principal, messages)
    _audit(
        principal,
        event_type="conversation.updated",
        payload={
            "role": role,
            "message_count": len(messages[-_MAX_MESSAGES:]),
            "redacted": redacted,
        },
    )
    return item


def _context(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for message in messages[-_CONTEXT_MESSAGES:]:
        speaker = "Owner" if message.get("role") == "user" else "ALTER"
        text = str(message.get("text", "")).strip()
        if text:
            lines.append(f"{speaker}: {text}")
    return "\n".join(lines)


@router.get("/conversation")
@router.get("/api/conversation")
def get_conversation(
    limit: int = Query(default=60, ge=1, le=_MAX_MESSAGES),
    principal: Principal = Depends(require_owner),
) -> dict[str, Any]:
    messages = _load_messages(principal)[-limit:]
    return {"messages": messages, "count": len(messages), "persistent": True}


@router.post("/conversation/messages")
@router.post("/api/conversation/messages")
def append_conversation_message(
    body: AppendMessageBody,
    principal: Principal = Depends(require_owner),
) -> dict[str, Any]:
    return _append_message(principal, role=body.role, text=body.text)


@router.post("/conversation/respond")
@router.post("/api/conversation/respond")
def respond_in_conversation(
    body: ChatBody,
    principal: Principal = Depends(require_owner),
) -> dict[str, Any]:
    if not gateway.status().configured:
        raise HTTPException(
            status_code=503,
            detail="ALTER AI runtime credential is not configured in Core.",
        )

    safe_owner_text, owner_redacted = _redact(body.text.strip())
    existing = _load_messages(principal)
    context = _context(existing)

    try:
        output = gateway.think(
            objective=safe_owner_text,
            context=context,
            mode=body.mode,
        )
    except BotpressUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BotpressRuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if output.get("sideEffectsPerformed") is not False:
        raise HTTPException(
            status_code=502,
            detail="ALTER specialist violated the no-side-effect response contract.",
        )
    if output.get("boundary") != _REQUIRED_SPECIALIST_BOUNDARY:
        raise HTTPException(
            status_code=502,
            detail="ALTER specialist returned an invalid execution boundary.",
        )

    response = output.get("response")
    if not isinstance(response, str) or not response.strip():
        raise HTTPException(status_code=502, detail="ALTER specialist returned no usable response.")

    owner_message = {
        "role": "user",
        "text": safe_owner_text,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "redacted": owner_redacted,
    }
    safe_response, response_redacted = _redact(response.strip())
    agent_message = {
        "role": "agent",
        "text": safe_response,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "redacted": response_redacted,
    }

    updated = [*existing, owner_message, agent_message][-_MAX_MESSAGES:]
    _save_messages(principal, updated)
    _audit(
        principal,
        event_type="conversation.responded",
        payload={
            "provider": "botpress",
            "message_count": len(updated),
            "owner_message_redacted": owner_redacted,
            "agent_message_redacted": response_redacted,
            "boundary": _REQUIRED_SPECIALIST_BOUNDARY,
        },
    )

    return {
        "provider": "botpress",
        "user": owner_message,
        "agent": agent_message,
        "persistent": True,
        "side_effects_performed": False,
        "boundary": _REQUIRED_SPECIALIST_BOUNDARY,
    }


@router.post("/conversation/clear")
@router.post("/api/conversation/clear")
def clear_conversation(
    principal: Principal = Depends(require_owner),
) -> dict[str, object]:
    _save_messages(principal, [])
    _audit(
        principal,
        event_type="conversation.cleared",
        payload={"message_count": 0},
    )
    return {"cleared": True, "message_count": 0}
