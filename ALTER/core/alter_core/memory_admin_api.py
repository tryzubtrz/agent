from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException
from psycopg import connect

from .api import _audit, _is_protected_memory_namespace, _memory_fallback, memory_store
from .auth import Principal, require_owner

router = APIRouter()


@router.delete("/api/memory/{namespace}/{key:path}")
def delete_memory(namespace: str, key: str, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    if _is_protected_memory_namespace(namespace):
        raise HTTPException(
            status_code=403,
            detail="Vault entries can be deleted only through ALTER Vault APIs.",
        )
    clean_key = unquote(key)
    if memory_store is not None:
        dsn = getattr(memory_store, "dsn", None)
        if not dsn:
            raise HTTPException(status_code=503, detail="Memory deletion backend unavailable")
        with connect(dsn) as conn:
            result = conn.execute(
                "DELETE FROM memories WHERE workspace_id = %s AND user_id = %s AND namespace = %s AND key = %s",
                (principal.workspace_id, principal.user_id, namespace, clean_key),
            )
            deleted = result.rowcount > 0
    else:
        deleted = _memory_fallback.pop((principal.workspace_id, principal.user_id, namespace, clean_key), None) is not None
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory item not found")
    _audit(principal, event_type="memory.deleted", payload={"namespace": namespace, "key": clean_key})
    return {"deleted": True, "namespace": namespace, "key": clean_key}

