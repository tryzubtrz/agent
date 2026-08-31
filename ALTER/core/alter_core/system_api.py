from __future__ import annotations

import os
from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends

from .api import STORAGE_MODE, connector_store, task_store
from .auth import Principal, require_owner
from .models import TaskStatus
from .reasoning_gateway import ReasoningGateway

router = APIRouter()
gateway = ReasoningGateway()


@router.get("/system/status")
@router.get("/api/system/status")
def system_status(principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    tasks = task_store.list_for_owner(
        principal.workspace_id,
        principal.user_id,
        limit=250,
    )
    active = [task for task in tasks if task.status not in {TaskStatus.DONE, TaskStatus.FAILED}]
    pending_approvals = [task for task in tasks if task.status == TaskStatus.AWAITING_APPROVAL]

    connectors: list[dict[str, Any]] = []
    if connector_store is not None:
        connectors = connector_store.list_for_workspace(principal.workspace_id)
    connector_counts = Counter(str(item.get("status", "unknown")) for item in connectors)

    agent = gateway.status()
    vault_envs = (
        "ALTER_API_TOKEN",
        "DATABASE_URL",
        "BOTPRESS_RUNTIME_TOKEN",
        "OPENAI_API_KEY",
        "ALTER_WEB_PIN",
    )
    vault_configured = sum(1 for name in vault_envs if os.getenv(name, "").strip())

    components = [
        {
            "key": "core",
            "label": "ALTER Core",
            "status": "ready",
            "detail": "Owner-authenticated API online",
        },
        {
            "key": "database",
            "label": "Neon Postgres",
            "status": "ready" if STORAGE_MODE == "postgres" else "degraded",
            "detail": STORAGE_MODE,
        },
        {
            "key": "conversation",
            "label": "Persistent conversation",
            "status": "ready",
            "detail": "Stored in owner-scoped memory with secret redaction",
        },
        {
            "key": "agent",
            "label": "ALTER AI specialist",
            "status": "ready" if agent.configured else "waiting",
            "detail": f"{agent.provider} · {agent.model or agent.action}" if agent.configured else "Runtime credential required",
        },
        {
            "key": "policy",
            "label": "Policy + Approvals",
            "status": "ready",
            "detail": f"{len(pending_approvals)} awaiting owner decision",
        },
        {
            "key": "files",
            "label": "Files v1",
            "status": "ready" if STORAGE_MODE == "postgres" else "degraded",
            "detail": "Text files up to 200 KB via Postgres memory store",
        },
        {
            "key": "vault",
            "label": "Vault aliases",
            "status": "ready" if vault_configured >= 2 else "waiting",
            "detail": f"{vault_configured}/{len(vault_envs)} server aliases configured",
        },
        {
            "key": "audit",
            "label": "Audit timeline",
            "status": "ready" if STORAGE_MODE == "postgres" else "degraded",
            "detail": "Owner actions recorded without raw secrets",
        },
        {
            "key": "local_models",
            "label": "Local models",
            "status": "waiting",
            "detail": "Catalog ready; a separate owner-controlled GPU/CPU runtime is required",
        },
        {
            "key": "browser",
            "label": "Browser executor",
            "status": "deferred",
            "detail": "Deferred by owner; no browser side effects are enabled",
        },
        {
            "key": "android",
            "label": "Android executor",
            "status": "deferred",
            "detail": "Deferred by owner; no Android side effects are enabled",
        },
    ]

    return {
        "overall": "ready" if STORAGE_MODE == "postgres" else "degraded",
        "storage": STORAGE_MODE,
        "tasks": {
            "total": len(tasks),
            "active": len(active),
            "awaiting_approval": len(pending_approvals),
        },
        "agent": {
            "provider": agent.provider,
            "configured": agent.configured,
            "credential_configured": agent.credential_configured,
            "bot_id_configured": agent.bot_id_configured,
            "action": agent.action,
            "model": agent.model,
            "available_providers": list(agent.available_providers),
        },
        "connectors": {
            "total": len(connectors),
            "by_status": dict(connector_counts),
        },
        "vault": {
            "aliases_known": len(vault_envs),
            "configured": vault_configured,
            "raw_secret_exposure": False,
        },
        "components": components,
    }
