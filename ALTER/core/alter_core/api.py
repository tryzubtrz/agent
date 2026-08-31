from __future__ import annotations

import os
from collections.abc import Callable
from threading import RLock
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from .auth import Principal, require_owner
from .memory_safety import (
    is_internal_memory_namespace as _is_internal_memory_namespace,
    is_protected_memory_namespace as _is_protected_memory_namespace,
)
from .models import Approval, ActionRequest, PolicyEffect, PolicyRule, Task, TaskStatus
from .orchestrator import (
    ApprovalMismatchError,
    InMemoryTaskStore,
    InvalidTaskTransitionError,
    PolicyDeniedApprovalError,
    SecretBearingActionError,
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
from .secret_safety import contains_high_confidence_secret

app = FastAPI(title="ALTER Core", version="0.7.0")

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


class _RecencyMemory(dict[tuple[UUID, UUID, str, str], Any]):
    """Dictionary fallback whose iteration order mirrors updated_at DESC reads."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = RLock()

    def __setitem__(self, key: tuple[UUID, UUID, str, str], value: Any) -> None:
        with self._lock:
            if super().__contains__(key):
                super().__delitem__(key)
            super().__setitem__(key, value)

    def get(self, key: tuple[UUID, UUID, str, str], default: Any = None) -> Any:
        with self._lock:
            return super().get(key, default)

    def pop(self, key: tuple[UUID, UUID, str, str], default: Any = None) -> Any:
        with self._lock:
            return super().pop(key, default)

    def items(self) -> list[tuple[tuple[UUID, UUID, str, str], Any]]:
        with self._lock:
            return list(super().items())

    def clear(self) -> None:
        with self._lock:
            super().clear()


_memory_fallback: dict[tuple[UUID, UUID, str, str], Any] = _RecencyMemory()
_connector_fallback: dict[tuple[UUID, str], dict[str, Any]] = {}


def _commit_task_transition_with_record(
    *,
    task_id: UUID,
    principal: Principal,
    namespace: str,
    key: str,
    value: Any,
    transition: Callable[[Task], Task],
) -> Task:
    """Persist a task transition and its evidence as one logical operation."""
    store = orchestrator.store
    if isinstance(store, PostgresTaskStore):
        return store.transition_with_memory(
            task_id=task_id,
            user_id=principal.user_id,
            namespace=namespace,
            key=key,
            value=value,
            transition=transition,
        )

    def persist_record() -> None:
        if memory_store is not None:
            memory_store.upsert(
                workspace_id=principal.workspace_id,
                user_id=principal.user_id,
                namespace=namespace,
                key=key,
                value=value,
            )
        else:
            _memory_fallback[
                (principal.workspace_id, principal.user_id, namespace, key)
            ] = value

    if isinstance(store, InMemoryTaskStore):
        return store.transition_with_effect(task_id, transition, persist_record)

    updated = store.transition(task_id, transition)
    persist_record()
    return updated


def _commit_approval_decision(
    *,
    task_id: UUID,
    principal: Principal,
    action_digest: str,
    approved: bool,
    source: str,
) -> tuple[Task, Approval]:
    """Commit the task decision with its approval row and audit evidence."""

    def transition(candidate: Task, current_rules: list[PolicyRule]) -> Task:
        if approved:
            return orchestrator.transition_pending_approval(
                candidate,
                workspace_id=principal.workspace_id,
                action_digest=action_digest,
                owner_rules=current_rules,
                owner_user_id=principal.user_id,
            )
        return orchestrator.transition_pending_rejection(
            candidate,
            workspace_id=principal.workspace_id,
            owner_user_id=principal.user_id,
            action_digest=action_digest,
        )

    def approval_factory(updated: Task) -> Approval | None:
        if (
            approved
            and updated.status == TaskStatus.BLOCKED_BY_RULE
            and updated.current_step == "policy_recheck_before_approved_action"
        ):
            return None
        return Approval(
            workspace_id=principal.workspace_id,
            task_id=updated.id,
            action_digest=action_digest,
            approved=approved,
        )

    def audit_factory(
        updated: Task,
        approval: Approval | None,
    ) -> tuple[str, dict[str, Any]]:
        if approval is None:
            return (
                "action.approval_blocked_by_policy",
                {
                    "action_digest": action_digest,
                    "reason": updated.blocker,
                    "source": source,
                },
            )
        return (
            "action.approved" if approval.approved else "action.rejected",
            {"action_digest": action_digest, "source": source},
        )

    store = orchestrator.store
    if isinstance(store, PostgresTaskStore):
        updated, approval = store.transition_with_decision(
            task_id=task_id,
            user_id=principal.user_id,
            transition=transition,
            approval_factory=approval_factory,
            approved_by=principal.user_id,
            actor_type=principal.actor_role,
            actor_id=principal.actor_id,
            audit_factory=audit_factory,
        )
    else:
        current_rules = policy_store.list_for_workspace(principal.workspace_id)
        outcome: dict[str, Any] = {}

        def apply(candidate: Task) -> Task:
            updated_task = transition(candidate, current_rules)
            outcome["task"] = updated_task
            outcome["approval"] = approval_factory(updated_task)
            return updated_task

        def persist_decision() -> None:
            updated_task = outcome["task"]
            approval_record = outcome["approval"]
            if approval_record is not None and approval_store is not None:
                approval_store.save(approval_record, approved_by=principal.user_id)
            event_type, payload = audit_factory(updated_task, approval_record)
            _audit(
                principal,
                event_type=event_type,
                task_id=updated_task.id,
                payload=payload,
            )

        if isinstance(store, InMemoryTaskStore):
            updated = store.transition_with_effect(task_id, apply, persist_decision)
        else:
            updated = store.transition(task_id, apply)
            persist_decision()
        approval = outcome["approval"]

    if approval is None:
        raise PolicyDeniedApprovalError(
            "Current policy denies the pending action; the stale approval was not applied."
        )
    return updated, approval


def _clean_bounded_text_items(values: list[str], *, field_name: str, max_length: int) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        item = value.strip()
        if not item:
            raise ValueError(f"{field_name} must not be blank.")
        if len(item) > max_length:
            raise ValueError(f"{field_name} must not exceed {max_length} characters.")
        cleaned.append(item)
    return cleaned


class CreateTaskBody(BaseModel):
    objective: str = Field(min_length=1, max_length=10_000)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("objective")
    @classmethod
    def validate_objective(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Task objective must not be blank.")
        return cleaned

    @field_validator("acceptance_criteria")
    @classmethod
    def validate_acceptance_criteria(cls, values: list[str]) -> list[str]:
        return _clean_bounded_text_items(values, field_name="Acceptance criterion", max_length=2_000)


class EvaluateActionBody(BaseModel):
    action: ActionRequest


class ApproveActionBody(BaseModel):
    action_digest: str = Field(min_length=64, max_length=64)


class CompleteTaskBody(BaseModel):
    result_summary: str = Field(min_length=1, max_length=10_000)
    verification_evidence: list[str] = Field(min_length=1, max_length=50)
    artifact_refs: list[str] = Field(default_factory=list, max_length=50)
    acceptance_criteria_met: bool

    @field_validator("result_summary")
    @classmethod
    def validate_result_summary(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Result summary must not be blank.")
        return cleaned

    @field_validator("verification_evidence")
    @classmethod
    def validate_verification_evidence(cls, values: list[str]) -> list[str]:
        return _clean_bounded_text_items(values, field_name="Verification evidence", max_length=2_000)

    @field_validator("artifact_refs")
    @classmethod
    def validate_artifact_refs(cls, values: list[str]) -> list[str]:
        return _clean_bounded_text_items(values, field_name="Artifact reference", max_length=2_000)


class ActionResultBody(BaseModel):
    action_digest: str = Field(min_length=64, max_length=64)
    attempt_id: UUID
    succeeded: bool
    result_summary: str = Field(min_length=1, max_length=10_000)
    verification_evidence: list[str] = Field(min_length=1, max_length=50)
    artifact_refs: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("result_summary")
    @classmethod
    def validate_result_summary(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Action result summary must not be blank.")
        return cleaned

    @field_validator("verification_evidence")
    @classmethod
    def validate_verification_evidence(cls, values: list[str]) -> list[str]:
        return _clean_bounded_text_items(values, field_name="Action verification evidence", max_length=2_000)

    @field_validator("artifact_refs")
    @classmethod
    def validate_artifact_refs(cls, values: list[str]) -> list[str]:
        return _clean_bounded_text_items(values, field_name="Action artifact reference", max_length=2_000)


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
        "version": "0.7.0",
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
    if contains_high_confidence_secret(body.model_dump(mode="json")):
        raise HTTPException(
            status_code=422,
            detail="Secret-like content is not allowed in a task. Store it in ALTER Vault and use an alias.",
        )
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
    try:
        task = orchestrator.mark_ready(task_id)
    except InvalidTaskTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(principal, event_type="task.ready", task_id=task.id)
    return task


@app.post("/tasks/{task_id}/complete", response_model=Task)
@app.post("/api/tasks/{task_id}/complete", response_model=Task)
def complete_task(
    task_id: UUID,
    body: CompleteTaskBody,
    principal: Principal = Depends(require_owner),
) -> Task:
    if principal.actor_role != "owner":
        raise HTTPException(
            status_code=403,
            detail="Only Owner can attest task completion.",
        )
    current = _get_owned_task(task_id, principal)
    if current.status not in {
        TaskStatus.READY,
        TaskStatus.RECOVERING,
    }:
        raise HTTPException(
            status_code=409,
            detail=f"Task cannot be completed from {current.status.value}.",
        )
    if current.pending_action is not None:
        raise HTTPException(
            status_code=409,
            detail="Task cannot be completed while an action is still pending execution verification.",
        )
    if not body.acceptance_criteria_met:
        raise HTTPException(
            status_code=409,
            detail="Acceptance criteria must be confirmed before completion.",
        )
    if contains_high_confidence_secret(body.model_dump(mode="json")):
        raise HTTPException(
            status_code=422,
            detail="Secret-like content is not allowed in task results or verification evidence.",
        )

    result_record = {
        "result_summary": body.result_summary,
        "verification_evidence": body.verification_evidence,
        "artifact_refs": body.artifact_refs,
        "acceptance_criteria_met": True,
        "verification_method": "owner_attestation",
    }
    try:
        task = _commit_task_transition_with_record(
            task_id=task_id,
            principal=principal,
            namespace="task.result",
            key=str(task_id),
            value=result_record,
            transition=lambda candidate: orchestrator.transition_task_completion(
                candidate,
                workspace_id=principal.workspace_id,
                owner_attestation_confirmed=True,
            ),
        )
    except InvalidTaskTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(
        principal,
        event_type="task.completed",
        task_id=task.id,
        payload={
            "verification_evidence_count": len(body.verification_evidence),
            "artifact_count": len(body.artifact_refs),
            "acceptance_criteria_met": True,
            "verification_method": "owner_attestation",
        },
    )
    return task


@app.post("/tasks/{task_id}/action-result", response_model=Task)
@app.post("/api/tasks/{task_id}/action-result", response_model=Task)
def record_action_result(
    task_id: UUID,
    body: ActionResultBody,
    principal: Principal = Depends(require_owner),
) -> Task:
    if principal.actor_role != "owner":
        raise HTTPException(status_code=403, detail="Only Owner can attest an action result.")
    current = _get_owned_task(task_id, principal)
    if current.status != TaskStatus.EXECUTING or current.pending_action is None:
        raise HTTPException(
            status_code=409,
            detail="Only an executing task with an active action can record an action result.",
        )
    if current.pending_action.digest() != body.action_digest:
        raise HTTPException(status_code=409, detail="Action result does not match the active action.")
    if current.pending_action.attempt_id != body.attempt_id:
        raise HTTPException(
            status_code=409,
            detail="Action result does not match the active execution attempt.",
        )
    if contains_high_confidence_secret(body.model_dump(mode="json")):
        raise HTTPException(
            status_code=422,
            detail="Secret-like content is not allowed in action results or verification evidence.",
        )

    execution_id = str(uuid4())
    result_record = {
        "execution_id": execution_id,
        "attempt_id": str(body.attempt_id),
        "action_digest": body.action_digest,
        "operation": current.pending_action.operation,
        "target": current.pending_action.target,
        "succeeded": body.succeeded,
        "result_summary": body.result_summary,
        "verification_evidence": body.verification_evidence,
        "artifact_refs": body.artifact_refs,
        "verification_method": "owner_attestation",
    }
    try:
        result_key = f"{task_id}:{body.attempt_id}:{execution_id}"
        task = _commit_task_transition_with_record(
            task_id=task_id,
            principal=principal,
            namespace="task.action_result",
            key=result_key,
            value=result_record,
            transition=lambda candidate: orchestrator.transition_action_result(
                candidate,
                workspace_id=principal.workspace_id,
                action_digest=body.action_digest,
                attempt_id=body.attempt_id,
                succeeded=body.succeeded,
                failure_reason=None if body.succeeded else body.result_summary,
            ),
        )
    except (InvalidTaskTransitionError, ApprovalMismatchError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    _audit(
        principal,
        event_type="action.result_attested",
        task_id=task.id,
        payload={
            "action_digest": body.action_digest,
            "attempt_id": str(body.attempt_id),
            "succeeded": body.succeeded,
            "verification_evidence_count": len(body.verification_evidence),
            "artifact_count": len(body.artifact_refs),
            "verification_method": "owner_attestation",
        },
    )
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
    if namespace is not None and _is_internal_memory_namespace(namespace):
        raise HTTPException(status_code=403, detail="Internal memory is accessible only through its dedicated ALTER API.")
    if memory_store is not None:
        rows = memory_store.list_for_user(
            workspace_id=principal.workspace_id,
            user_id=principal.user_id,
            namespace=namespace,
            exclude_protected=True,
            limit=limit,
        )
        return [row for row in rows if not _is_internal_memory_namespace(str(row.get("namespace", "")))]

    items: list[dict[str, Any]] = []
    for (workspace_id, user_id, item_namespace, key), value in _memory_fallback.items():
        if workspace_id != principal.workspace_id or user_id != principal.user_id:
            continue
        if namespace is not None and item_namespace != namespace:
            continue
        if _is_internal_memory_namespace(item_namespace):
            continue
        items.append({"namespace": item_namespace, "key": key, "value": value})
    return list(reversed(items))[:limit]


@app.put("/memory")
@app.put("/api/memory")
def upsert_memory(
    body: MemoryUpsertBody,
    principal: Principal = Depends(require_owner),
) -> dict[str, Any]:
    if _is_internal_memory_namespace(body.namespace):
        raise HTTPException(
            status_code=403,
            detail="Internal memory is accessible only through its dedicated ALTER API.",
        )
    if contains_high_confidence_secret(body.value):
        raise HTTPException(
            status_code=422,
            detail="Secret-like content is not allowed in ordinary memory. Use ALTER Vault.",
        )
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
            owner_user_id=principal.user_id,
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
    except InvalidTaskTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SecretBearingActionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/tasks/{task_id}/approve", response_model=Task)
@app.post("/api/tasks/{task_id}/approve", response_model=Task)
def approve_action(
    task_id: UUID,
    body: ApproveActionBody,
    principal: Principal = Depends(require_owner),
) -> Task:
    _get_owned_task(task_id, principal)
    try:
        task, _approval = _commit_approval_decision(
            task_id=task_id,
            principal=principal,
            action_digest=body.action_digest,
            approved=True,
            source="legacy_task_endpoint",
        )
        return task
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Workspace mismatch") from exc
    except PolicyDeniedApprovalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
        actor_type=principal.actor_role,
        actor_id=principal.actor_id,
        event_type=event_type,
        payload=payload,
    )
