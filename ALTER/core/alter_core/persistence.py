from __future__ import annotations

from collections.abc import Callable
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

    def list_for_owner(
        self,
        workspace_id: UUID,
        owner_user_id: UUID,
        *,
        limit: int = 100,
    ) -> list[Task]:
        with connect(self.dsn, row_factory=dict_row) as conn:
            rows = conn.execute(
                """
                SELECT id, workspace_id, owner_user_id, objective, status,
                       acceptance_criteria, current_step, blocker, pending_action,
                       created_at, updated_at
                FROM tasks
                WHERE workspace_id = %s AND owner_user_id = %s
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (workspace_id, owner_user_id, limit),
            ).fetchall()
        return [Task.model_validate(row) for row in rows]

    def transition_with_memory(
        self,
        *,
        task_id: UUID,
        user_id: UUID,
        namespace: str,
        key: str,
        value: Any,
        transition: Callable[[Task], Task],
    ) -> Task:
        """Commit a task transition and its evidence record atomically."""
        with connect(self.dsn, row_factory=dict_row) as conn:
            row = conn.execute(
                """
                SELECT id, workspace_id, owner_user_id, objective, status,
                       acceptance_criteria, current_step, blocker, pending_action,
                       created_at, updated_at
                FROM tasks
                WHERE id = %s
                FOR UPDATE
                """,
                (task_id,),
            ).fetchone()
            if row is None:
                raise TaskNotFoundError(str(task_id))

            current = Task.model_validate(row)
            if current.owner_user_id != user_id:
                raise PermissionError("Cross-owner task transition denied.")
            task = transition(current)
            task.touch()
            conn.execute(
                """
                UPDATE tasks
                SET status = %s,
                    current_step = %s,
                    blocker = %s,
                    pending_action = %s,
                    updated_at = %s
                WHERE id = %s AND workspace_id = %s
                """,
                (
                    task.status.value,
                    task.current_step,
                    task.blocker,
                    Jsonb(task.pending_action.model_dump(mode="json"))
                    if task.pending_action is not None
                    else None,
                    task.updated_at,
                    task.id,
                    task.workspace_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO memories (workspace_id, user_id, namespace, key, value)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (workspace_id, user_id, namespace, key)
                DO UPDATE SET value = EXCLUDED.value, updated_at = now()
                """,
                (task.workspace_id, user_id, namespace, key, Jsonb(value)),
            )
        return task


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

    def list_for_workspace(
        self,
        workspace_id: UUID,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with connect(self.dsn, row_factory=dict_row) as conn:
            rows = conn.execute(
                """
                SELECT id, workspace_id, task_id, actor_type, actor_id,
                       event_type, payload, created_at
                FROM audit_events
                WHERE workspace_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (workspace_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]


class PostgresMemoryStore:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def upsert(
        self,
        *,
        workspace_id: UUID,
        user_id: UUID,
        namespace: str,
        key: str,
        value: Any,
    ) -> dict[str, Any]:
        with connect(self.dsn, row_factory=dict_row) as conn:
            _ensure_workspace(conn, workspace_id)
            row = conn.execute(
                """
                INSERT INTO memories (workspace_id, user_id, namespace, key, value)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (workspace_id, user_id, namespace, key)
                DO UPDATE SET value = EXCLUDED.value, updated_at = now()
                RETURNING id, workspace_id, user_id, namespace, key, value,
                          created_at, updated_at
                """,
                (workspace_id, user_id, namespace, key, Jsonb(value)),
            ).fetchone()
        assert row is not None
        return dict(row)

    def list_for_user(
        self,
        *,
        workspace_id: UUID,
        user_id: UUID,
        namespace: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT id, workspace_id, user_id, namespace, key, value,
                   created_at, updated_at
            FROM memories
            WHERE workspace_id = %s AND user_id = %s
        """
        params: list[Any] = [workspace_id, user_id]
        if namespace:
            query += " AND namespace = %s"
            params.append(namespace)
        query += " ORDER BY updated_at DESC LIMIT %s"
        params.append(limit)
        with connect(self.dsn, row_factory=dict_row) as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


class PostgresConnectorStore:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def list_for_workspace(self, workspace_id: UUID) -> list[dict[str, Any]]:
        with connect(self.dsn, row_factory=dict_row) as conn:
            rows = conn.execute(
                """
                SELECT id, workspace_id, connector_key, status, capabilities,
                       details, checked_at, updated_at
                FROM connector_states
                WHERE workspace_id = %s
                ORDER BY connector_key ASC
                """,
                (workspace_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert(
        self,
        *,
        workspace_id: UUID,
        connector_key: str,
        status: str,
        capabilities: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with connect(self.dsn, row_factory=dict_row) as conn:
            _ensure_workspace(conn, workspace_id)
            row = conn.execute(
                """
                INSERT INTO connector_states (
                    workspace_id, connector_key, status, capabilities,
                    details, checked_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, now(), now())
                ON CONFLICT (workspace_id, connector_key)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    capabilities = EXCLUDED.capabilities,
                    details = EXCLUDED.details,
                    checked_at = now(),
                    updated_at = now()
                RETURNING id, workspace_id, connector_key, status, capabilities,
                          details, checked_at, updated_at
                """,
                (
                    workspace_id,
                    connector_key,
                    status,
                    Jsonb(capabilities or []),
                    Jsonb(details or {}),
                ),
            ).fetchone()
        assert row is not None
        return dict(row)


def _ensure_workspace(conn: Any, workspace_id: UUID) -> None:
    conn.execute(
        """
        INSERT INTO workspaces (id, name)
        VALUES (%s, %s)
        ON CONFLICT (id) DO UPDATE SET updated_at = now()
        """,
        (workspace_id, "ALTER"),
    )
