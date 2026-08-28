from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import connect
from pydantic import BaseModel, Field

from .api import _audit, _memory_fallback, memory_store
from .auth import Principal, require_owner
from .secret_safety import contains_high_confidence_secret

router = APIRouter()
_NAMESPACE = "memory.typed"

MemoryKind = Literal["preference", "fact", "decision", "context"]


class MemoryItemBody(BaseModel):
    key: str | None = Field(default=None, min_length=1, max_length=160)
    kind: MemoryKind
    content: str = Field(min_length=1, max_length=20_000)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list, max_length=20)
    source: str = Field(default="owner", min_length=1, max_length=120)
    expires_at: datetime | None = None


def _normalize_tags(tags: list[str]) -> list[str]:
    clean: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        value = re.sub(r"\s+", " ", str(tag).strip())[:60]
        if value and value.lower() not in seen:
            seen.add(value.lower())
            clean.append(value)
    return clean[:20]


def _key(body: MemoryItemBody) -> str:
    if body.key:
        return re.sub(r"[^A-Za-z0-9._:-]+", "-", body.key.strip())[:160]
    normalized = re.sub(r"\s+", " ", body.content.strip().lower())
    return hashlib.sha256(f"{body.kind}\0{normalized}".encode("utf-8")).hexdigest()[:32]


def _is_expired(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    raw = value.get("expires_at")
    if not raw:
        return False
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed <= datetime.now(timezone.utc)
    except ValueError:
        return False


def _rows(principal: Principal) -> list[dict[str, Any]]:
    if memory_store is not None:
        return memory_store.list_for_user(
            workspace_id=principal.workspace_id,
            user_id=principal.user_id,
            namespace=_NAMESPACE,
            limit=500,
        )
    return [
        {"namespace": namespace, "key": key, "value": value}
        for (workspace_id, user_id, namespace, key), value in _memory_fallback.items()
        if workspace_id == principal.workspace_id and user_id == principal.user_id and namespace == _NAMESPACE
    ][:500]


@router.get("/api/memory/items")
def list_memory_items(
    kind: MemoryKind | None = Query(default=None),
    include_expired: bool = Query(default=False),
    principal: Principal = Depends(require_owner),
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for row in _rows(principal):
        value = row.get("value")
        if not isinstance(value, dict):
            continue
        if kind and value.get("kind") != kind:
            continue
        expired = _is_expired(value)
        if expired and not include_expired:
            continue
        items.append({"key": row.get("key"), **value, "expired": expired})
    return {"items": items, "count": len(items), "namespace": _NAMESPACE}


@router.post("/api/memory/items")
def upsert_memory_item(body: MemoryItemBody, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    if contains_high_confidence_secret(body.model_dump(mode="json")):
        raise HTTPException(status_code=422, detail="Secrets must be stored in ALTER Vault, not ordinary memory")
    key = _key(body)
    if not key:
        raise HTTPException(status_code=422, detail="Memory key is invalid")
    value = {
        "kind": body.kind,
        "content": body.content.strip(),
        "importance": body.importance,
        "tags": _normalize_tags(body.tags),
        "source": body.source.strip(),
        "expires_at": body.expires_at.astimezone(timezone.utc).isoformat() if body.expires_at else None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if memory_store is not None:
        memory_store.upsert(
            workspace_id=principal.workspace_id,
            user_id=principal.user_id,
            namespace=_NAMESPACE,
            key=key,
            value=value,
        )
    else:
        _memory_fallback[(principal.workspace_id, principal.user_id, _NAMESPACE, key)] = value
    _audit(
        principal,
        event_type="memory.typed.upserted",
        payload={"key": key, "kind": body.kind, "importance": body.importance, "tag_count": len(value["tags"])},
    )
    return {"key": key, **value, "expired": _is_expired(value)}


@router.delete("/api/memory/items/{key:path}")
def delete_memory_item(key: str, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    clean_key = unquote(key)
    if memory_store is not None:
        dsn = getattr(memory_store, "dsn", None)
        if not dsn:
            raise HTTPException(status_code=503, detail="Memory deletion backend unavailable")
        with connect(dsn) as conn:
            result = conn.execute(
                "DELETE FROM memories WHERE workspace_id = %s AND user_id = %s AND namespace = %s AND key = %s",
                (principal.workspace_id, principal.user_id, _NAMESPACE, clean_key),
            )
            deleted = result.rowcount > 0
    else:
        deleted = _memory_fallback.pop((principal.workspace_id, principal.user_id, _NAMESPACE, clean_key), None) is not None
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory item not found")
    _audit(principal, event_type="memory.typed.deleted", payload={"key": clean_key})
    return {"deleted": True, "key": clean_key}
