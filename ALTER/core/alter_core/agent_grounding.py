from __future__ import annotations

import json
import re
from typing import Any

from .api import STORAGE_MODE, connector_store, policy_store, task_store
from .auth import Principal
from .learning_api import learning_context
from .local_model_gateway import LocalModelGateway
from .productivity_api import _memory_list
from .secret_safety import redact_secrets


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _safe_json(value: Any, *, limit: int = 6000) -> str:
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        raw = str(value)
    safe, _ = redact_secrets(raw)
    return safe[:limit]


def collect_agent_grounding(principal: Principal, objective: str) -> tuple[str, list[dict[str, Any]]]:
    """Collect real read-only evidence before the model answers.

    The routing is deterministic, bounded and side-effect free. It ports the
    useful part of Agent-2's tool loop without trusting a model to execute
    arbitrary tools or exposing hidden chain-of-thought.
    """
    low = objective.lower()
    evidence: list[dict[str, Any]] = []
    blocks: list[str] = []

    if _matches(low, (r"\bзадач", r"\btask", r"канбан", r"запланован", r"статус.{0,12}роб")):
        tasks = task_store.list_for_owner(principal.workspace_id, principal.user_id, limit=60)
        payload = [
            {
                "id": str(task.id),
                "objective": task.objective[:500],
                "status": task.status.value,
                "current_step": task.current_step,
                "blocker": task.blocker,
                "updated_at": task.updated_at.isoformat(),
            }
            for task in tasks
        ]
        blocks.append("REAL TOOL RESULT tasks.list:\n" + _safe_json(payload))
        evidence.append({"tool": "tasks.list", "ok": True, "items": len(payload)})

    if _matches(low, (r"\bправил", r"\bpolicy", r"заборон", r"обмеженн", r"запрет")):
        rules = policy_store.list_for_workspace(principal.workspace_id)
        payload = [
            {
                "id": str(rule.id),
                "text": rule.original_text[:700],
                "category": rule.category,
                "effect": rule.effect.value,
                "enabled": rule.enabled,
                "priority": rule.priority,
            }
            for rule in rules
        ]
        blocks.append("REAL TOOL RESULT rules.list:\n" + _safe_json(payload))
        evidence.append({"tool": "rules.list", "ok": True, "items": len(payload)})

    if _matches(low, (r"стан систем", r"самоаудит", r"self.?audit", r"чи все прац", r"\bhealth\b", r"що ти вмієш")):
        connectors = connector_store.list_for_workspace(principal.workspace_id) if connector_store is not None else []
        runtime = LocalModelGateway().status()
        payload = {
            "storage": STORAGE_MODE,
            "tasks": len(task_store.list_for_owner(principal.workspace_id, principal.user_id, limit=500)),
            "rules": len(policy_store.list_for_workspace(principal.workspace_id)),
            "connectors": {
                "total": len(connectors),
                "connected": sum(1 for item in connectors if str(item.get("status")) == "connected"),
            },
            "local_model_runtime": {
                "configured": runtime.configured,
                "connected": runtime.connected,
                "installed_models": list(runtime.installed_models),
                "selected_model": runtime.model,
            },
        }
        blocks.append("REAL TOOL RESULT system.audit:\n" + _safe_json(payload))
        evidence.append({"tool": "system.audit", "ok": True, "items": len(payload)})

    if _matches(low, (r"автоматизац", r"розклад", r"scheduler", r"cron", r"нагадув")):
        rows = _memory_list(principal, "automation", 100)
        payload = [
            {"id": row.get("key"), **(row.get("value") if isinstance(row.get("value"), dict) else {})}
            for row in rows
            if not (isinstance(row.get("value"), dict) and row["value"].get("deleted"))
        ]
        blocks.append("REAL TOOL RESULT automations.list:\n" + _safe_json(payload))
        evidence.append({"tool": "automations.list", "ok": True, "items": len(payload)})

    learned = learning_context(principal, objective)
    if learned:
        blocks.append(learned)
        evidence.append({"tool": "learning.context", "ok": True})

    return "\n\n".join(blocks), evidence
