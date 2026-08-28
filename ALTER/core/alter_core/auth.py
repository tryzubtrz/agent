from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from fastapi import Header, HTTPException, Request, status

ActorRole = Literal["owner", "operator", "viewer", "system"]


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UUID
    workspace_id: UUID
    actor_role: ActorRole = "owner"
    actor_id: str = "owner"
    capabilities: tuple[str, ...] = ("*",)

    @property
    def is_owner(self) -> bool:
        return self.actor_role == "owner"


def _configured_principal() -> tuple[str, UUID, UUID]:
    token = os.getenv("ALTER_API_TOKEN")
    user_id = os.getenv("ALTER_OWNER_USER_ID")
    workspace_id = os.getenv("ALTER_OWNER_WORKSPACE_ID")
    if not token or not user_id or not workspace_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ALTER owner authentication is not configured.",
        )
    try:
        return token, UUID(user_id), UUID(workspace_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ALTER owner identity configuration is invalid.",
        ) from exc


def system_principal(actor_id: str) -> Principal:
    _token, user_id, workspace_id = _configured_principal()
    return Principal(
        user_id=user_id,
        workspace_id=workspace_id,
        actor_role="system",
        actor_id=actor_id[:160],
        capabilities=("*",),
    )


def _member_signing_key() -> bytes:
    raw = os.getenv("ALTER_MEMBER_TOKEN_SECRET") or os.getenv("ALTER_API_TOKEN")
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ALTER member-token signing is not configured.",
        )
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64_decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(value + padding)


def issue_member_token(
    *,
    member_id: str,
    user_id: UUID,
    workspace_id: UUID,
    role: Literal["operator", "viewer"],
    capabilities: list[str],
) -> tuple[str, int]:
    try:
        ttl = int(os.getenv("ALTER_MEMBER_TOKEN_TTL_SECONDS", "43200"))
    except ValueError:
        ttl = 43200
    ttl = min(max(ttl, 300), 86400)
    now = int(time.time())
    payload = {
        "v": 1,
        "sub": member_id[:160],
        "uid": str(user_id),
        "wid": str(workspace_id),
        "role": role,
        "cap": sorted({str(item)[:120] for item in capabilities if str(item).strip()}),
        "iat": now,
        "exp": now + ttl,
    }
    encoded = _b64_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_input = f"altm.{encoded}".encode("ascii")
    signature = hmac.new(_member_signing_key(), signing_input, hashlib.sha256).digest()
    return f"altm.{encoded}.{_b64_encode(signature)}", ttl


def _parse_member_token(token: str) -> Principal:
    try:
        prefix, encoded, signature = token.split(".", 2)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid member credential.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if prefix != "altm":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid member credential.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    expected = hmac.new(
        _member_signing_key(),
        f"altm.{encoded}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    try:
        supplied = _b64_decode(signature)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid member credential.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid member credential.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = json.loads(_b64_decode(encoded).decode("utf-8"))
        if payload.get("v") != 1 or int(payload["exp"]) <= int(time.time()):
            raise ValueError("expired")
        role = payload["role"]
        if role not in {"operator", "viewer"}:
            raise ValueError("invalid role")
        capabilities = tuple(
            sorted({str(item) for item in payload.get("cap", []) if str(item).strip()})
        )
        principal = Principal(
            user_id=UUID(str(payload["uid"])),
            workspace_id=UUID(str(payload["wid"])),
            actor_role=role,
            actor_id=str(payload["sub"])[:160],
            capabilities=capabilities,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired member credential.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return _refresh_member_from_database(principal)


def _refresh_member_from_database(principal: Principal) -> Principal:
    """Load live member role/capabilities in production so deactivation is immediate."""
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        return principal
    try:
        from psycopg import connect
        from psycopg.rows import dict_row

        with connect(dsn, row_factory=dict_row) as conn:
            row = conn.execute(
                """
                SELECT value
                FROM memories
                WHERE workspace_id = %s
                  AND user_id = %s
                  AND namespace = 'access.member'
                  AND key = %s
                LIMIT 1
                """,
                (principal.workspace_id, principal.user_id, principal.actor_id),
            ).fetchone()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Member authorization store is unavailable.",
        ) from exc
    if row is None or not isinstance(row.get("value"), dict):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Member credential is no longer active.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    member = row["value"]
    if not member.get("active", False) or member.get("deleted", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Member credential is no longer active.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    role = member.get("role")
    if role not in {"operator", "viewer"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Member role is invalid.")
    capabilities = tuple(
        sorted({str(item) for item in member.get("capabilities", []) if str(item).strip()})
    )
    return Principal(
        user_id=principal.user_id,
        workspace_id=principal.workspace_id,
        actor_role=role,
        actor_id=principal.actor_id,
        capabilities=capabilities,
    )


def _required_capability(method: str, path: str) -> str | None:
    method = method.upper()
    normalized = path.rstrip("/") or "/"

    if normalized == "/api/auth/me":
        return "authenticated"
    if normalized.startswith("/api/access") or normalized.startswith("/api/vault"):
        return None
    if normalized.startswith("/api/audit"):
        return "audit.read"
    if normalized.startswith("/api/connectors"):
        return "connectors.read" if method == "GET" else "connectors.write"
    if normalized.startswith("/api/models") or normalized.startswith("/api/model"):
        return "models.read" if method == "GET" else "models.write"
    if normalized.startswith("/api/memory"):
        return "memory.read" if method == "GET" else "memory.write"
    if normalized.startswith("/tasks") or normalized.startswith("/api/tasks"):
        return "tasks.read" if method == "GET" else "tasks.write"
    if normalized.startswith("/api/agent"):
        return "tasks.write"
    if "conversation" in normalized:
        return "conversation"
    if "document" in normalized:
        return "documents"
    if "knowledge" in normalized or "/api/rag" in normalized:
        return "knowledge"
    if "calendar" in normalized:
        return "calendar.read" if method == "GET" else "calendar"
    if "contact" in normalized:
        return "contacts.read" if method == "GET" else "contacts"
    if "automation" in normalized or "scheduler" in normalized:
        return "automations.read" if method == "GET" else "automations"
    if "notification" in normalized:
        return "notifications.read" if method == "GET" else "notifications"
    return None


def _has_capability(capabilities: tuple[str, ...], required: str) -> bool:
    if required == "authenticated":
        return True
    caps = set(capabilities)
    if "*" in caps or required in caps:
        return True
    if required.endswith(".read"):
        base = required.removesuffix(".read")
        if base in caps or f"{base}.write" in caps:
            return True
    return False


def require_owner(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    actor_role: str | None = Header(default=None, alias="X-ALTER-Actor-Role"),
    actor_id: str | None = Header(default=None, alias="X-ALTER-Actor-Id"),
) -> Principal:
    expected_token, user_id, workspace_id = _configured_principal()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    supplied_token = authorization.removeprefix("Bearer ").strip()
    if not supplied_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer credential.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if secrets.compare_digest(supplied_token, expected_token):
        # Backward-compatible downgrade for trusted callers that already possess
        # the owner credential. It cannot grant more authority than the bearer has.
        # Real delegated members authenticate only with signed altm.* tokens.
        owner_role: ActorRole = (
            actor_role if isinstance(actor_role, str) and actor_role in {"operator", "viewer"} else "owner"
        )
        clean_actor = actor_id.strip()[:160] if isinstance(actor_id, str) and actor_id.strip() else "owner"
        return Principal(
            user_id=user_id,
            workspace_id=workspace_id,
            actor_role=owner_role,
            actor_id=clean_actor,
            capabilities=("*",),
        )

    if not supplied_token.startswith("altm."):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer credential.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    principal = _parse_member_token(supplied_token)
    if principal.user_id != user_id or principal.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Member credential belongs to another workspace.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    required = _required_capability(request.method, request.url.path)
    if required is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner role required for this operation.",
        )
    if not _has_capability(principal.capabilities, required):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing capability: {required}",
        )
    return principal
