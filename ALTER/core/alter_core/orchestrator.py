from __future__ import annotations

from typing import Protocol
from uuid import UUID

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


class InvalidTaskTransitionError(ValueError):
    pass


class SecretBearingActionError(ValueError):
    pass


class TaskStore(Protocol):
    def save(self, task: Task) -> Task: ...

    def get(self, task_id: UUID) -> Task: ...

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

    def save(self, task: Task) -> Task:
        task.touch()
        self._tasks[task.id] = task
        return task

    def get(self, task_id: UUID) -> Task:
        try:
            return self._tasks[task_id]
        except KeyError as exc:
            raise TaskNotFoundError(str(task_id)) from exc

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
        task = self.store.get(task_id)
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
        return self.store.save(task)

    def request_action(
        self,
        action: ActionRequest,
        *,
        owner_rules: list[PolicyRule] | None = None,
    ) -> Task:
        task = self.store.get(action.task_id)
        self._assert_same_workspace(task, action.workspace_id)

        if contains_high_confidence_secret(action.model_dump(mode="json")):
            raise SecretBearingActionError(
                "Raw secret-like values are not allowed in actions. Use an ALTER Vault alias."
            )

        if task.status not in {
            TaskStatus.READY,
            TaskStatus.EXECUTING,
            TaskStatus.RECOVERING,
        }:
            raise InvalidTaskTransitionError(
                f"Task cannot request an action from {task.status.value}."
            )

        decision = self.policy_engine.evaluate(action, owner_rules or [])

        if decision.effect == PolicyEffect.DENY:
            task.status = TaskStatus.BLOCKED_BY_RULE
            task.blocker = decision.reason
            task.pending_action = None
            return self.store.save(task)

        if action.requires_human_auth:
            task.status = TaskStatus.AWAITING_LOGIN
            task.blocker = "Human authentication is required."
            task.pending_action = action
            return self.store.save(task)

        if decision.effect == PolicyEffect.REQUIRE_APPROVAL:
            task.status = TaskStatus.AWAITING_APPROVAL
            task.blocker = decision.reason
            task.pending_action = action
            return self.store.save(task)

        task.status = TaskStatus.EXECUTING
        task.current_step = action.operation
        task.blocker = None
        # Keep the exact active action attached until execution is verified. This
        # prevents an executor from losing the approved parameters/digest.
        task.pending_action = action
        return self.store.save(task)

    def approve_pending_action(
        self,
        *,
        task_id: UUID,
        workspace_id: UUID,
        action_digest: str,
        owner_rules: list[PolicyRule] | None = None,
    ) -> tuple[Task, Approval]:
        task = self.store.get(task_id)
        self._assert_same_workspace(task, workspace_id)

        if task.status != TaskStatus.AWAITING_APPROVAL or task.pending_action is None:
            raise ApprovalMismatchError("Task is not awaiting approval.")

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
            self.store.save(task)
            raise ApprovalMismatchError(
                "Current policy denies the pending action; the stale approval was not applied."
            )

        approval = Approval(
            workspace_id=workspace_id,
            task_id=task.id,
            action_digest=action_digest,
            approved=True,
        )

        task.status = TaskStatus.EXECUTING
        task.current_step = task.pending_action.operation
        task.blocker = None
        # The status, rather than deleting the action, records that approval has
        # been granted. The action is cleared only after verified completion.
        return self.store.save(task), approval

    def resume_after_human_auth(self, *, task_id: UUID, workspace_id: UUID) -> Task:
        task = self.store.get(task_id)
        self._assert_same_workspace(task, workspace_id)

        if task.status not in {TaskStatus.AWAITING_LOGIN, TaskStatus.AWAITING_MFA}:
            raise ApprovalMismatchError("Task is not waiting for human authentication.")

        task.status = TaskStatus.READY
        task.current_step = "policy_recheck_after_human_auth"
        task.blocker = None
        return self.store.save(task)

    def complete_task(
        self,
        *,
        task_id: UUID,
        workspace_id: UUID,
        owner_attestation_confirmed: bool,
    ) -> Task:
        task = self.store.get(task_id)
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
        return self.store.save(task)

    def record_action_result(
        self,
        *,
        task_id: UUID,
        workspace_id: UUID,
        action_digest: str,
        succeeded: bool,
        failure_reason: str | None = None,
    ) -> Task:
        task = self.store.get(task_id)
        self._assert_same_workspace(task, workspace_id)
        if task.status != TaskStatus.EXECUTING or task.pending_action is None:
            raise InvalidTaskTransitionError(
                "Only an executing task with an active action can record an action result."
            )
        if task.pending_action.digest() != action_digest:
            raise ApprovalMismatchError(
                "Action result does not match the active action."
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
        return self.store.save(task)

    @staticmethod
    def _assert_same_workspace(task: Task, workspace_id: UUID) -> None:
        if task.workspace_id != workspace_id:
            raise PermissionError("Cross-workspace task access denied.")
