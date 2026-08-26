from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .auth import Principal, require_owner
from .models import Approval, Task, TaskStatus
from .orchestrator import ApprovalMismatchError
from .api import _audit, approval_store, orchestrator, policy_store, task_store

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
        limit=limit,
    )
    return [
        _pending_payload(task)
        for task in tasks
        if task.status == TaskStatus.AWAITING_APPROVAL and task.pending_action is not None
    ]


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
        updated, approval = orchestrator.approve_pending_action(
            task_id=task_id,
            workspace_id=principal.workspace_id,
            action_digest=body.action_digest,
            owner_rules=policy_store.list_for_workspace(principal.workspace_id),
        )
    except ApprovalMismatchError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if approval_store is not None:
        approval_store.save(approval, approved_by=principal.user_id)
    _audit(
        principal,
        event_type="action.approved",
        task_id=updated.id,
        payload={"action_digest": approval.action_digest, "source": "approval_ui"},
    )
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
    if task.status != TaskStatus.AWAITING_APPROVAL or task.pending_action is None:
        raise HTTPException(status_code=409, detail="Task is not awaiting approval")
    if task.pending_action.digest() != body.action_digest:
        raise HTTPException(status_code=409, detail="Rejection does not match the pending action")

    rejection = Approval(
        workspace_id=principal.workspace_id,
        task_id=task.id,
        action_digest=body.action_digest,
        approved=False,
    )
    task.status = TaskStatus.PAUSED
    task.current_step = "owner_rejected_action"
    task.blocker = "Owner rejected the pending action."
    task.pending_action = None
    updated = task_store.save(task)
    if approval_store is not None:
        approval_store.save(rejection, approved_by=principal.user_id)
    _audit(
        principal,
        event_type="action.rejected",
        task_id=updated.id,
        payload={"action_digest": body.action_digest, "source": "approval_ui"},
    )
    return updated
