from __future__ import annotations

from collections.abc import Callable
from threading import RLock
from typing import Protocol
from uuid import UUID, uuid4

from .models import (
    ActionRequest,
    Approval,
    PolicyEffect,
    PolicyRule,
    Task,
    TaskStatus,
)
from .policy import PolicyEngine
from .secret_safety import contains_high_confidence_secret


class TaskNotFoundError(KeyError):
    pass


class ApprovalMismatchError(ValueError):
    pass


class PolicyDeniedApprovalError(ApprovalMismatchError):
    pass


class InvalidTaskTransitionError(ValueError):
    pass


class SecretBearingActionError(ValueError):
    pass


class TaskStore(Protocol):
    def save(self, task: Task) -> Task: ...

    def get(self, task_id: UUID) -> Task: ...

    def transition(
        self,
        task_id: UUID,
        transition: Callable[[Task], Task],
    ) -> Task: ...

    def list_for_owner(
        self,
        workspace_id: UUID,
        owner_user_id: UUID,
        *,
        limit: int = 100,
    ) -> list[Task]: ...


class InMemoryTaskStore:
    """Local/test fallback. Production should use a durable TaskStore."""

    def __init__(self) -> None:
        self._tasks: dict[UUID, Task] = {}
        self._lock = RLock()

    def save(self, task: Task) -> Task:
        task.touch()
        self._tasks[task.id] = task
        return task

    def get(self, task_id: UUID) -> Task:
        try:
            return self._tasks[task_id]
        except KeyError as exc:
            raise TaskNotFoundError(str(task_id)) from exc

    def transition(
        self,
        task_id: UUID,
        transition: Callable[[Task], Task],
    ) -> Task:
        """Apply a state transition against the latest task under one lock."""
        with self._lock:
            current = self.get(task_id).model_copy(deep=True)
            return self.save(transition(current))

    def transition_with_effect(
        self,
        task_id: UUID,
        transition: Callable[[Task], Task],
        effect: Callable[[], None],
    ) -> Task:
        """Commit an in-memory state transition only after its side effect succeeds."""
        with self._lock:
            current = self.get(task_id).model_copy(deep=True)
            updated = transition(current)
            effect()
            return self.save(updated)

    def list_for_owner(
        self,
        workspace_id: UUID,
        owner_user_id: UUID,
        *,
        limit: int = 100,
    ) -> list[Task]:
        items = [
            task
            for task in self._tasks.values()
            if task.workspace_id == workspace_id and task.owner_user_id == owner_user_id
        ]
        items.sort(key=lambda task: task.updated_at, reverse=True)
        return items[:limit]


class TaskOrchestrator:
    def __init__(
        self,
        *,
        store: TaskStore | None = None,
        policy_engine: PolicyEngine | None = None,
    ) -> None:
        self.store = store or InMemoryTaskStore()
        self.policy_engine = policy_engine or PolicyEngine()

    def create_task(
        self,
        *,
        workspace_id: UUID,
        owner_user_id: UUID,
        objective: str,
        acceptance_criteria: list[str] | None = None,
    ) -> Task:
        task = Task(
            workspace_id=workspace_id,
            owner_user_id=owner_user_id,
            objective=objective,
            acceptance_criteria=acceptance_criteria or [],
            status=TaskStatus.PLANNING,
            current_step="intake",
        )
        return self.store.save(task)

    def mark_ready(self, task_id: UUID) -> Task:
        return self.store.transition(task_id, self.transition_mark_ready)

    @staticmethod
    def transition_mark_ready(task: Task) -> Task:
        """Validate and apply readiness without persisting it."""
        if task.status not in {
            TaskStatus.INTAKE,
            TaskStatus.PLANNING,
            TaskStatus.RECOVERING,
        }:
            raise InvalidTaskTransitionError(
                f"Task cannot become ready from {task.status.value}."
            )
        task.status = TaskStatus.READY
        task.current_step = "preflight_quality_gate"
        task.blocker = None
        return task

    def request_action(
        self,
        action: ActionRequest,
        *,
        owner_rules: list[PolicyRule] | None = None,
        owner_user_id: UUID | None = None,
    ) -> Task:
        if contains_high_confidence_secret(action.model_dump(mode="json")):
            raise SecretBearingActionError(
                "Raw secret-like values are not allowed in actions. Use an ALTER Vault alias."
            )

        active_action = action.model_copy(
            deep=True,
            update={"attempt_id": uuid4()},
        )

        def apply(current: Task, current_rules: list[PolicyRule]) -> Task:
            self._assert_same_workspace(current, active_action.workspace_id)
            if owner_user_id is not None and current.owner_user_id != owner_user_id:
                raise PermissionError("Cross-owner task transition denied.")

            if current.status not in {
                TaskStatus.READY,
                TaskStatus.EXECUTING,
                TaskStatus.RECOVERING,
            }:
                raise InvalidTaskTransitionError(
                    f"Task cannot request an action from {current.status.value}."
                )

            if current.pending_action is not None:
                raise InvalidTaskTransitionError(
                    "The active action must be verified or cancelled before a new action is requested."
                )

            decision = self.policy_engine.evaluate(active_action, current_rules)

            if decision.effect == PolicyEffect.DENY:
                current.status = TaskStatus.BLOCKED_BY_RULE
                current.blocker = decision.reason
                current.pending_action = None
                return current

            if active_action.requires_human_auth:
                current.status = TaskStatus.AWAITING_LOGIN
                current.blocker = "Human authentication is required."
                current.pending_action = active_action
                return current

            if decision.effect == PolicyEffect.REQUIRE_APPROVAL:
                current.status = TaskStatus.AWAITING_APPROVAL
                current.blocker = decision.reason
                current.pending_action = active_action
                return current

            current.status = TaskStatus.EXECUTING
            current.current_step = active_action.operation
            current.blocker = None
            # Keep the exact active action attached until execution is verified.
            current.pending_action = active_action
            return current

        return self._transition_with_latest_rules(
            task_id=active_action.task_id,
            owner_user_id=owner_user_id,
            fallback_rules=owner_rules,
            transition=apply,
        )

    def approve_pending_action(
        self,
        *,
        task_id: UUID,
        workspace_id: UUID,
        action_digest: str,
        owner_rules: list[PolicyRule] | None = None,
        owner_user_id: UUID | None = None,
    ) -> tuple[Task, Approval]:
        task = self._transition_with_latest_rules(
            task_id=task_id,
            owner_user_id=owner_user_id,
            fallback_rules=owner_rules,
            transition=lambda candidate, current_rules: self.transition_pending_approval(
                candidate,
                workspace_id=workspace_id,
                action_digest=action_digest,
                owner_rules=current_rules,
                owner_user_id=owner_user_id,
            ),
        )
        if (
            task.status == TaskStatus.BLOCKED_BY_RULE
            and task.current_step == "policy_recheck_before_approved_action"
        ):
            raise PolicyDeniedApprovalError(
                "Current policy denies the pending action; the stale approval was not applied."
            )

        approval = Approval(
            workspace_id=workspace_id,
            task_id=task.id,
            action_digest=action_digest,
            approved=True,
        )
        return task, approval

    def transition_pending_approval(
        self,
        task: Task,
        *,
        workspace_id: UUID,
        action_digest: str,
        owner_rules: list[PolicyRule] | None = None,
        owner_user_id: UUID | None = None,
    ) -> Task:
        """Validate and apply approval against the latest locked task."""
        self._assert_same_workspace(task, workspace_id)
        if owner_user_id is not None and task.owner_user_id != owner_user_id:
            raise PermissionError("Cross-owner task transition denied.")

        if task.status != TaskStatus.AWAITING_APPROVAL or task.pending_action is None:
            raise ApprovalMismatchError("Task is not awaiting approval.")

        if task.pending_action.attempt_id is None:
            raise ApprovalMismatchError(
                "Pending action predates attempt binding; cancel and request it again."
            )

        if task.pending_action.digest() != action_digest:
            raise ApprovalMismatchError("Approval does not match the pending action.")

        current_decision = self.policy_engine.evaluate(
            task.pending_action,
            owner_rules or [],
        )
        if current_decision.effect == PolicyEffect.DENY:
            task.status = TaskStatus.BLOCKED_BY_RULE
            task.current_step = "policy_recheck_before_approved_action"
            task.blocker = current_decision.reason
            task.pending_action = None
            return task

        task.status = TaskStatus.EXECUTING
        task.current_step = task.pending_action.operation
        task.blocker = None
        # The status, rather than deleting the action, records that approval has
        # been granted. The action is cleared only after verified completion.
        return task

    def resume_after_human_auth(
        self,
        *,
        task_id: UUID,
        workspace_id: UUID,
        owner_rules: list[PolicyRule] | None = None,
        owner_user_id: UUID | None = None,
    ) -> Task:
        return self._transition_with_latest_rules(
            task_id=task_id,
            owner_user_id=owner_user_id,
            fallback_rules=owner_rules,
            transition=lambda task, current_rules: self.transition_after_human_auth(
                task,
                workspace_id=workspace_id,
                owner_rules=current_rules,
                owner_user_id=owner_user_id,
            ),
        )

    def transition_after_human_auth(
        self,
        task: Task,
        *,
        workspace_id: UUID,
        owner_rules: list[PolicyRule] | None = None,
        owner_user_id: UUID | None = None,
    ) -> Task:
        """Apply the post-authentication policy decision without persisting it."""
        self._assert_same_workspace(task, workspace_id)
        if owner_user_id is not None and task.owner_user_id != owner_user_id:
            raise PermissionError("Cross-owner task transition denied.")

        if task.status not in {TaskStatus.AWAITING_LOGIN, TaskStatus.AWAITING_MFA}:
            raise ApprovalMismatchError("Task is not waiting for human authentication.")
        if task.pending_action is None:
            raise ApprovalMismatchError("Authenticated task has no pending action.")
        if task.pending_action.attempt_id is None:
            raise ApprovalMismatchError(
                "Pending action predates attempt binding; cancel and request it again."
            )

        decision = self.policy_engine.evaluate(task.pending_action, owner_rules or [])
        if decision.effect == PolicyEffect.DENY:
            task.status = TaskStatus.BLOCKED_BY_RULE
            task.current_step = "policy_recheck_after_human_auth"
            task.blocker = decision.reason
            task.pending_action = None
            return task
        if decision.effect == PolicyEffect.REQUIRE_APPROVAL:
            task.status = TaskStatus.AWAITING_APPROVAL
            task.current_step = "approval_after_human_auth"
            task.blocker = decision.reason
            return task

        task.status = TaskStatus.EXECUTING
        task.current_step = task.pending_action.operation
        task.blocker = None
        return task

    def complete_task(
        self,
        *,
        task_id: UUID,
        workspace_id: UUID,
        owner_attestation_confirmed: bool,
    ) -> Task:
        return self.store.transition(
            task_id,
            lambda task: self.transition_task_completion(
                task,
                workspace_id=workspace_id,
                owner_attestation_confirmed=owner_attestation_confirmed,
            ),
        )

    def transition_task_completion(
        self,
        task: Task,
        *,
        workspace_id: UUID,
        owner_attestation_confirmed: bool,
    ) -> Task:
        """Validate and apply completion without persisting it.

        Persistence adapters use this pure transition inside a database
        transaction so the task state and verification record commit together.
        """
        self._assert_same_workspace(task, workspace_id)
        if not owner_attestation_confirmed:
            raise InvalidTaskTransitionError(
                "Task completion requires explicit Owner attestation."
            )
        if task.status not in {
            TaskStatus.READY,
            TaskStatus.RECOVERING,
        }:
            raise InvalidTaskTransitionError(
                f"Task cannot be completed from {task.status.value}."
            )
        if task.pending_action is not None:
            raise InvalidTaskTransitionError(
                "Task cannot be completed while an action is still pending execution verification."
            )
        task.status = TaskStatus.DONE
        task.current_step = "report_and_memory"
        task.blocker = None
        task.pending_action = None
        return task

    def record_action_result(
        self,
        *,
        task_id: UUID,
        workspace_id: UUID,
        action_digest: str,
        attempt_id: UUID,
        succeeded: bool,
        failure_reason: str | None = None,
    ) -> Task:
        return self.store.transition(
            task_id,
            lambda task: self.transition_action_result(
                task,
                workspace_id=workspace_id,
                action_digest=action_digest,
                attempt_id=attempt_id,
                succeeded=succeeded,
                failure_reason=failure_reason,
            ),
        )

    def transition_action_result(
        self,
        task: Task,
        *,
        workspace_id: UUID,
        action_digest: str,
        attempt_id: UUID,
        succeeded: bool,
        failure_reason: str | None = None,
    ) -> Task:
        """Validate and apply an action result without persisting it."""
        self._assert_same_workspace(task, workspace_id)
        if task.status != TaskStatus.EXECUTING or task.pending_action is None:
            raise InvalidTaskTransitionError(
                "Only an executing task with an active action can record an action result."
            )
        if task.pending_action.digest() != action_digest:
            raise ApprovalMismatchError(
                "Action result does not match the active action."
            )
        if task.pending_action.attempt_id != attempt_id:
            raise ApprovalMismatchError(
                "Action result does not match the active execution attempt."
            )

        task.pending_action = None
        if succeeded:
            task.status = TaskStatus.READY
            task.current_step = "action_result_verified"
            task.blocker = None
        else:
            task.status = TaskStatus.RECOVERING
            task.current_step = "action_failed_recovery"
            task.blocker = failure_reason or "The active action failed verification."
        return task

    def control_task(
        self,
        *,
        task_id: UUID,
        workspace_id: UUID,
        owner_user_id: UUID,
        action: str,
        reason: str | None = None,
        owner_rules: list[PolicyRule] | None = None,
    ) -> Task:
        return self._transition_with_latest_rules(
            task_id=task_id,
            owner_user_id=owner_user_id,
            fallback_rules=owner_rules,
            transition=lambda task, current_rules: self.transition_task_control(
                task,
                workspace_id=workspace_id,
                owner_user_id=owner_user_id,
                action=action,
                reason=reason,
                owner_rules=current_rules,
            ),
        )

    def transition_task_control(
        self,
        task: Task,
        *,
        workspace_id: UUID,
        owner_user_id: UUID,
        action: str,
        reason: str | None = None,
        owner_rules: list[PolicyRule] | None = None,
    ) -> Task:
        """Apply an Owner control command against the current locked task."""
        self._assert_same_workspace(task, workspace_id)
        if task.owner_user_id != owner_user_id:
            raise PermissionError("Cross-owner task transition denied.")

        if action == "pause":
            if task.status not in {
                TaskStatus.READY,
                TaskStatus.EXECUTING,
                TaskStatus.RECOVERING,
            }:
                raise InvalidTaskTransitionError(
                    f"Task cannot be paused from {task.status.value}."
                )
            task.status = TaskStatus.PAUSED
            task.blocker = reason or "Paused by owner."
            task.current_step = "paused"
            return task

        if action == "resume":
            if task.status != TaskStatus.PAUSED:
                raise InvalidTaskTransitionError("Only paused tasks can be resumed.")
            if task.pending_action is None:
                task.status = TaskStatus.READY
                task.blocker = None
                task.current_step = "resume_preflight"
                return task
            if task.pending_action.attempt_id is None:
                raise InvalidTaskTransitionError(
                    "Pending action predates attempt binding; cancel and request it again."
                )
            decision = self.policy_engine.evaluate(task.pending_action, owner_rules or [])
            if decision.effect == PolicyEffect.DENY:
                task.status = TaskStatus.BLOCKED_BY_RULE
                task.current_step = "policy_recheck_after_pause"
                task.blocker = decision.reason
                task.pending_action = None
                return task
            if decision.effect == PolicyEffect.REQUIRE_APPROVAL:
                task.status = TaskStatus.AWAITING_APPROVAL
                task.current_step = "approval_after_pause"
                task.blocker = decision.reason
                return task
            task.status = TaskStatus.EXECUTING
            task.blocker = None
            task.current_step = task.pending_action.operation
            return task

        if action == "retry":
            if task.status not in {
                TaskStatus.FAILED,
                TaskStatus.BLOCKED_BY_RULE,
                TaskStatus.RECOVERING,
            }:
                raise InvalidTaskTransitionError(
                    "Only failed or blocked tasks can be retried."
                )
            task.status = TaskStatus.RECOVERING
            task.blocker = reason
            task.current_step = "retry_preflight"
            task.pending_action = None
            return task

        if action == "cancel":
            if task.status == TaskStatus.DONE:
                raise InvalidTaskTransitionError("Completed task cannot be cancelled.")
            task.status = TaskStatus.CANCELLED
            task.blocker = reason or "Cancelled by owner."
            task.current_step = "cancelled"
            task.pending_action = None
            return task

        raise InvalidTaskTransitionError("Unsupported task control action.")

    def reject_pending_action(
        self,
        *,
        task_id: UUID,
        workspace_id: UUID,
        owner_user_id: UUID,
        action_digest: str,
    ) -> tuple[Task, Approval]:
        def apply(task: Task) -> Task:
            self._assert_same_workspace(task, workspace_id)
            if task.owner_user_id != owner_user_id:
                raise PermissionError("Cross-owner task transition denied.")
            if task.status != TaskStatus.AWAITING_APPROVAL or task.pending_action is None:
                raise ApprovalMismatchError("Task is not awaiting approval.")
            if task.pending_action.digest() != action_digest:
                raise ApprovalMismatchError("Rejection does not match the pending action.")
            task.status = TaskStatus.PAUSED
            task.current_step = "owner_rejected_action"
            task.blocker = "Owner rejected the pending action."
            task.pending_action = None
            return task

        task = self.store.transition(task_id, apply)
        rejection = Approval(
            workspace_id=workspace_id,
            task_id=task.id,
            action_digest=action_digest,
            approved=False,
        )
        return task, rejection

    def _transition_with_latest_rules(
        self,
        *,
        task_id: UUID,
        owner_user_id: UUID | None,
        fallback_rules: list[PolicyRule] | None,
        transition: Callable[[Task, list[PolicyRule]], Task],
    ) -> Task:
        policy_transition = getattr(self.store, "transition_with_policy_rules", None)
        if callable(policy_transition):
            if owner_user_id is None:
                raise PermissionError(
                    "Owner identity is required for a policy-aware durable transition."
                )
            return policy_transition(
                task_id=task_id,
                user_id=owner_user_id,
                transition=transition,
            )
        rules = fallback_rules or []
        return self.store.transition(task_id, lambda task: transition(task, rules))

    @staticmethod
    def _assert_same_workspace(task: Task, workspace_id: UUID) -> None:
        if task.workspace_id != workspace_id:
            raise PermissionError("Cross-workspace task access denied.")
