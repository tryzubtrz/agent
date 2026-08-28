from __future__ import annotations

from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .api import (
    _audit,
    _commit_task_transition_with_record,
    orchestrator,
    policy_store,
)
from .auth import Principal, require_owner
from .connector_gateway_api import test_connector
from .models import ActionRisk, PolicyEffect, Task, TaskStatus
from .orchestrator import ApprovalMismatchError, InvalidTaskTransitionError, TaskNotFoundError
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


def _validate_supported_action(task: Task) -> tuple[str, str, UUID]:
    if task.status not in {TaskStatus.EXECUTING, TaskStatus.AWAITING_APPROVAL} or task.pending_action is None:
        raise HTTPException(
            status_code=409,
            detail="Only an executing or approval-pending task with an active action can use the runtime executor.",
        )
    action = task.pending_action
    if action.attempt_id is None:
        raise HTTPException(status_code=409, detail="Active action has no bound execution attempt")
    if action.category != "connector" or action.operation != "self_test":
        raise HTTPException(
            status_code=422,
            detail="Runtime executor supports only connector/self_test actions in this release.",
        )
    if action.risk != ActionRisk.READ:
        raise HTTPException(
            status_code=422,
            detail="Connector self-test executor accepts read-risk actions only.",
        )
    connector = (action.target or "").strip().lower()
    if connector not in _SUPPORTED_CONNECTORS:
        raise HTTPException(
            status_code=422,
            detail="Unsupported read-only connector target.",
        )
    return connector, action.digest(), action.attempt_id


def _policy_preflight(
    *,
    task_id: UUID,
    principal: Principal,
    expected_digest: str,
    approval_digest: str | None,
) -> Task:
    """Lock task + latest policy snapshot immediately before read-only execution.

    The first executor intentionally supports read-only provider calls only. This
    preflight therefore does not hold a database transaction open across a network
    request. Future write executors require an execution lease/idempotency key.
    """
    outcome: dict[str, str | None] = {}

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
        if approval_digest is not None and approval_digest != current_digest:
            raise ApprovalMismatchError("Execution approval does not match the active action.")

        decision = orchestrator.policy_engine.evaluate(candidate.pending_action, current_rules)
        outcome["effect"] = decision.effect.value
        outcome["reason"] = decision.reason
        outcome["matched_rule_id"] = str(decision.matched_rule_id) if decision.matched_rule_id else None

        if decision.effect == PolicyEffect.DENY:
            candidate.status = TaskStatus.BLOCKED_BY_RULE
            candidate.current_step = "policy_recheck_before_executor"
            candidate.blocker = decision.reason
            candidate.pending_action = None
            return candidate

        if decision.effect == PolicyEffect.REQUIRE_APPROVAL and approval_digest != current_digest:
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
    reason = str(outcome.get("reason") or "Policy preflight failed")
    audit_payload = {
        "effect": effect,
        "reason": reason,
        "action_digest": expected_digest,
        "matched_rule_id": outcome.get("matched_rule_id"),
        "approval_digest_supplied": approval_digest == expected_digest,
    }

    if effect == PolicyEffect.DENY.value:
        _audit(
            principal,
            event_type="executor.policy_recheck_blocked",
            task_id=updated.id,
            payload=audit_payload,
        )
        raise HTTPException(status_code=409, detail=f"Current policy denies execution: {reason}")

    if effect == PolicyEffect.REQUIRE_APPROVAL.value and approval_digest != expected_digest:
        _audit(
            principal,
            event_type="executor.approval_required",
            task_id=updated.id,
            payload=audit_payload,
        )
        raise HTTPException(status_code=409, detail=f"Current policy requires approval: {reason}")

    if effect == PolicyEffect.REQUIRE_APPROVAL.value:
        _audit(
            principal,
            event_type="executor.inline_approval",
            task_id=updated.id,
            payload=audit_payload,
        )
    else:
        _audit(
            principal,
            event_type="executor.policy_preflight_allowed",
            task_id=updated.id,
            payload=audit_payload,
        )
    return updated


def _run_connector_self_test(connector: ReadOnlyConnector, principal: Principal) -> dict[str, Any]:
    # The existing connector gateway owns credential retrieval and provider-specific
    # network boundaries. The executor never receives or returns raw credentials.
    result = test_connector(connector, principal)
    return _safe_connector_output(connector, result)


def _persist_executor_result(
    *,
    task: Task,
    principal: Principal,
    action_digest: str,
    attempt_id: UUID,
    connector: str,
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
        "operation": "self_test",
        "target": connector,
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
            "connector": connector,
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
    # External connector execution remains Owner-only in the first production
    # release. Delegated execution can be added later with per-connector scopes.
    if principal.actor_role != "owner":
        raise HTTPException(status_code=403, detail="Only Owner can execute external connector actions")

    current = _owned_task(task_id, principal)
    connector, action_digest, _attempt_id = _validate_supported_action(current)
    approval_digest = body.approval_digest if body is not None else None
    prepared = _policy_preflight(
        task_id=task_id,
        principal=principal,
        expected_digest=action_digest,
        approval_digest=approval_digest,
    )
    connector, action_digest, attempt_id = _validate_supported_action(prepared)

    try:
        tool_output = _run_connector_self_test(connector, principal)  # type: ignore[arg-type]
        if tool_output.get("ok") is not True:
            raise HTTPException(status_code=502, detail="Connector self-test did not return ok=true")
        summary = f"{connector} connector self-test succeeded."
        evidence = [
            f"connector={connector}",
            "provider_result_ok=true",
            "secret_exposed=false",
        ]
        updated, record = _persist_executor_result(
            task=prepared,
            principal=principal,
            action_digest=action_digest,
            attempt_id=attempt_id,
            connector=connector,
            succeeded=True,
            summary=summary,
            evidence=evidence,
            tool_output=tool_output,
        )
    except HTTPException as exc:
        # Authentication/authorization/state/input errors are not provider outcomes.
        if exc.status_code in {401, 403, 409, 422}:
            raise
        summary = f"{connector} connector self-test failed: {str(exc.detail)[:500]}"
        evidence = [
            f"connector={connector}",
            f"provider_error_status={exc.status_code}",
            "secret_exposed=false",
        ]
        updated, record = _persist_executor_result(
            task=prepared,
            principal=principal,
            action_digest=action_digest,
            attempt_id=attempt_id,
            connector=connector,
            succeeded=False,
            summary=summary,
            evidence=evidence,
        )

    return {"task": updated, "execution": record}
