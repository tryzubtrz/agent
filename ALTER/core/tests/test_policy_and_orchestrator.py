from uuid import uuid4

import pytest
from alter_core import persistence
from alter_core.models import (
    ActionRequest,
    ActionRisk,
    PolicyEffect,
    PolicyRule,
    TaskStatus,
)
from alter_core.orchestrator import (
    ApprovalMismatchError,
    InMemoryTaskStore,
    InvalidTaskTransitionError,
    TaskOrchestrator,
)
from alter_core.persistence import PostgresMemoryStore, PostgresTaskStore
from alter_core.policy import PolicyEngine


def make_action(*, workspace_id, task_id, category="files", risk=ActionRisk.READ, **kwargs):
    return ActionRequest(
        workspace_id=workspace_id,
        task_id=task_id,
        category=category,
        operation=kwargs.pop("operation", "read"),
        risk=risk,
        **kwargs,
    )


def test_immutable_safety_core_beats_owner_allow_rule():
    workspace_id = uuid4()
    task_id = uuid4()
    action = make_action(
        workspace_id=workspace_id,
        task_id=task_id,
        category="secret_exfiltration",
    )
    rule = PolicyRule(
        workspace_id=workspace_id,
        original_text="Дозволяю все",
        category="secret_exfiltration",
        effect=PolicyEffect.ALLOW,
        priority=1,
    )

    decision = PolicyEngine().evaluate(action, [rule])

    assert decision.effect == PolicyEffect.DENY
    assert decision.matched_rule_id is None


def test_public_action_requires_approval_by_default():
    workspace_id = uuid4()
    action = make_action(
        workspace_id=workspace_id,
        task_id=uuid4(),
        category="social_publish",
        risk=ActionRisk.PUBLIC,
        operation="publish_post",
    )

    decision = PolicyEngine().evaluate(action, [])

    assert decision.effect == PolicyEffect.REQUIRE_APPROVAL


def test_owner_deny_rule_blocks_matching_action():
    workspace_id = uuid4()
    action = make_action(
        workspace_id=workspace_id,
        task_id=uuid4(),
        category="tiktok",
        risk=ActionRisk.REVERSIBLE,
        operation="open_tiktok",
    )
    rule = PolicyRule(
        workspace_id=workspace_id,
        original_text="Не відкривай TikTok",
        category="tiktok",
        effect=PolicyEffect.DENY,
    )

    decision = PolicyEngine().evaluate(action, [rule])

    assert decision.effect == PolicyEffect.DENY
    assert decision.matched_rule_id == rule.id


def test_other_workspace_rule_is_ignored():
    workspace_id = uuid4()
    action = make_action(
        workspace_id=workspace_id,
        task_id=uuid4(),
        category="files",
        risk=ActionRisk.READ,
    )
    foreign_rule = PolicyRule(
        workspace_id=uuid4(),
        original_text="Block all files",
        category="files",
        effect=PolicyEffect.DENY,
    )

    decision = PolicyEngine().evaluate(action, [foreign_rule])

    assert decision.effect == PolicyEffect.ALLOW


def test_orchestrator_rejects_cross_workspace_action():
    orchestrator = TaskOrchestrator()
    workspace_id = uuid4()
    task = orchestrator.create_task(
        workspace_id=workspace_id,
        owner_user_id=uuid4(),
        objective="Read a file",
    )
    action = make_action(
        workspace_id=uuid4(),
        task_id=task.id,
    )

    with pytest.raises(PermissionError):
        orchestrator.request_action(action)


def test_approval_is_bound_to_exact_pending_action_digest():
    orchestrator = TaskOrchestrator()
    workspace_id = uuid4()
    task = orchestrator.create_task(
        workspace_id=workspace_id,
        owner_user_id=uuid4(),
        objective="Publish a post",
    )
    orchestrator.mark_ready(task.id)
    action = make_action(
        workspace_id=workspace_id,
        task_id=task.id,
        category="social_publish",
        risk=ActionRisk.PUBLIC,
        operation="publish_post",
        parameters={"caption": "hello"},
    )

    waiting = orchestrator.request_action(action)
    assert waiting.status == TaskStatus.AWAITING_APPROVAL
    assert waiting.pending_action is not None
    pending_action = waiting.pending_action

    tampered_action = pending_action.model_copy(update={"parameters": {"caption": "changed"}})
    with pytest.raises(ApprovalMismatchError):
        orchestrator.approve_pending_action(
            task_id=task.id,
            workspace_id=workspace_id,
            action_digest=tampered_action.digest(),
        )

    approved, approval = orchestrator.approve_pending_action(
        task_id=task.id,
        workspace_id=workspace_id,
        action_digest=pending_action.digest(),
    )
    assert approved.status == TaskStatus.EXECUTING
    assert approval.approved is True
    assert approved.pending_action == pending_action


def test_human_authentication_pauses_instead_of_bypassing():
    orchestrator = TaskOrchestrator()
    workspace_id = uuid4()
    task = orchestrator.create_task(
        workspace_id=workspace_id,
        owner_user_id=uuid4(),
        objective="Open authenticated service",
    )
    orchestrator.mark_ready(task.id)
    action = make_action(
        workspace_id=workspace_id,
        task_id=task.id,
        category="service_login",
        risk=ActionRisk.AUTHENTICATION,
        operation="login",
        requires_human_auth=True,
    )

    waiting = orchestrator.request_action(action)

    assert waiting.status == TaskStatus.AWAITING_LOGIN
    assert waiting.pending_action is not None


def test_human_authentication_resume_rechecks_policy_and_restores_execution():
    orchestrator = TaskOrchestrator()
    workspace_id = uuid4()
    task = orchestrator.create_task(
        workspace_id=workspace_id,
        owner_user_id=uuid4(),
        objective="Open authenticated service",
    )
    orchestrator.mark_ready(task.id)
    action = make_action(
        workspace_id=workspace_id,
        task_id=task.id,
        category="service_login",
        risk=ActionRisk.AUTHENTICATION,
        operation="login",
        requires_human_auth=True,
    )
    allow_after_login = PolicyRule(
        workspace_id=workspace_id,
        original_text="Allow this owner-authenticated login",
        category="service_login",
        effect=PolicyEffect.ALLOW,
        priority=1,
    )

    waiting = orchestrator.request_action(action, owner_rules=[allow_after_login])
    assert waiting.status == TaskStatus.AWAITING_LOGIN
    assert waiting.pending_action is not None
    pending_action = waiting.pending_action

    resumed = orchestrator.resume_after_human_auth(
        task_id=task.id,
        workspace_id=workspace_id,
        owner_rules=[allow_after_login],
    )
    assert resumed.status == TaskStatus.EXECUTING
    assert resumed.pending_action == pending_action

    verified = orchestrator.record_action_result(
        task_id=task.id,
        workspace_id=workspace_id,
        action_digest=pending_action.digest(),
        attempt_id=pending_action.attempt_id,
        succeeded=True,
    )
    assert verified.status == TaskStatus.READY


def test_action_guard_runs_against_latest_locked_task_state():
    class ConcurrentStore(InMemoryTaskStore):
        injected_action: ActionRequest | None = None

        def transition(self, task_id, transition):
            if self.injected_action is not None:
                latest = self._tasks[task_id].model_copy(deep=True)
                latest.status = TaskStatus.EXECUTING
                latest.pending_action = self.injected_action
                self._tasks[task_id] = latest
                self.injected_action = None
            return super().transition(task_id, transition)

    store = ConcurrentStore()
    orchestrator = TaskOrchestrator(store=store)
    workspace_id = uuid4()
    task = orchestrator.create_task(
        workspace_id=workspace_id,
        owner_user_id=uuid4(),
        objective="Do one action at a time",
    )
    orchestrator.mark_ready(task.id)
    first = make_action(
        workspace_id=workspace_id,
        task_id=task.id,
        operation="first",
    )
    second = make_action(
        workspace_id=workspace_id,
        task_id=task.id,
        operation="second",
    )
    store.injected_action = first

    with pytest.raises(InvalidTaskTransitionError, match="active action"):
        orchestrator.request_action(second)

    retained = store.get(task.id)
    assert retained.pending_action == first


def test_stale_approval_cannot_resurrect_a_concurrently_cancelled_task():
    class CancellingStore(InMemoryTaskStore):
        cancel_before_next_transition = False

        def transition(self, task_id, transition):
            if self.cancel_before_next_transition:
                cancelled = self._tasks[task_id].model_copy(deep=True)
                cancelled.status = TaskStatus.CANCELLED
                cancelled.current_step = "cancelled"
                cancelled.blocker = "Cancelled concurrently."
                cancelled.pending_action = None
                self._tasks[task_id] = cancelled
                self.cancel_before_next_transition = False
            return super().transition(task_id, transition)

    store = CancellingStore()
    orchestrator = TaskOrchestrator(store=store)
    workspace_id = uuid4()
    task = orchestrator.create_task(
        workspace_id=workspace_id,
        owner_user_id=uuid4(),
        objective="Publish safely",
    )
    orchestrator.mark_ready(task.id)
    waiting = orchestrator.request_action(
        make_action(
            workspace_id=workspace_id,
            task_id=task.id,
            category="social_publish",
            risk=ActionRisk.PUBLIC,
            operation="publish_post",
        )
    )
    assert waiting.pending_action is not None
    store.cancel_before_next_transition = True

    with pytest.raises(ApprovalMismatchError, match="not awaiting approval"):
        orchestrator.approve_pending_action(
            task_id=task.id,
            workspace_id=workspace_id,
            action_digest=waiting.pending_action.digest(),
        )

    retained = store.get(task.id)
    assert retained.status == TaskStatus.CANCELLED
    assert retained.pending_action is None


def test_postgres_human_auth_transition_loads_policies_after_task_lock(monkeypatch):
    orchestrator = TaskOrchestrator()
    workspace_id = uuid4()
    owner_user_id = uuid4()
    task = orchestrator.create_task(
        workspace_id=workspace_id,
        owner_user_id=owner_user_id,
        objective="Authenticate before reading",
    )
    orchestrator.mark_ready(task.id)
    action = make_action(
        workspace_id=workspace_id,
        task_id=task.id,
        category="authenticated_read",
        operation="read",
        requires_human_auth=True,
    )
    waiting = orchestrator.request_action(action)
    deny = PolicyRule(
        workspace_id=workspace_id,
        original_text="Block after authentication",
        category="authenticated_read",
        effect=PolicyEffect.DENY,
        priority=1,
    )
    queries: list[str] = []

    class Result:
        def __init__(self, *, one=None, many=None):
            self.one = one
            self.many = many or []

        def fetchone(self):
            return self.one

        def fetchall(self):
            return self.many

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, _params):
            normalized = " ".join(query.split())
            queries.append(normalized)
            if "FROM tasks" in normalized and "FOR UPDATE" in normalized:
                return Result(one=waiting.model_dump(mode="python"))
            if "FROM policy_rules" in normalized:
                return Result(many=[deny.model_dump(mode="python")])
            return Result()

    monkeypatch.setattr(persistence, "connect", lambda *_args, **_kwargs: Connection())
    saved = PostgresTaskStore("postgresql://unused").transition_with_policy_rules(
        task_id=task.id,
        user_id=owner_user_id,
        transition=lambda candidate, current_rules: orchestrator.transition_after_human_auth(
            candidate,
            workspace_id=workspace_id,
            owner_rules=current_rules,
        ),
    )

    assert saved.status == TaskStatus.BLOCKED_BY_RULE
    assert saved.pending_action is None
    task_lock_index = next(index for index, query in enumerate(queries) if "FOR UPDATE" in query)
    policy_index = next(index for index, query in enumerate(queries) if "FROM policy_rules" in query)
    assert task_lock_index < policy_index


def test_postgres_memory_excludes_vault_rows_before_limit(monkeypatch):
    queries: list[str] = []

    class Result:
        def fetchall(self):
            return []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, _params):
            queries.append(" ".join(query.split()))
            return Result()

    monkeypatch.setattr(persistence, "connect", lambda *_args, **_kwargs: Connection())
    PostgresMemoryStore("postgresql://unused").list_for_user(
        workspace_id=uuid4(),
        user_id=uuid4(),
        exclude_protected=True,
        limit=25,
    )

    query = queries[0]
    protected_filter = query.index("left(lower(btrim(namespace)), 6) = '_vault'")
    order_by = query.index("ORDER BY updated_at DESC")
    limit = query.index("LIMIT %s")
    assert protected_filter < order_by < limit
    assert "left(lower(btrim(namespace)), 12) = 'vault_secure'" in query


def test_approval_rechecks_current_policy_and_rejects_stale_authority():
    orchestrator = TaskOrchestrator()
    workspace_id = uuid4()
    task = orchestrator.create_task(
        workspace_id=workspace_id,
        owner_user_id=uuid4(),
        objective="Publish a post",
    )
    orchestrator.mark_ready(task.id)
    action = make_action(
        workspace_id=workspace_id,
        task_id=task.id,
        category="social_publish",
        risk=ActionRisk.PUBLIC,
        operation="publish_post",
    )
    waiting = orchestrator.request_action(action)
    assert waiting.pending_action is not None
    new_deny_rule = PolicyRule(
        workspace_id=workspace_id,
        original_text="Do not publish anything",
        category="social_publish",
        effect=PolicyEffect.DENY,
        priority=1,
    )

    with pytest.raises(ApprovalMismatchError, match="Current policy denies"):
        orchestrator.approve_pending_action(
            task_id=task.id,
            workspace_id=workspace_id,
            action_digest=waiting.pending_action.digest(),
            owner_rules=[new_deny_rule],
        )

    blocked = orchestrator.store.get(task.id)
    assert blocked.status == TaskStatus.BLOCKED_BY_RULE
    assert blocked.pending_action is None
