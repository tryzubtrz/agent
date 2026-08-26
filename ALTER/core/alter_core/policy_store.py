from __future__ import annotations

from uuid import UUID

from .models import PolicyRule


class InMemoryPolicyStore:
    """MVP policy persistence boundary.

    Policy objects are created by authenticated control-plane endpoints and loaded
    server-side during action evaluation. Tool/model requests cannot supply their
    own policy rules.
    """

    def __init__(self) -> None:
        self._rules: dict[UUID, list[PolicyRule]] = {}

    def add(self, rule: PolicyRule) -> PolicyRule:
        self._rules.setdefault(rule.workspace_id, []).append(rule)
        return rule

    def list_for_workspace(self, workspace_id: UUID) -> list[PolicyRule]:
        return list(self._rules.get(workspace_id, []))
