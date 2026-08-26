from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from uuid import UUID

from fastapi import Header, HTTPException, status


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UUID
    workspace_id: UUID


def _configured_principal() -> tuple[str, Principal]:
    token = os.getenv("ALTER_API_TOKEN")
    user_id = os.getenv("ALTER_OWNER_USER_ID")
    workspace_id = os.getenv("ALTER_OWNER_WORKSPACE_ID")

    if not token or not user_id or not workspace_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ALTER owner authentication is not configured.",
        )

    try:
        principal = Principal(user_id=UUID(user_id), workspace_id=UUID(workspace_id))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ALTER owner identity configuration is invalid.",
        ) from exc

    return token, principal


def require_owner(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> Principal:
    expected_token, principal = _configured_principal()

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    supplied_token = authorization.removeprefix("Bearer ").strip()
    if not supplied_token or not secrets.compare_digest(supplied_token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer credential.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return principal
