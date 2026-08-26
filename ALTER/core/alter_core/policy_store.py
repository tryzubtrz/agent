from __future__ import annotations

from uuid import UUID

from .models import PolicyRule


class InMemoryPolicyStore:
    """Local/test policy persistence boundary."""

    def __init__(self) -> None:
        self._rules: dict[UUID, list[PolicyRule]] = {}

    def add(self, rule: PolicyRule) -> PolicyRule:
        rules = self._rules.setdefault(rule.workspace_id, [])
        for index, existing in enumerate(rules):
            if existing.id == rule.id:
                rules[index] = rule
                return rule
        rules.append(rule)
        return rule

    def list_for_workspace(self, workspace_id: UUID) -> list[PolicyRule]:
        return list(self._rules.get(workspace_id, []))

    def delete(self, workspace_id: UUID, rule_id: UUID) -> bool:
        rules = self._rules.get(workspace_id, [])
        remaining = [rule for rule in rules if rule.id != rule_id]
        if len(remaining) == len(rules):
            return False
        self._rules[workspace_id] = remaining
        return True
