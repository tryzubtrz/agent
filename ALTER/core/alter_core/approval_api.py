from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .api import _commit_approval_decision, task_store
from .auth import Principal, require_owner
from .models import Task, TaskStatus
from .orchestrator import ApprovalMismatchError, PolicyDeniedApprovalError

router = APIRouter()


class ApprovalDecisionBody(BaseModel):
    action_digest: str = Field(min_length=64, max_length=64)


def _pending_payload(task: Task) -> dict[str, Any]:
    action = task.pending_action
    if action is None:
        raise ApprovalMismatchError("Task has no pending action.")
    return {
        "task_id": str(task.id),
        "objective": task.objective,
        "status": task.status.value,
        "blocker": task.blocker,
        "action_digest": action.digest(),
        "action": action.model_dump(mode="json"),
        "updated_at": task.updated_at,
    }


@router.get("/approvals")
@router.get("/api/approvals")
def list_pending_approvals(
    limit: int = Query(default=100, ge=1, le=250),
    principal: Principal = Depends(require_owner),
) -> list[dict[str, Any]]:
    tasks = task_store.list_for_owner(
        principal.workspace_id,
        principal.user_id,
        status=TaskStatus.AWAITING_APPROVAL,
        require_pending_action=True,
        limit=limit,
    )
    return [_pending_payload(task) for task in tasks]


@router.post("/approvals/{task_id}/approve", response_model=Task)
@router.post("/api/approvals/{task_id}/approve", response_model=Task)
def approve_pending(
    task_id: UUID,
    body: ApprovalDecisionBody,
    principal: Principal = Depends(require_owner),
) -> Task:
    try:
        task = task_store.get(task_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc

    if task.workspace_id != principal.workspace_id or task.owner_user_id != principal.user_id:
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        updated, _approval = _commit_approval_decision(
            task_id=task_id,
            principal=principal,
            action_digest=body.action_digest,
            approved=True,
            source="approval_ui",
        )
    except PolicyDeniedApprovalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ApprovalMismatchError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return updated


@router.post("/approvals/{task_id}/reject", response_model=Task)
@router.post("/api/approvals/{task_id}/reject", response_model=Task)
def reject_pending(
    task_id: UUID,
    body: ApprovalDecisionBody,
    principal: Principal = Depends(require_owner),
) -> Task:
    try:
        task = task_store.get(task_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc

    if task.workspace_id != principal.workspace_id or task.owner_user_id != principal.user_id:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        updated, _rejection = _commit_approval_decision(
            task_id=task_id,
            principal=principal,
            action_digest=body.action_digest,
            approved=False,
            source="approval_ui",
        )
    except ApprovalMismatchError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return updated
