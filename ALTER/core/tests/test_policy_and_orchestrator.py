from uuid import uuid4

import pytest

from alter_core.models import (
    ActionRequest,
    ActionRisk,
    PolicyEffect,
    PolicyRule,
    TaskStatus,
)
from alter_core.orchestrator import ApprovalMismatchError, TaskOrchestrator
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

    tampered_action = action.model_copy(update={"parameters": {"caption": "changed"}})
    with pytest.raises(ApprovalMismatchError):
        orchestrator.approve_pending_action(
            task_id=task.id,
            workspace_id=workspace_id,
            action_digest=tampered_action.digest(),
        )

    approved, approval = orchestrator.approve_pending_action(
        task_id=task.id,
        workspace_id=workspace_id,
        action_digest=action.digest(),
    )
    assert approved.status == TaskStatus.EXECUTING
    assert approval.approved is True


def test_human_authentication_pauses_instead_of_bypassing():
    orchestrator = TaskOrchestrator()
    workspace_id = uuid4()
    task = orchestrator.create_task(
        workspace_id=workspace_id,
        owner_user_id=uuid4(),
        objective="Open authenticated service",
    )
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
