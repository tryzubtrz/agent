from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .api import _audit, _commit_task_transition_with_record, _get_owned_task, orchestrator
from .auth import Principal, require_owner
from .botpress_contract import BotpressContractError, validate_specialist_output
from .botpress_gateway import (
    BotpressGateway,
    BotpressRuntimeError,
    BotpressUnavailableError,
)
from .models import TaskStatus
from .orchestrator import InvalidTaskTransitionError
from .secret_safety import redact_secrets

router = APIRouter()
gateway = BotpressGateway()


class ThinkBody(BaseModel):
    objective: str = Field(min_length=1, max_length=10_000)
    context: str = Field(default="", max_length=20_000)
    mode: Literal["quick", "normal", "deep", "plan"] = "normal"


class PlanTaskBody(BaseModel):
    context: str = Field(default="", max_length=20_000)
    mode: Literal["normal", "deep", "plan"] = "plan"


@router.get("/agent/status")
@router.get("/api/agent/status")
def agent_status(_principal: Principal = Depends(require_owner)) -> dict[str, object]:
    status = gateway.status()
    return {
        "provider": "botpress",
        "configured": status.configured,
        "bot_id_configured": status.bot_id_configured,
        "credential_configured": status.credential_configured,
        "action": status.action,
        "side_effect_boundary": "core-policy-required",
    }


@router.post("/agent/think")
@router.post("/api/agent/think")
def agent_think(
    body: ThinkBody,
    principal: Principal = Depends(require_owner),
) -> dict[str, object]:
    safe_objective, objective_redacted = redact_secrets(body.objective)
    safe_context, context_redacted = redact_secrets(body.context)
    try:
        output = gateway.think(
            objective=safe_objective,
            context=safe_context,
            mode=body.mode,
        )
    except BotpressUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BotpressRuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        response = validate_specialist_output(output)
    except BotpressContractError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    safe_response, response_redacted = redact_secrets(response)
    redacted = objective_redacted or context_redacted or response_redacted
    _audit(
        principal,
        event_type="agent.thought",
        payload={
            "provider": "botpress",
            "mode": body.mode,
            "redacted": redacted,
            "boundary": "core-policy-required",
        },
    )

    return {
        "provider": "botpress",
        "response": safe_response,
        "side_effects_performed": False,
        "boundary": "core-policy-required",
        "redacted": redacted,
    }


@router.post("/tasks/{task_id}/plan")
@router.post("/api/tasks/{task_id}/plan")
def plan_task(
    task_id: UUID,
    body: PlanTaskBody,
    principal: Principal = Depends(require_owner),
) -> dict[str, object]:
    task = _get_owned_task(task_id, principal)
    if task.status not in {
        TaskStatus.INTAKE,
        TaskStatus.PLANNING,
        TaskStatus.RECOVERING,
    }:
        raise HTTPException(
            status_code=409,
            detail=f"Task cannot be planned from {task.status.value}.",
        )

    criteria = "\n".join(f"- {item}" for item in task.acceptance_criteria) or "- Define measurable acceptance criteria in the plan."
    planning_objective = (
        "Create a concrete execution plan for this ALTER task. "
        "Include scope, ordered steps, policy/permission preflight, likely blockers, "
        "and exact verification evidence required before completion. Do not claim execution.\n\n"
        f"TASK:\n{task.objective}\n\nACCEPTANCE CRITERIA:\n{criteria}"
    )
    safe_objective, objective_redacted = redact_secrets(planning_objective)
    safe_context, context_redacted = redact_secrets(body.context)

    try:
        output = gateway.think(
            objective=safe_objective,
            context=safe_context,
            mode=body.mode,
        )
    except BotpressUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BotpressRuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        response = validate_specialist_output(output, content_kind="plan")
    except BotpressContractError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    safe_plan, plan_redacted = redact_secrets(response)
    plan_record = {
        "plan": safe_plan,
        "provider": "botpress",
        "mode": body.mode,
        "boundary": "core-policy-required",
        "side_effects_performed": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        updated = _commit_task_transition_with_record(
            task_id=task.id,
            principal=principal,
            namespace="task.plan",
            key=str(task.id),
            value=plan_record,
            transition=orchestrator.transition_mark_ready,
        )
    except InvalidTaskTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(
        principal,
        event_type="task.planned",
        task_id=task.id,
        payload={
            "provider": "botpress",
            "mode": body.mode,
            "redacted": objective_redacted or context_redacted or plan_redacted,
            "boundary": "core-policy-required",
        },
    )
    return {
        "task": updated.model_dump(mode="json"),
        "plan": plan_record,
    }
