from __future__ import annotations

from collections.abc import Iterable

from .models import ActionRequest, ActionRisk, PolicyDecision, PolicyEffect, PolicyRule


IMMUTABLE_DENY_CATEGORIES = {
    "bypass_authentication",
    "secret_exfiltration",
    "disable_audit",
    "cross_workspace_access",
    "malware",
    "destructive_operating_system_action",
}


class PolicyEngine:
    """Evaluate an action immediately before execution.

    External content and model output never become policy. Only immutable rules and
    owner rules already persisted by the control plane are evaluated here.
    """

    def evaluate(
        self,
        action: ActionRequest,
        owner_rules: Iterable[PolicyRule],
    ) -> PolicyDecision:
        if action.category in IMMUTABLE_DENY_CATEGORIES:
            return PolicyDecision(
                effect=PolicyEffect.DENY,
                reason="Blocked by immutable ALTER safety core.",
            )

        matching_rules = sorted(
            (
                rule
                for rule in owner_rules
                if rule.enabled
                and rule.workspace_id == action.workspace_id
                and rule.category in {action.category, "*"}
            ),
            key=lambda rule: rule.priority,
        )

        if matching_rules:
            rule = matching_rules[0]
            return PolicyDecision(
                effect=rule.effect,
                reason=f"Matched owner Policy Menu rule: {rule.original_text}",
                matched_rule_id=rule.id,
            )

        if action.risk in {
            ActionRisk.PUBLIC,
            ActionRisk.FINANCIAL,
            ActionRisk.IRREVERSIBLE,
            ActionRisk.AUTHENTICATION,
        }:
            return PolicyDecision(
                effect=PolicyEffect.REQUIRE_APPROVAL,
                reason=f"{action.risk.value} action requires explicit approval by default.",
            )

        return PolicyDecision(
            effect=PolicyEffect.ALLOW,
            reason="Allowed by default low-risk policy.",
        )
