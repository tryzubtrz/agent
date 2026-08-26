from __future__ import annotations

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


class TaskNotFoundError(KeyError):
    pass


class ApprovalMismatchError(ValueError):
    pass


class InMemoryTaskStore:
    """MVP storage only. Replace with durable PostgreSQL/workflow persistence."""

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


class TaskOrchestrator:
    def __init__(
        self,
        *,
        store: InMemoryTaskStore | None = None,
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
        task.pending_action = None
        return self.store.save(task)

    def approve_pending_action(
        self,
        *,
        task_id: UUID,
        workspace_id: UUID,
        action_digest: str,
    ) -> tuple[Task, Approval]:
        task = self.store.get(task_id)
        self._assert_same_workspace(task, workspace_id)

        if task.status != TaskStatus.AWAITING_APPROVAL or task.pending_action is None:
            raise ApprovalMismatchError("Task is not awaiting approval.")

        if task.pending_action.digest() != action_digest:
            raise ApprovalMismatchError("Approval does not match the pending action.")

        approval = Approval(
            workspace_id=workspace_id,
            task_id=task.id,
            action_digest=action_digest,
            approved=True,
        )

        task.status = TaskStatus.EXECUTING
        task.current_step = task.pending_action.operation
        task.blocker = None
        task.pending_action = None
        return self.store.save(task), approval

    def resume_after_human_auth(self, *, task_id: UUID, workspace_id: UUID) -> Task:
        task = self.store.get(task_id)
        self._assert_same_workspace(task, workspace_id)

        if task.status not in {TaskStatus.AWAITING_LOGIN, TaskStatus.AWAITING_MFA}:
            raise ApprovalMismatchError("Task is not waiting for human authentication.")

        task.status = TaskStatus.READY
        task.current_step = "policy_recheck_after_human_auth"
        task.blocker = None
        task.pending_action = None
        return self.store.save(task)

    def complete_task(self, *, task_id: UUID, workspace_id: UUID) -> Task:
        task = self.store.get(task_id)
        self._assert_same_workspace(task, workspace_id)
        task.status = TaskStatus.DONE
        task.current_step = "report_and_memory"
        task.blocker = None
        task.pending_action = None
        return self.store.save(task)

    @staticmethod
    def _assert_same_workspace(task: Task, workspace_id: UUID) -> None:
        if task.workspace_id != workspace_id:
            raise PermissionError("Cross-workspace task access denied.")
