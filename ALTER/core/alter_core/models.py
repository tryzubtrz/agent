from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TaskStatus(StrEnum):
    INTAKE = "intake"
    PLANNING = "planning"
    READY = "ready"
    EXECUTING = "executing"
    AWAITING_APPROVAL = "awaiting_approval"
    AWAITING_LOGIN = "awaiting_login"
    AWAITING_MFA = "awaiting_mfa"
    BLOCKED_BY_RULE = "blocked_by_rule"
    RECOVERING = "recovering"
    PAUSED = "paused"
    DONE = "done"
    FAILED = "failed"


class ActionRisk(StrEnum):
    READ = "read"
    REVERSIBLE = "reversible"
    PUBLIC = "public"
    FINANCIAL = "financial"
    IRREVERSIBLE = "irreversible"
    AUTHENTICATION = "authentication"


class PolicyEffect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class PolicyRule(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    workspace_id: UUID
    original_text: str
    category: str
    effect: PolicyEffect
    enabled: bool = True
    priority: int = 100
    created_at: datetime = Field(default_factory=utc_now)


class ActionRequest(BaseModel):
    workspace_id: UUID
    task_id: UUID
    category: str
    operation: str
    risk: ActionRisk
    target: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    requires_human_auth: bool = False

    def digest(self) -> str:
        stable = json.dumps(
            self.model_dump(mode="json", exclude_none=False),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(stable.encode("utf-8")).hexdigest()


class PolicyDecision(BaseModel):
    effect: PolicyEffect
    reason: str
    matched_rule_id: UUID | None = None


class Approval(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    workspace_id: UUID
    task_id: UUID
    action_digest: str
    approved: bool
    created_at: datetime = Field(default_factory=utc_now)


class Task(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    workspace_id: UUID
    owner_user_id: UUID
    objective: str
    status: TaskStatus = TaskStatus.INTAKE
    acceptance_criteria: list[str] = Field(default_factory=list)
    current_step: str | None = None
    blocker: str | None = None
    pending_action: ActionRequest | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def touch(self) -> None:
        self.updated_at = utc_now()
