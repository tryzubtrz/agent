from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .agent_grounding import collect_agent_grounding
from .api import (
    _audit,
    _commit_task_transition_with_record,
    _get_owned_task,
    orchestrator,
)
from .auth import Principal, require_owner
from .botpress_contract import (
    BotpressContractError,
    BotpressInternalLeakError,
    validate_specialist_output,
)
from .botpress_gateway import (
    BotpressRuntimeError,
    BotpressUnavailableError,
)
from .local_model_gateway import LocalModelRuntimeError, LocalModelUnavailableError
from .models import TaskStatus
from .openai_agents_gateway import (
    OpenAIAgentsRuntimeError,
    OpenAIAgentsUnavailableError,
)
from .orchestrator import InvalidTaskTransitionError
from .reasoning_gateway import ReasoningGateway
from .secret_safety import redact_secrets

router = APIRouter()
gateway = ReasoningGateway()

_UNAVAILABLE_ERRORS = (
    BotpressUnavailableError,
    OpenAIAgentsUnavailableError,
    LocalModelUnavailableError,
)
_RUNTIME_ERRORS = (BotpressRuntimeError, OpenAIAgentsRuntimeError, LocalModelRuntimeError)


def _provider_name() -> str:
    status_method = getattr(gateway, "status", None)
    if not callable(status_method):
        return "botpress"
    return str(getattr(status_method(), "provider", "botpress"))


class ThinkBody(BaseModel):
    objective: str = Field(min_length=1, max_length=10_000)
    context: str = Field(default="", max_length=20_000)
    mode: Literal["quick", "normal", "deep", "plan"] = "normal"


class PlanTaskBody(BaseModel):
    context: str = Field(default="", max_length=20_000)
    mode: Literal["normal", "deep", "plan"] = "plan"


def _repair_internal_chat_output(*, objective: str, draft: str) -> tuple[str, bool]:
    """Retry once when Botpress accidentally returns internal orchestration notes.

    The rejected draft is secret-redacted and size-bounded before it is sent back
    to the specialist. The repaired response must pass the same strict contract.
    """
    safe_draft, draft_redacted = redact_secrets(draft)
    safe_draft = safe_draft[:8_000]
    repair_objective = (
        "Answer the user's original message directly and naturally. "
        "The previous draft was rejected because it exposed internal ALTER reasoning. "
        "Return only the final user-facing answer. Do not mention Core, orchestration, "
        "preflight, hidden reasoning, tools not being invoked, redacted context, or the repair.\n\n"
        f"ORIGINAL USER MESSAGE:\n{objective}"
    )
    repair_context = f"REJECTED DRAFT (rewrite, do not describe):\n{safe_draft}"
    repaired_output = gateway.think(
        objective=repair_objective,
        context=repair_context,
        mode="quick",
    )
    repaired = validate_specialist_output(repaired_output)
    return repaired, draft_redacted


@router.get("/agent/status")
@router.get("/api/agent/status")
def agent_status(_principal: Principal = Depends(require_owner)) -> dict[str, object]:
    status = gateway.status()
    return {
        "provider": status.provider,
        "configured": status.configured,
        "bot_id_configured": status.bot_id_configured,
        "credential_configured": status.credential_configured,
        "action": status.action,
        "model": status.model,
        "available_providers": list(status.available_providers),
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
    grounding_context, grounding_evidence = collect_agent_grounding(principal, safe_objective)
    if grounding_context:
        safe_context = "\n\n".join(part for part in (safe_context, grounding_context) if part)
    try:
        output = gateway.think(
            objective=safe_objective,
            context=safe_context,
            mode=body.mode,
        )
    except _UNAVAILABLE_ERRORS as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except _RUNTIME_ERRORS as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    recovered_internal_leak = False
    repair_redacted = False
    try:
        response = validate_specialist_output(output)
    except BotpressInternalLeakError:
        recovered_internal_leak = True
        raw_draft = output.get("response")
        draft = raw_draft if isinstance(raw_draft, str) else ""
        try:
            response, repair_redacted = _repair_internal_chat_output(
                objective=safe_objective,
                draft=draft,
            )
        except _UNAVAILABLE_ERRORS as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (*_RUNTIME_ERRORS, BotpressContractError) as exc:
            raise HTTPException(
                status_code=502,
                detail="ALTER blocked an internal reasoning leak and could not safely repair the response.",
            ) from exc
    except BotpressContractError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    reviewed = False
    reviewer_provider: str | None = None
    if body.mode == "deep":
        review_method = getattr(gateway, "review", None)
        if callable(review_method):
            try:
                reviewed_output = review_method(
                    objective=safe_objective,
                    draft=response,
                    context=safe_context,
                )
                response = validate_specialist_output(reviewed_output)
                raw_reviewer = reviewed_output.get("reviewerProvider")
                reviewer_provider = raw_reviewer if isinstance(raw_reviewer, str) else None
                reviewed = True
            except (*_UNAVAILABLE_ERRORS, *_RUNTIME_ERRORS, BotpressContractError):
                # A critic is an optional quality pass; the validated primary
                # response remains the safe fallback.
                reviewed = False

    safe_response, response_redacted = redact_secrets(response)
    redacted = (
        objective_redacted
        or context_redacted
        or repair_redacted
        or response_redacted
    )
    _audit(
        principal,
        event_type="agent.thought",
        payload={
            "provider": _provider_name(),
            "mode": body.mode,
            "redacted": redacted,
            "recovered_internal_leak": recovered_internal_leak,
            "grounded_tools": [item.get("tool") for item in grounding_evidence],
            "reviewed": reviewed,
            "reviewer_provider": reviewer_provider,
            "boundary": "core-policy-required",
        },
    )

    return {
        "provider": _provider_name(),
        "response": safe_response,
        "side_effects_performed": False,
        "boundary": "core-policy-required",
        "redacted": redacted,
        "recovered_internal_leak": recovered_internal_leak,
        "grounding": grounding_evidence,
        "reviewed": reviewed,
        "reviewer_provider": reviewer_provider,
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
    except _UNAVAILABLE_ERRORS as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except _RUNTIME_ERRORS as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        response = validate_specialist_output(output, content_kind="plan")
    except BotpressContractError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    safe_plan, plan_redacted = redact_secrets(response)
    plan_record = {
        "plan": safe_plan,
        "provider": _provider_name(),
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
            "provider": _provider_name(),
            "mode": body.mode,
            "redacted": objective_redacted or context_redacted or plan_redacted,
            "boundary": "core-policy-required",
        },
    )
    return {
        "task": updated.model_dump(mode="json"),
        "plan": plan_record,
    }
