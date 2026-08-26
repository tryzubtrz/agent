from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .api import _audit, _memory_fallback, memory_store
from .auth import Principal, require_owner

router = APIRouter()

Role = Literal["operator", "viewer"]
_DEFAULT_CAPABILITIES: dict[str, list[str]] = {
    "operator": ["tasks.read", "tasks.write", "conversation", "documents", "knowledge", "calendar", "contacts", "automations", "notifications"],
    "viewer": ["tasks.read", "memory.read", "audit.read", "connectors.read", "models.read", "knowledge", "calendar.read", "contacts.read", "notifications.read"],
}


class InviteBody(BaseModel):
    label: str = Field(min_length=1, max_length=160)
    role: Role = "viewer"
    capabilities: list[str] = Field(default_factory=list, max_length=50)
    expires_hours: int = Field(default=72, ge=1, le=24 * 30)


class RedeemBody(BaseModel):
    code: str = Field(min_length=20, max_length=300)


def _rows(principal: Principal, namespace: str) -> list[dict[str, Any]]:
    if memory_store is not None:
        return memory_store.list_for_user(workspace_id=principal.workspace_id, user_id=principal.user_id, namespace=namespace, limit=250)
    return [
        {"namespace": ns, "key": key, "value": value}
        for (workspace_id, user_id, ns, key), value in _memory_fallback.items()
        if workspace_id == principal.workspace_id and user_id == principal.user_id and ns == namespace
    ][:250]


def _put(principal: Principal, namespace: str, key: str, value: dict[str, Any]) -> None:
    if memory_store is not None:
        memory_store.upsert(workspace_id=principal.workspace_id, user_id=principal.user_id, namespace=namespace, key=key, value=value)
    else:
        _memory_fallback[(principal.workspace_id, principal.user_id, namespace, key)] = value


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


@router.get("/api/access/members")
def list_members(principal: Principal = Depends(require_owner)) -> list[dict[str, Any]]:
    members: list[dict[str, Any]] = []
    for row in _rows(principal, "access.member"):
        value = row.get("value")
        if isinstance(value, dict) and not value.get("deleted"):
            members.append({**value, "code_hash": None})
    members.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return members


@router.get("/api/access/invites")
def list_invites(principal: Principal = Depends(require_owner)) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in _rows(principal, "access.invite"):
        value = row.get("value")
        if not isinstance(value, dict) or value.get("deleted"):
            continue
        output.append({key: item for key, item in value.items() if key != "code_hash"})
    output.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return output


@router.post("/api/access/invites")
def create_invite(body: InviteBody, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    invite_id = str(uuid4())
    raw_code = f"alt_{secrets.token_urlsafe(30)}"
    now = datetime.now(timezone.utc)
    capabilities = sorted(set(body.capabilities or _DEFAULT_CAPABILITIES[body.role]))
    value = {
        "id": invite_id,
        "label": body.label.strip(),
        "role": body.role,
        "capabilities": capabilities,
        "code_hash": _hash(raw_code),
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=body.expires_hours)).isoformat(),
        "redeemed_at": None,
        "revoked": False,
        "deleted": False,
    }
    _put(principal, "access.invite", invite_id, value)
    _audit(principal, event_type="access.invite.created", payload={"invite_id": invite_id, "role": body.role, "capability_count": len(capabilities)})
    return {
        "id": invite_id,
        "label": value["label"],
        "role": body.role,
        "capabilities": capabilities,
        "expires_at": value["expires_at"],
        "code": raw_code,
        "code_shown_once": True,
    }


@router.post("/api/access/redeem")
def redeem_invite(body: RedeemBody, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    digest = _hash(body.code.strip())
    now = datetime.now(timezone.utc)
    match: tuple[str, dict[str, Any]] | None = None
    for row in _rows(principal, "access.invite"):
        value = row.get("value")
        if isinstance(value, dict) and secrets.compare_digest(str(value.get("code_hash") or ""), digest):
            match = (str(row.get("key")), value)
            break
    if match is None:
        raise HTTPException(status_code=401, detail="Invalid invitation code")
    invite_id, invite = match
    if invite.get("revoked") or invite.get("redeemed_at"):
        raise HTTPException(status_code=409, detail="Invitation is no longer active")
    try:
        expires_at = datetime.fromisoformat(str(invite["expires_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="Invitation metadata is invalid") from exc
    if expires_at <= now:
        raise HTTPException(status_code=410, detail="Invitation has expired")

    member_id = str(uuid4())
    member = {
        "id": member_id,
        "label": invite.get("label") or "Member",
        "role": invite.get("role") or "viewer",
        "capabilities": invite.get("capabilities") or [],
        "active": True,
        "created_at": now.isoformat(),
        "last_login_at": now.isoformat(),
        "invite_id": invite_id,
        "deleted": False,
    }
    invite = dict(invite)
    invite["redeemed_at"] = now.isoformat()
    _put(principal, "access.invite", invite_id, invite)
    _put(principal, "access.member", member_id, member)
    _audit(principal, event_type="access.invite.redeemed", payload={"invite_id": invite_id, "member_id": member_id, "role": member["role"]})
    return member


@router.post("/api/access/members/{member_id}/deactivate")
def deactivate_member(member_id: str, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    row = next((item for item in _rows(principal, "access.member") if str(item.get("key")) == member_id), None)
    if row is None or not isinstance(row.get("value"), dict):
        raise HTTPException(status_code=404, detail="Member not found")
    value = dict(row["value"])
    value["active"] = False
    value["deactivated_at"] = datetime.now(timezone.utc).isoformat()
    _put(principal, "access.member", member_id, value)
    _audit(principal, event_type="access.member.deactivated", payload={"member_id": member_id})
    return {"id": member_id, "active": False}


@router.get("/api/access/members/{member_id}")
def member_status(member_id: str, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    row = next((item for item in _rows(principal, "access.member") if str(item.get("key")) == member_id), None)
    if row is None or not isinstance(row.get("value"), dict):
        raise HTTPException(status_code=404, detail="Member not found")
    value = row["value"]
    return {key: item for key, item in value.items() if key not in {"code_hash"}}
