from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends

from .auth import Principal, require_owner
from .productivity_api import _is_deleted, _memory_list, _next_due, run_automation

router = APIRouter()


@router.post("/api/automations/tick")
def tick_automations(principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    due: list[str] = []
    skipped: list[str] = []
    for row in _memory_list(principal, "automation", 250):
        if _is_deleted(row) or not isinstance(row.get("value"), dict):
            continue
        value = row["value"]
        automation_id = str(row.get("key"))
        next_due = _next_due(value, now)
        if next_due is None or next_due > now:
            skipped.append(automation_id)
            continue
        run_automation(automation_id, principal)
        due.append(automation_id)
    return {
        "checked_at": now.isoformat(),
        "ran": due,
        "ran_count": len(due),
        "skipped_count": len(skipped),
        "external_side_effects": False,
        "behavior": "creates ALTER tasks or in-app notifications only",
    }
