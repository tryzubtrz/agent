from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from psycopg import connect
from pydantic import BaseModel, Field

from .api import _audit, policy_store
from .auth import Principal, require_owner
from .models import PolicyEffect, PolicyRule

router = APIRouter()


class PolicyPatchBody(BaseModel):
    original_text: str | None = Field(default=None, min_length=1, max_length=2000)
    category: str | None = Field(default=None, min_length=1, max_length=200)
    effect: PolicyEffect | None = None
    priority: int | None = Field(default=None, ge=0, le=10000)
    enabled: bool | None = None


def _get(rule_id: UUID, principal: Principal) -> PolicyRule:
    rule = next((item for item in policy_store.list_for_workspace(principal.workspace_id) if item.id == rule_id), None)
    if rule is None:
        raise HTTPException(status_code=404, detail="Policy rule not found")
    return rule


@router.patch("/api/policies/{rule_id}")
def patch_policy(rule_id: UUID, body: PolicyPatchBody, principal: Principal = Depends(require_owner)) -> PolicyRule:
    rule = _get(rule_id, principal)
    values = body.model_dump(exclude_none=True)
    updated = rule.model_copy(update=values)
    saved = policy_store.add(updated)
    _audit(
        principal,
        event_type="policy.updated",
        payload={"rule_id": str(rule_id), "fields": sorted(values.keys()), "enabled": saved.enabled},
    )
    return saved


@router.delete("/api/policies/{rule_id}")
def delete_policy(rule_id: UUID, principal: Principal = Depends(require_owner)) -> dict[str, object]:
    _get(rule_id, principal)
    deleted = False
    delete_method = getattr(policy_store, "delete", None)
    if callable(delete_method):
        deleted = bool(delete_method(principal.workspace_id, rule_id))
    else:
        dsn = getattr(policy_store, "dsn", None)
        if not dsn:
            raise HTTPException(status_code=503, detail="Policy deletion backend is unavailable")
        with connect(dsn) as conn:
            result = conn.execute(
                "DELETE FROM policy_rules WHERE workspace_id = %s AND id = %s",
                (principal.workspace_id, rule_id),
            )
            deleted = result.rowcount > 0
    if not deleted:
        raise HTTPException(status_code=404, detail="Policy rule not found")
    _audit(principal, event_type="policy.deleted", payload={"rule_id": str(rule_id)})
    return {"deleted": True, "rule_id": str(rule_id)}
