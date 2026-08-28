from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .access_api import _hash, _invite_redeem_lock, _redeem_values
from .api import _audit, _memory_fallback, memory_store
from .auth import Principal, issue_member_token, require_owner, system_principal
from .persistence import PostgresMemoryStore

router = APIRouter()


class RedeemInviteBody(BaseModel):
    code: str = Field(min_length=20, max_length=300)


def _public_member(member: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in member.items()
        if key not in {"code_hash", "deleted"}
    }


@router.post("/api/auth/redeem-invite")
def redeem_invite(body: RedeemInviteBody) -> dict[str, Any]:
    # The one-time invite code is the credential for this endpoint; requiring the
    # owner bearer here would make delegated membership impossible to bootstrap.
    code = body.code.strip()
    principal = system_principal("access.redeem")
    digest = _hash(code)
    now = datetime.now(timezone.utc)

    if memory_store is not None:
        if not isinstance(memory_store, PostgresMemoryStore):
            raise HTTPException(status_code=503, detail="Atomic invitation storage is unavailable")
        member = memory_store.redeem_invite(
            workspace_id=principal.workspace_id,
            user_id=principal.user_id,
            code_hash=digest,
            transition=lambda invite_id, invite: _redeem_values(invite_id, invite, now=now),
        )
        if member is None:
            raise HTTPException(status_code=401, detail="Invalid invitation code")
    else:
        with _invite_redeem_lock:
            match: tuple[str, dict[str, Any]] | None = None
            for (workspace_id, user_id, namespace, key), value in _memory_fallback.items():
                if (
                    workspace_id == principal.workspace_id
                    and user_id == principal.user_id
                    and namespace == "access.invite"
                    and isinstance(value, dict)
                    and secrets.compare_digest(str(value.get("code_hash") or ""), digest)
                ):
                    match = (key, value)
                    break
            if match is None:
                raise HTTPException(status_code=401, detail="Invalid invitation code")
            invite_id, invite = match
            updated_invite, member = _redeem_values(invite_id, invite, now=now)
            _memory_fallback[(principal.workspace_id, principal.user_id, "access.invite", invite_id)] = updated_invite
            _memory_fallback[(principal.workspace_id, principal.user_id, "access.member", str(member["id"]))] = member

    role = member.get("role")
    if role not in {"operator", "viewer"}:
        raise HTTPException(status_code=409, detail="Invitation role is invalid")
    token, ttl = issue_member_token(
        member_id=str(member["id"]),
        user_id=principal.user_id,
        workspace_id=principal.workspace_id,
        role=role,
        capabilities=[str(item) for item in member.get("capabilities", [])],
    )
    _audit(
        principal,
        event_type="access.member.session_issued",
        payload={
            "invite_id": str(member["invite_id"]),
            "member_id": str(member["id"]),
            "role": role,
            "capability_count": len(member.get("capabilities", [])),
            "ttl_seconds": ttl,
        },
    )
    return {
        "member": _public_member(member),
        "access_token": token,
        "token_type": "bearer",
        "expires_in": ttl,
    }


@router.get("/api/auth/me")
def current_principal(principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    return {
        "user_id": str(principal.user_id),
        "workspace_id": str(principal.workspace_id),
        "actor_role": principal.actor_role,
        "actor_id": principal.actor_id,
        "capabilities": list(principal.capabilities),
    }
