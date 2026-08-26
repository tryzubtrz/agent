from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import connect
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .models import Approval, PolicyRule, Task
from .orchestrator import TaskNotFoundError


class PostgresTaskStore:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def save(self, task: Task) -> Task:
        task.touch()
        with connect(self.dsn) as conn:
            _ensure_workspace(conn, task.workspace_id)
            conn.execute(
                """
                INSERT INTO tasks (
                    id, workspace_id, owner_user_id, objective, status,
                    acceptance_criteria, current_step, blocker, pending_action,
                    created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    objective = EXCLUDED.objective,
                    status = EXCLUDED.status,
                    acceptance_criteria = EXCLUDED.acceptance_criteria,
                    current_step = EXCLUDED.current_step,
                    blocker = EXCLUDED.blocker,
                    pending_action = EXCLUDED.pending_action,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    task.id,
                    task.workspace_id,
                    task.owner_user_id,
                    task.objective,
                    task.status.value,
                    Jsonb(task.acceptance_criteria),
                    task.current_step,
                    task.blocker,
                    Jsonb(task.pending_action.model_dump(mode="json"))
                    if task.pending_action is not None
                    else None,
                    task.created_at,
                    task.updated_at,
                ),
            )
        return task

    def get(self, task_id: UUID) -> Task:
        with connect(self.dsn, row_factory=dict_row) as conn:
            row = conn.execute(
                """
                SELECT id, workspace_id, owner_user_id, objective, status,
                       acceptance_criteria, current_step, blocker, pending_action,
                       created_at, updated_at
                FROM tasks
                WHERE id = %s
                """,
                (task_id,),
            ).fetchone()
        if row is None:
            raise TaskNotFoundError(str(task_id))
        return Task.model_validate(row)


class PostgresPolicyStore:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def add(self, rule: PolicyRule) -> PolicyRule:
        with connect(self.dsn) as conn:
            _ensure_workspace(conn, rule.workspace_id)
            conn.execute(
                """
                INSERT INTO policy_rules (
                    id, workspace_id, original_text, category, effect,
                    enabled, priority, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    original_text = EXCLUDED.original_text,
                    category = EXCLUDED.category,
                    effect = EXCLUDED.effect,
                    enabled = EXCLUDED.enabled,
                    priority = EXCLUDED.priority
                """,
                (
                    rule.id,
                    rule.workspace_id,
                    rule.original_text,
                    rule.category,
                    rule.effect.value,
                    rule.enabled,
                    rule.priority,
                    rule.created_at,
                ),
            )
        return rule

    def list_for_workspace(self, workspace_id: UUID) -> list[PolicyRule]:
        with connect(self.dsn, row_factory=dict_row) as conn:
            rows = conn.execute(
                """
                SELECT id, workspace_id, original_text, category, effect,
                       enabled, priority, created_at
                FROM policy_rules
                WHERE workspace_id = %s
                ORDER BY priority DESC, created_at ASC
                """,
                (workspace_id,),
            ).fetchall()
        return [PolicyRule.model_validate(row) for row in rows]


class PostgresApprovalStore:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def save(self, approval: Approval, *, approved_by: UUID | None = None) -> Approval:
        with connect(self.dsn) as conn:
            _ensure_workspace(conn, approval.workspace_id)
            conn.execute(
                """
                INSERT INTO approvals (
                    id, workspace_id, task_id, action_digest, approved,
                    approved_by, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (task_id, action_digest) DO UPDATE SET
                    approved = EXCLUDED.approved,
                    approved_by = EXCLUDED.approved_by
                """,
                (
                    approval.id,
                    approval.workspace_id,
                    approval.task_id,
                    approval.action_digest,
                    approval.approved,
                    approved_by,
                    approval.created_at,
                ),
            )
        return approval


class PostgresAuditStore:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def write(
        self,
        *,
        workspace_id: UUID,
        event_type: str,
        actor_type: str,
        actor_id: str | None = None,
        task_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with connect(self.dsn) as conn:
            _ensure_workspace(conn, workspace_id)
            conn.execute(
                """
                INSERT INTO audit_events (
                    workspace_id, task_id, actor_type, actor_id, event_type, payload
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    workspace_id,
                    task_id,
                    actor_type,
                    actor_id,
                    event_type,
                    Jsonb(payload or {}),
                ),
            )


def _ensure_workspace(conn: Any, workspace_id: UUID) -> None:
    conn.execute(
        """
        INSERT INTO workspaces (id, name)
        VALUES (%s, %s)
        ON CONFLICT (id) DO UPDATE SET updated_at = now()
        """,
        (workspace_id, "ALTER"),
    )
