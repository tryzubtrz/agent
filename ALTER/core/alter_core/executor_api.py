from __future__ import annotations

from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .api import (
    _audit,
    _commit_approval_decision,
    _commit_task_transition_with_record,
    orchestrator,
    policy_store,
)
from .auth import Principal, require_owner
from .connector_gateway_api import test_connector
from .local_model_catalog import installable_model_ids
from .local_model_gateway import (
    LocalModelGateway,
    LocalModelRuntimeError,
    LocalModelUnavailableError,
)
from .models import ActionRisk, PolicyEffect, Task, TaskStatus
from .orchestrator import (
    ApprovalMismatchError,
    InvalidTaskTransitionError,
    PolicyDeniedApprovalError,
    TaskNotFoundError,
)
from .secret_safety import contains_high_confidence_secret

router = APIRouter()

ReadOnlyConnector = Literal["neon", "botpress", "github", "vercel"]
_SUPPORTED_CONNECTORS: set[str] = {"neon", "botpress", "github", "vercel"}


class ExecutePendingBody(BaseModel):
    approval_digest: str | None = Field(default=None, min_length=64, max_length=64)


def _owned_task(task_id: UUID, principal: Principal) -> Task:
    try:
        task = orchestrator.store.get(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    if task.workspace_id != principal.workspace_id or task.owner_user_id != principal.user_id:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def _safe_connector_output(connector: str, result: dict[str, Any]) -> dict[str, Any]:
    allowed: dict[str, tuple[str, ...]] = {
        "neon": ("connector", "ok", "storage", "secret_exposed"),
        "botpress": ("connector", "ok", "action", "paid_model_call", "secret_exposed"),
        "github": ("connector", "ok", "repository", "private", "default_branch", "secret_exposed"),
        "vercel": ("connector", "ok", "project_id", "project_name", "framework", "secret_exposed"),
    }
    safe = {key: result[key] for key in allowed[connector] if key in result}
    if safe.get("secret_exposed") is not False:
        raise HTTPException(status_code=502, detail="Connector self-test did not prove secret-safe output")
    if contains_high_confidence_secret(safe):
        raise HTTPException(status_code=502, detail="Connector output failed ALTER secret-safety verification")
    return safe


def _validate_supported_action(task: Task) -> tuple[str, str, str, UUID]:
    if task.status not in {TaskStatus.EXECUTING, TaskStatus.AWAITING_APPROVAL} or task.pending_action is None:
        raise HTTPException(
            status_code=409,
            detail="Only an executing or approval-pending task with an active action can use the runtime executor.",
        )
    action = task.pending_action
    if action.attempt_id is None:
        raise HTTPException(status_code=409, detail="Active action has no bound execution attempt")
    target = (action.target or "").strip().lower()
    if action.category == "connector" and action.operation == "self_test":
        if action.risk != ActionRisk.READ:
            raise HTTPException(status_code=422, detail="Connector self-test executor accepts read-risk actions only.")
        if target not in _SUPPORTED_CONNECTORS:
            raise HTTPException(status_code=422, detail="Unsupported read-only connector target.")
        return "connector", target, action.digest(), action.attempt_id
    if action.category == "model_install" and action.operation == "pull_allowlisted_model":
        if action.risk != ActionRisk.REVERSIBLE:
            raise HTTPException(status_code=422, detail="Model installation must be classified as reversible.")
        if target not in installable_model_ids():
            raise HTTPException(status_code=422, detail="Model is not in the ALTER installation allowlist.")
        return "model_install", target, action.digest(), action.attempt_id
    raise HTTPException(
        status_code=422,
        detail="Runtime executor does not support this action contract.",
    )


def _policy_preflight(
    *,
    task_id: UUID,
    principal: Principal,
    expected_digest: str,
    approval_satisfied: bool,
) -> tuple[Task, PolicyEffect, str]:
    """Lock task + latest policy snapshot immediately before bounded execution.

    Supported calls are either read-only connector tests or an allowlisted,
    reversible model pull accepted by the owner runtime. The preflight does not
    hold a database transaction open across a network request; the action digest
    and attempt ID bind the result to the approved request.
    """
    outcome: dict[str, Any] = {}

    def transition(candidate: Task, current_rules) -> Task:
        if candidate.workspace_id != principal.workspace_id or candidate.owner_user_id != principal.user_id:
            raise PermissionError("Cross-owner task transition denied.")
        if candidate.status not in {TaskStatus.EXECUTING, TaskStatus.AWAITING_APPROVAL}:
            raise InvalidTaskTransitionError(
                f"Task cannot enter executor preflight from {candidate.status.value}."
            )
        if candidate.pending_action is None:
            raise InvalidTaskTransitionError("Executor preflight requires an active action.")
        current_digest = candidate.pending_action.digest()
        if current_digest != expected_digest:
            raise ApprovalMismatchError("Active action changed before executor preflight.")

        decision = orchestrator.policy_engine.evaluate(candidate.pending_action, current_rules)
        outcome["effect"] = decision.effect
        outcome["reason"] = decision.reason
        outcome["matched_rule_id"] = str(decision.matched_rule_id) if decision.matched_rule_id else None

        if decision.effect == PolicyEffect.DENY:
            candidate.status = TaskStatus.BLOCKED_BY_RULE
            candidate.current_step = "policy_recheck_before_executor"
            candidate.blocker = decision.reason
            candidate.pending_action = None
            return candidate

        if decision.effect == PolicyEffect.REQUIRE_APPROVAL and not approval_satisfied:
            candidate.status = TaskStatus.AWAITING_APPROVAL
            candidate.current_step = "approval_before_executor"
            candidate.blocker = decision.reason
            return candidate

        candidate.status = TaskStatus.EXECUTING
        candidate.current_step = candidate.pending_action.operation
        candidate.blocker = None
        return candidate

    try:
        updated = orchestrator._transition_with_latest_rules(
            task_id=task_id,
            owner_user_id=principal.user_id,
            fallback_rules=policy_store.list_for_workspace(principal.workspace_id),
            transition=transition,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Task ownership changed before execution") from exc
    except (InvalidTaskTransitionError, ApprovalMismatchError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    effect = outcome.get("effect")
    if not isinstance(effect, PolicyEffect):
        raise HTTPException(status_code=500, detail="Executor policy preflight produced no decision")
    reason = str(outcome.get("reason") or "Policy preflight failed")
    event_type = "executor.policy_preflight_allowed"
    if effect == PolicyEffect.DENY:
        event_type = "executor.policy_recheck_blocked"
    elif effect == PolicyEffect.REQUIRE_APPROVAL and not approval_satisfied:
        event_type = "executor.approval_required"
    _audit(
        principal,
        event_type=event_type,
        task_id=updated.id,
        payload={
            "effect": effect.value,
            "reason": reason,
            "action_digest": expected_digest,
            "matched_rule_id": outcome.get("matched_rule_id"),
            "approval_satisfied": approval_satisfied,
        },
    )
    return updated, effect, reason


def _record_required_approval(
    *,
    task_id: UUID,
    principal: Principal,
    action_digest: str,
) -> Task:
    try:
        approved, _approval = _commit_approval_decision(
            task_id=task_id,
            principal=principal,
            action_digest=action_digest,
            approved=True,
            source="runtime_executor",
        )
    except PolicyDeniedApprovalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ApprovalMismatchError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return approved


def _run_connector_self_test(connector: ReadOnlyConnector, principal: Principal) -> dict[str, Any]:
    # The existing connector gateway owns credential retrieval and provider-specific
    # network boundaries. The executor never receives or returns raw credentials.
    result = test_connector(connector, principal)
    return _safe_connector_output(connector, result)


def _run_model_install(model_id: str, approval_digest: str) -> dict[str, Any]:
    try:
        result = LocalModelGateway().start_install(model_id=model_id, approval_digest=approval_digest)
    except LocalModelUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Owner model runtime is unavailable") from exc
    except LocalModelRuntimeError as exc:
        raise HTTPException(status_code=502, detail="Owner model runtime rejected the install job") from exc
    allowed = {key: result[key] for key in ("job_id", "state", "model_id", "secret_exposed") if key in result}
    if allowed.get("model_id") != model_id or allowed.get("secret_exposed") is not False:
        raise HTTPException(status_code=502, detail="Model runtime returned unverifiable install evidence")
    return allowed


def _persist_executor_result(
    *,
    task: Task,
    principal: Principal,
    action_digest: str,
    attempt_id: UUID,
    category: str,
    operation: str,
    target: str,
    succeeded: bool,
    summary: str,
    evidence: list[str],
    tool_output: dict[str, Any] | None = None,
) -> tuple[Task, dict[str, Any]]:
    execution_id = str(uuid4())
    record = {
        "execution_id": execution_id,
        "attempt_id": str(attempt_id),
        "action_digest": action_digest,
        "category": category,
        "operation": operation,
        "target": target,
        "succeeded": succeeded,
        "result_summary": summary,
        "verification_evidence": evidence,
        "artifact_refs": [],
        "verification_method": "tool_executor",
        "tool_output": tool_output or {},
    }
    if contains_high_confidence_secret(record):
        raise HTTPException(status_code=502, detail="Executor evidence failed ALTER secret-safety verification")

    try:
        updated = _commit_task_transition_with_record(
            task_id=task.id,
            principal=principal,
            namespace="task.action_result",
            key=f"{task.id}:{attempt_id}:{execution_id}",
            value=record,
            transition=lambda candidate: orchestrator.transition_action_result(
                candidate,
                workspace_id=principal.workspace_id,
                action_digest=action_digest,
                attempt_id=attempt_id,
                succeeded=succeeded,
                failure_reason=None if succeeded else summary,
            ),
        )
    except (InvalidTaskTransitionError, ApprovalMismatchError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    _audit(
        principal,
        event_type="action.executed_by_tool",
        task_id=updated.id,
        payload={
            "action_digest": action_digest,
            "attempt_id": str(attempt_id),
            "execution_id": execution_id,
            "category": category,
            "target": target,
            "succeeded": succeeded,
            "verification_method": "tool_executor",
        },
    )
    return updated, record


@router.post("/api/tasks/{task_id}/execute-pending")
@router.post("/tasks/{task_id}/execute-pending")
def execute_pending_action(
    task_id: UUID,
    body: ExecutePendingBody | None = None,
    principal: Principal = Depends(require_owner),
) -> dict[str, Any]:
    # Connector checks and model pulls remain Owner-only. Delegated execution can
    # be added later with explicit per-capability scopes.
    if principal.actor_role != "owner":
        raise HTTPException(status_code=403, detail="Only Owner can execute external connector actions")

    current = _owned_task(task_id, principal)
    category, target, action_digest, _attempt_id = _validate_supported_action(current)
    approval_digest = body.approval_digest if body is not None else None
    if approval_digest is not None and approval_digest != action_digest:
        raise HTTPException(status_code=409, detail="Execution approval does not match the active action.")

    prepared, effect, reason = _policy_preflight(
        task_id=task_id,
        principal=principal,
        expected_digest=action_digest,
        approval_satisfied=False,
    )
    approval_recorded = False

    if effect == PolicyEffect.DENY:
        raise HTTPException(status_code=409, detail=f"Current policy denies execution: {reason}")

    if effect == PolicyEffect.REQUIRE_APPROVAL:
        if approval_digest != action_digest:
            raise HTTPException(status_code=409, detail=f"Current policy requires approval: {reason}")
        prepared = _record_required_approval(
            task_id=task_id,
            principal=principal,
            action_digest=action_digest,
        )
        approval_recorded = True
        # A second lock/snapshot closes the gap between approval and provider call.
        prepared, effect, reason = _policy_preflight(
            task_id=task_id,
            principal=principal,
            expected_digest=action_digest,
            approval_satisfied=True,
        )
        if effect == PolicyEffect.DENY:
            raise HTTPException(status_code=409, detail=f"Current policy denies execution: {reason}")

    category, target, action_digest, attempt_id = _validate_supported_action(prepared)

    try:
        if category == "connector":
            tool_output = _run_connector_self_test(target, principal)  # type: ignore[arg-type]
            operation = "self_test"
            summary = f"{target} connector self-test succeeded."
            evidence = [
                f"connector={target}",
                "provider_result_ok=true",
                "secret_exposed=false",
            ]
        else:
            tool_output = _run_model_install(target, action_digest)
            operation = "pull_allowlisted_model"
            summary = f"{target} model installation job was accepted by the owner runtime."
            evidence = [
                f"model_id={target}",
                f"runtime_job_id={tool_output.get('job_id')}",
                f"runtime_job_state={tool_output.get('state')}",
                "allowlist_verified=true",
                "secret_exposed=false",
            ]
        if category == "connector" and tool_output.get("ok") is not True:
            raise HTTPException(status_code=502, detail="Connector self-test did not return ok=true")
        if approval_recorded:
            evidence.append("policy_approval_recorded=true")
        updated, record = _persist_executor_result(
            task=prepared,
            principal=principal,
            action_digest=action_digest,
            attempt_id=attempt_id,
            category=category,
            operation=operation,
            target=target,
            succeeded=True,
            summary=summary,
            evidence=evidence,
            tool_output=tool_output,
        )
    except HTTPException as exc:
        # Authentication/authorization/state/input errors are not provider outcomes.
        if exc.status_code in {401, 403, 409, 422}:
            raise
        operation = "self_test" if category == "connector" else "pull_allowlisted_model"
        summary = f"{target} {category} execution failed: {str(exc.detail)[:500]}"
        evidence = [
            f"category={category}",
            f"target={target}",
            f"provider_error_status={exc.status_code}",
            "secret_exposed=false",
        ]
        if approval_recorded:
            evidence.append("policy_approval_recorded=true")
        updated, record = _persist_executor_result(
            task=prepared,
            principal=principal,
            action_digest=action_digest,
            attempt_id=attempt_id,
            category=category,
            operation=operation,
            target=target,
            succeeded=False,
            summary=summary,
            evidence=evidence,
        )

    return {"task": updated, "execution": record}
