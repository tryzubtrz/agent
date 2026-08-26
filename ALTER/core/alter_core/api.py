from __future__ import annotations

import os
from typing import Any, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from .auth import Principal, require_owner
from .models import ActionRequest, PolicyEffect, PolicyRule, Task
from .orchestrator import (
    ApprovalMismatchError,
    InMemoryTaskStore,
    TaskNotFoundError,
    TaskOrchestrator,
)
from .persistence import (
    PostgresApprovalStore,
    PostgresAuditStore,
    PostgresConnectorStore,
    PostgresMemoryStore,
    PostgresPolicyStore,
    PostgresTaskStore,
)
from .policy_store import InMemoryPolicyStore

app = FastAPI(title="ALTER Core", version="0.4.0")

_database_url = os.getenv("DATABASE_URL")
if _database_url:
    task_store = PostgresTaskStore(_database_url)
    policy_store = PostgresPolicyStore(_database_url)
    approval_store: PostgresApprovalStore | None = PostgresApprovalStore(_database_url)
    audit_store: PostgresAuditStore | None = PostgresAuditStore(_database_url)
    memory_store: PostgresMemoryStore | None = PostgresMemoryStore(_database_url)
    connector_store: PostgresConnectorStore | None = PostgresConnectorStore(_database_url)
    STORAGE_MODE = "postgres"
else:
    task_store = InMemoryTaskStore()
    policy_store = InMemoryPolicyStore()
    approval_store = None
    audit_store = None
    memory_store = None
    connector_store = None
    STORAGE_MODE = "memory"

orchestrator = TaskOrchestrator(store=task_store)
_memory_fallback: dict[tuple[UUID, UUID, str, str], Any] = {}
_connector_fallback: dict[tuple[UUID, str], dict[str, Any]] = {}


class CreateTaskBody(BaseModel):
    objective: str = Field(min_length=1, max_length=10_000)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=50)


class EvaluateActionBody(BaseModel):
    action: ActionRequest


class ApproveActionBody(BaseModel):
    action_digest: str = Field(min_length=64, max_length=64)


class CreatePolicyBody(BaseModel):
    original_text: str = Field(min_length=1, max_length=2_000)
    category: str = Field(min_length=1, max_length=200)
    effect: PolicyEffect
    priority: int = Field(default=100, ge=0, le=10_000)


class MemoryUpsertBody(BaseModel):
    namespace: str = Field(min_length=1, max_length=120)
    key: str = Field(min_length=1, max_length=240)
    value: Any


ConnectorStatus = Literal[
    "available",
    "connected",
    "degraded",
    "blocked",
    "not_configured",
    "unavailable",
]


class ConnectorStateBody(BaseModel):
    status: ConnectorStatus
    capabilities: list[str] = Field(default_factory=list, max_length=100)
    details: dict[str, Any] = Field(default_factory=dict)


@app.get("/health")
@app.get("/api/health")
def health() -> dict[str, str]:
    return {
        "service": "alter-core",
        "status": "ok",
        "version": "0.4.0",
        "storage": STORAGE_MODE,
    }


@app.get("/tasks", response_model=list[Task])
@app.get("/api/tasks", response_model=list[Task])
def list_tasks(
    limit: int = Query(default=100, ge=1, le=250),
    principal: Principal = Depends(require_owner),
) -> list[Task]:
    return task_store.list_for_owner(
        principal.workspace_id,
        principal.user_id,
        limit=limit,
    )


@app.post("/tasks", response_model=Task)
@app.post("/api/tasks", response_model=Task)
def create_task(
    body: CreateTaskBody,
    principal: Principal = Depends(require_owner),
) -> Task:
    task = orchestrator.create_task(
        workspace_id=principal.workspace_id,
        owner_user_id=principal.user_id,
        objective=body.objective,
        acceptance_criteria=body.acceptance_criteria,
    )
    _audit(
        principal,
        event_type="task.created",
        task_id=task.id,
        payload={"objective": task.objective, "status": task.status.value},
    )
    return task


@app.get("/tasks/{task_id}", response_model=Task)
@app.get("/api/tasks/{task_id}", response_model=Task)
def get_task(
    task_id: UUID,
    principal: Principal = Depends(require_owner),
) -> Task:
    return _get_owned_task(task_id, principal)


@app.post("/tasks/{task_id}/ready", response_model=Task)
@app.post("/api/tasks/{task_id}/ready", response_model=Task)
def mark_task_ready(
    task_id: UUID,
    principal: Principal = Depends(require_owner),
) -> Task:
    _get_owned_task(task_id, principal)
    task = orchestrator.mark_ready(task_id)
    _audit(principal, event_type="task.ready", task_id=task.id)
    return task


@app.post("/tasks/{task_id}/complete", response_model=Task)
@app.post("/api/tasks/{task_id}/complete", response_model=Task)
def complete_task(
    task_id: UUID,
    principal: Principal = Depends(require_owner),
) -> Task:
    _get_owned_task(task_id, principal)
    task = orchestrator.complete_task(
        task_id=task_id,
        workspace_id=principal.workspace_id,
    )
    _audit(principal, event_type="task.completed", task_id=task.id)
    return task


@app.get("/policies", response_model=list[PolicyRule])
@app.get("/api/policies", response_model=list[PolicyRule])
def list_policies(
    principal: Principal = Depends(require_owner),
) -> list[PolicyRule]:
    return policy_store.list_for_workspace(principal.workspace_id)


@app.post("/policies", response_model=PolicyRule)
@app.post("/api/policies", response_model=PolicyRule)
def create_policy(
    body: CreatePolicyBody,
    principal: Principal = Depends(require_owner),
) -> PolicyRule:
    rule = PolicyRule(
        workspace_id=principal.workspace_id,
        original_text=body.original_text,
        category=body.category,
        effect=body.effect,
        priority=body.priority,
    )
    saved = policy_store.add(rule)
    _audit(
        principal,
        event_type="policy.created",
        payload={
            "rule_id": str(saved.id),
            "category": saved.category,
            "effect": saved.effect.value,
            "priority": saved.priority,
        },
    )
    return saved


@app.get("/memory")
@app.get("/api/memory")
def list_memory(
    namespace: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=100, ge=1, le=250),
    principal: Principal = Depends(require_owner),
) -> list[dict[str, Any]]:
    if memory_store is not None:
        return memory_store.list_for_user(
            workspace_id=principal.workspace_id,
            user_id=principal.user_id,
            namespace=namespace,
            limit=limit,
        )

    items: list[dict[str, Any]] = []
    for (workspace_id, user_id, item_namespace, key), value in _memory_fallback.items():
        if workspace_id != principal.workspace_id or user_id != principal.user_id:
            continue
        if namespace is not None and item_namespace != namespace:
            continue
        items.append({"namespace": item_namespace, "key": key, "value": value})
    return items[:limit]


@app.put("/memory")
@app.put("/api/memory")
def upsert_memory(
    body: MemoryUpsertBody,
    principal: Principal = Depends(require_owner),
) -> dict[str, Any]:
    if memory_store is not None:
        saved = memory_store.upsert(
            workspace_id=principal.workspace_id,
            user_id=principal.user_id,
            namespace=body.namespace,
            key=body.key,
            value=body.value,
        )
    else:
        _memory_fallback[
            (principal.workspace_id, principal.user_id, body.namespace, body.key)
        ] = body.value
        saved = {
            "namespace": body.namespace,
            "key": body.key,
            "value": body.value,
        }
    _audit(
        principal,
        event_type="memory.upserted",
        payload={"namespace": body.namespace, "key": body.key},
    )
    return saved


@app.get("/audit")
@app.get("/api/audit")
def list_audit_events(
    limit: int = Query(default=100, ge=1, le=250),
    principal: Principal = Depends(require_owner),
) -> list[dict[str, Any]]:
    if audit_store is None:
        return []
    return audit_store.list_for_workspace(principal.workspace_id, limit=limit)


@app.get("/connectors")
@app.get("/api/connectors")
def list_connectors(
    principal: Principal = Depends(require_owner),
) -> list[dict[str, Any]]:
    if connector_store is not None:
        return connector_store.list_for_workspace(principal.workspace_id)
    return [
        item
        for (workspace_id, _), item in _connector_fallback.items()
        if workspace_id == principal.workspace_id
    ]


@app.put("/connectors/{connector_key}")
@app.put("/api/connectors/{connector_key}")
def upsert_connector(
    connector_key: str,
    body: ConnectorStateBody,
    principal: Principal = Depends(require_owner),
) -> dict[str, Any]:
    normalized_key = connector_key.strip().lower()
    if not normalized_key or len(normalized_key) > 120:
        raise HTTPException(status_code=422, detail="Invalid connector key")

    if connector_store is not None:
        saved = connector_store.upsert(
            workspace_id=principal.workspace_id,
            connector_key=normalized_key,
            status=body.status,
            capabilities=body.capabilities,
            details=body.details,
        )
    else:
        saved = {
            "workspace_id": str(principal.workspace_id),
            "connector_key": normalized_key,
            "status": body.status,
            "capabilities": body.capabilities,
            "details": body.details,
        }
        _connector_fallback[(principal.workspace_id, normalized_key)] = saved

    _audit(
        principal,
        event_type="connector.checked",
        payload={"connector_key": normalized_key, "status": body.status},
    )
    return saved


@app.post("/actions/evaluate", response_model=Task)
@app.post("/api/actions/evaluate", response_model=Task)
def evaluate_action(
    body: EvaluateActionBody,
    principal: Principal = Depends(require_owner),
) -> Task:
    _get_owned_task(body.action.task_id, principal)
    if body.action.workspace_id != principal.workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")

    try:
        task = orchestrator.request_action(
            body.action,
            owner_rules=policy_store.list_for_workspace(principal.workspace_id),
        )
        _audit(
            principal,
            event_type="action.evaluated",
            task_id=task.id,
            payload={
                "category": body.action.category,
                "operation": body.action.operation,
                "risk": body.action.risk.value,
                "resulting_status": task.status.value,
            },
        )
        return task
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Workspace mismatch") from exc


@app.post("/tasks/{task_id}/approve", response_model=Task)
@app.post("/api/tasks/{task_id}/approve", response_model=Task)
def approve_action(
    task_id: UUID,
    body: ApproveActionBody,
    principal: Principal = Depends(require_owner),
) -> Task:
    _get_owned_task(task_id, principal)
    try:
        task, approval = orchestrator.approve_pending_action(
            task_id=task_id,
            workspace_id=principal.workspace_id,
            action_digest=body.action_digest,
        )
        if approval_store is not None:
            approval_store.save(approval, approved_by=principal.user_id)
        _audit(
            principal,
            event_type="action.approved",
            task_id=task.id,
            payload={"action_digest": approval.action_digest},
        )
        return task
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Workspace mismatch") from exc
    except ApprovalMismatchError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _get_owned_task(task_id: UUID, principal: Principal) -> Task:
    try:
        task = orchestrator.store.get(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc

    if task.workspace_id != principal.workspace_id or task.owner_user_id != principal.user_id:
        raise HTTPException(status_code=404, detail="Task not found")

    return task


def _audit(
    principal: Principal,
    *,
    event_type: str,
    task_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    if audit_store is None:
        return
    audit_store.write(
        workspace_id=principal.workspace_id,
        task_id=task_id,
        actor_type="owner",
        actor_id=str(principal.user_id),
        event_type=event_type,
        payload=payload,
    )
