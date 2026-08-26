from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from fastapi import Header, HTTPException, status

ActorRole = Literal["owner", "operator", "viewer", "system"]


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UUID
    workspace_id: UUID
    actor_role: ActorRole = "owner"
    actor_id: str = "owner"


def _configured_principal() -> tuple[str, UUID, UUID]:
    token = os.getenv("ALTER_API_TOKEN")
    user_id = os.getenv("ALTER_OWNER_USER_ID")
    workspace_id = os.getenv("ALTER_OWNER_WORKSPACE_ID")
    if not token or not user_id or not workspace_id:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="ALTER owner authentication is not configured.")
    try:
        return token, UUID(user_id), UUID(workspace_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="ALTER owner identity configuration is invalid.") from exc


def system_principal(actor_id: str) -> Principal:
    _token, user_id, workspace_id = _configured_principal()
    return Principal(user_id=user_id, workspace_id=workspace_id, actor_role="system", actor_id=actor_id[:160])


def require_owner(
    authorization: str | None = Header(default=None, alias="Authorization"),
    actor_role: str | None = Header(default=None, alias="X-ALTER-Actor-Role"),
    actor_id: str | None = Header(default=None, alias="X-ALTER-Actor-Id"),
) -> Principal:
    expected_token, user_id, workspace_id = _configured_principal()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer authentication required.", headers={"WWW-Authenticate": "Bearer"})
    supplied_token = authorization.removeprefix("Bearer ").strip()
    if not supplied_token or not secrets.compare_digest(supplied_token, expected_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer credential.", headers={"WWW-Authenticate": "Bearer"})

    # A caller that possesses the Core bearer token may identify an owner/member actor,
    # but may never self-assert the internal system role. System principals are created
    # only by validated internal/OIDC entrypoints.
    role: ActorRole = actor_role if actor_role in {"owner", "operator", "viewer"} else "owner"  # type: ignore[assignment]
    clean_actor = (actor_id or "owner").strip()[:160] or "owner"
    return Principal(user_id=user_id, workspace_id=workspace_id, actor_role=role, actor_id=clean_actor)
