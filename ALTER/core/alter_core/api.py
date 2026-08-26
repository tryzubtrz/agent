from __future__ import annotations

from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from .auth import Principal, require_owner
from .models import ActionRequest, PolicyEffect, PolicyRule, Task
from .orchestrator import ApprovalMismatchError, TaskNotFoundError, TaskOrchestrator
from .policy_store import InMemoryPolicyStore

app = FastAPI(title="ALTER Core", version="0.1.0")
orchestrator = TaskOrchestrator()
policy_store = InMemoryPolicyStore()


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


@app.get("/health")
def health() -> dict[str, str]:
    return {"service": "alter-core", "status": "ok", "version": "0.1.0"}


@app.post("/tasks", response_model=Task)
def create_task(
    body: CreateTaskBody,
    principal: Principal = Depends(require_owner),
) -> Task:
    return orchestrator.create_task(
        workspace_id=principal.workspace_id,
        owner_user_id=principal.user_id,
        objective=body.objective,
        acceptance_criteria=body.acceptance_criteria,
    )


@app.get("/tasks/{task_id}", response_model=Task)
def get_task(
    task_id: UUID,
    principal: Principal = Depends(require_owner),
) -> Task:
    return _get_owned_task(task_id, principal)


@app.get("/policies", response_model=list[PolicyRule])
def list_policies(
    principal: Principal = Depends(require_owner),
) -> list[PolicyRule]:
    return policy_store.list_for_workspace(principal.workspace_id)


@app.post("/policies", response_model=PolicyRule)
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
    return policy_store.add(rule)


@app.post("/actions/evaluate", response_model=Task)
def evaluate_action(
    body: EvaluateActionBody,
    principal: Principal = Depends(require_owner),
) -> Task:
    _get_owned_task(body.action.task_id, principal)
    if body.action.workspace_id != principal.workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")

    try:
        return orchestrator.request_action(
            body.action,
            owner_rules=policy_store.list_for_workspace(principal.workspace_id),
        )
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Workspace mismatch") from exc


@app.post("/tasks/{task_id}/approve", response_model=Task)
def approve_action(
    task_id: UUID,
    body: ApproveActionBody,
    principal: Principal = Depends(require_owner),
) -> Task:
    _get_owned_task(task_id, principal)
    try:
        task, _approval = orchestrator.approve_pending_action(
            task_id=task_id,
            workspace_id=principal.workspace_id,
            action_digest=body.action_digest,
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
