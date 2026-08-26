from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .api import _memory_fallback, memory_store
from .auth import Principal, require_owner
from .rag_engine import retrieve_rows

router = APIRouter()


class RagSearchBody(BaseModel):
    query: str = Field(min_length=1, max_length=10_000)
    limit: int = Field(default=6, ge=1, le=12)


def knowledge_rows(principal: Principal, *, limit: int = 1200) -> list[dict[str, Any]]:
    if memory_store is not None:
        return memory_store.list_for_user(
            workspace_id=principal.workspace_id,
            user_id=principal.user_id,
            namespace=None,
            limit=min(limit, 2000),
        )
    rows = [
        {"namespace": namespace, "key": key, "value": value}
        for (workspace_id, user_id, namespace, key), value in _memory_fallback.items()
        if workspace_id == principal.workspace_id and user_id == principal.user_id
    ]
    return rows[:limit]


@router.post("/api/rag/search")
def rag_search(body: RagSearchBody, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    hits = retrieve_rows(knowledge_rows(principal), body.query, limit=body.limit)
    return {
        "query": body.query,
        "hits": hits,
        "count": len(hits),
        "engine": "secret-safe-chunked-lexical-rag-v2",
        "embedding_provider": None,
        "semantic_upgrade_candidate": "BGE-M3 when a local runtime is connected",
    }
