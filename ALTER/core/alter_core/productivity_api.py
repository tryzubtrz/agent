from __future__ import annotations

import ipaddress
import json
import re
import socket
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .api import (
    _audit,
    _get_owned_task,
    _memory_fallback,
    audit_store,
    memory_store,
    orchestrator,
    policy_store,
)
from .auth import Principal, require_owner
from .memory_safety import is_rag_excluded_namespace
from .models import ActionRequest, ActionRisk, TaskStatus
from .orchestrator import ApprovalMismatchError, InvalidTaskTransitionError
from .secret_safety import contains_high_confidence_secret, redact_secrets

router = APIRouter()


class TaskControlBody(BaseModel):
    action: Literal["pause", "resume", "retry", "cancel", "authentication_complete"]
    reason: str | None = Field(default=None, max_length=1000)


class TaskMetaBody(BaseModel):
    expected_result: str | None = Field(default=None, max_length=5000)
    deadline: datetime | None = None
    autonomy: Literal["ask_often", "balanced", "high"] = "balanced"
    sources: list[str] = Field(default_factory=list, max_length=50)
    notes: str | None = Field(default=None, max_length=5000)


class KnowledgeSearchBody(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    namespaces: list[str] = Field(default_factory=lambda: ["memory", "files", "conversation", "task.meta"])
    limit: int = Field(default=20, ge=1, le=50)


class PolicyDryRunBody(BaseModel):
    category: str = Field(min_length=1, max_length=200)
    operation: str = Field(min_length=1, max_length=200)
    risk: ActionRisk = ActionRisk.READ
    target: str | None = Field(default=None, max_length=1000)
    parameters: dict[str, Any] = Field(default_factory=dict)


class AutomationBody(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1, max_length=5000)
    cadence: Literal["manual", "daily", "weekly", "hourly"] = "manual"
    hour_utc: int = Field(default=12, ge=0, le=23)
    weekday: int = Field(default=0, ge=0, le=6)
    enabled: bool = True
    mode: Literal["create_task", "notify_only"] = "create_task"


class CalendarEventBody(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    starts_at: datetime
    ends_at: datetime | None = None
    location: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=3000)


class ContactBody(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=3000)


class SettingsBody(BaseModel):
    language: str = Field(default="uk", max_length=20)
    voice_enabled: bool = True
    notifications_enabled: bool = True
    autonomy: Literal["ask_often", "balanced", "high"] = "balanced"
    remember_conversations: bool = True
    theme: Literal["dark", "system"] = "dark"


class ResearchUrlBody(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


class NoResearchRedirectHandler(HTTPRedirectHandler):
    """Expose redirects to ALTER so every destination is SSRF-validated."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


_RESEARCH_OPENER = build_opener(NoResearchRedirectHandler())
_RESEARCH_REDIRECT_CODES = {301, 302, 303, 307, 308}
_MAX_RESEARCH_REDIRECTS = 5


def _memory_list(
    principal: Principal,
    namespace: str | None = None,
    limit: int = 250,
    *,
    key: str | None = None,
    key_prefix: str | None = None,
) -> list[dict[str, Any]]:
    if memory_store is not None:
        return memory_store.list_for_user(
            workspace_id=principal.workspace_id,
            user_id=principal.user_id,
            namespace=namespace,
            key=key,
            key_prefix=key_prefix,
            limit=limit,
        )
    result: list[dict[str, Any]] = []
    for (workspace_id, user_id, item_namespace, item_key), value in _memory_fallback.items():
        if workspace_id != principal.workspace_id or user_id != principal.user_id:
            continue
        if namespace is not None and item_namespace != namespace:
            continue
        if key is not None and item_key != key:
            continue
        if key_prefix is not None and not item_key.startswith(key_prefix):
            continue
        result.append({"namespace": item_namespace, "key": item_key, "value": value})
    return list(reversed(result))[:limit]


def _memory_put(principal: Principal, namespace: str, key: str, value: Any) -> dict[str, Any]:
    if contains_high_confidence_secret(value):
        raise HTTPException(status_code=422, detail="Secret-like content must be stored through ALTER Vault, not ordinary memory.")
    if memory_store is not None:
        return memory_store.upsert(
            workspace_id=principal.workspace_id,
            user_id=principal.user_id,
            namespace=namespace,
            key=key,
            value=value,
        )
    _memory_fallback[(principal.workspace_id, principal.user_id, namespace, key)] = value
    return {"namespace": namespace, "key": key, "value": value}


def _knowledge_rows(principal: Principal, *, limit: int = 250) -> list[dict[str, Any]]:
    """Load newest searchable rows after excluding internal namespaces."""
    if memory_store is not None:
        return memory_store.list_for_user(
            workspace_id=principal.workspace_id,
            user_id=principal.user_id,
            namespace=None,
            exclude_rag_internal=True,
            limit=limit,
        )
    rows = [
        {"namespace": namespace, "key": key, "value": value}
        for (workspace_id, user_id, namespace, key), value in _memory_fallback.items()
        if workspace_id == principal.workspace_id
        and user_id == principal.user_id
        and not is_rag_excluded_namespace(namespace, exclude_conversation=False)
    ]
    return list(reversed(rows))[:limit]


def _is_deleted(item: dict[str, Any]) -> bool:
    value = item.get("value")
    return isinstance(value, dict) and bool(value.get("deleted"))


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[\w'-]{2,}", value.lower(), flags=re.UNICODE)}


def _next_due(value: dict[str, Any], now: datetime) -> datetime | None:
    cadence = value.get("cadence")
    if cadence == "manual" or not value.get("enabled", True):
        return None
    hour = int(value.get("hour_utc", 12))
    last_run_raw = value.get("last_run_at")
    last_run: datetime | None = None
    if isinstance(last_run_raw, str):
        try:
            last_run = datetime.fromisoformat(last_run_raw.replace("Z", "+00:00"))
        except ValueError:
            last_run = None
    if cadence == "hourly":
        base = (last_run or value.get("created_at_dt") or now - timedelta(hours=1))
        if not isinstance(base, datetime):
            base = now - timedelta(hours=1)
        return base + timedelta(hours=1)
    if cadence == "daily":
        candidate = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if candidate <= (last_run or now - timedelta(days=1)):
            candidate += timedelta(days=1)
        return candidate
    if cadence == "weekly":
        weekday = int(value.get("weekday", 0))
        candidate = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        candidate += timedelta(days=(weekday - candidate.weekday()) % 7)
        if candidate <= (last_run or now - timedelta(days=7)):
            candidate += timedelta(days=7)
        return candidate
    return None


@router.get("/api/tasks/{task_id}/inspector")
def task_inspector(task_id: UUID, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    task = _get_owned_task(task_id, principal)
    events: list[dict[str, Any]] = []
    if audit_store is not None:
        events = audit_store.list_for_task(principal.workspace_id, task_id, limit=250)
    task_key = str(task_id)
    meta_rows = _memory_list(principal, "task.meta", 1, key=task_key)
    meta = next((row.get("value") for row in meta_rows), {})
    plan_rows = _memory_list(principal, "task.plan", 1, key=task_key)
    plan = next((row.get("value") for row in plan_rows), None)
    result_rows = _memory_list(principal, "task.result", 1, key=task_key)
    result = next((row.get("value") for row in result_rows), None)
    action_result_rows = _memory_list(
        principal,
        "task.action_result",
        250,
        key_prefix=f"{task_id}:",
    )
    action_results = [
        row.get("value")
        for row in action_result_rows
        if isinstance(row.get("value"), dict)
    ]
    return {
        "task": task.model_dump(mode="json"),
        "meta": meta if isinstance(meta, dict) else {},
        "plan": plan if isinstance(plan, dict) else None,
        "result": result if isinstance(result, dict) else None,
        "action_results": action_results,
        "events": events,
        "pending_action_digest": task.pending_action.digest() if task.pending_action else None,
        "pending_action_attempt_id": (
            str(task.pending_action.attempt_id)
            if task.pending_action is not None and task.pending_action.attempt_id is not None
            else None
        ),
    }


@router.put("/api/tasks/{task_id}/meta")
def task_meta(task_id: UUID, body: TaskMetaBody, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    _get_owned_task(task_id, principal)
    value = body.model_dump(mode="json")
    saved = _memory_put(principal, "task.meta", str(task_id), value)
    _audit(principal, event_type="task.meta.updated", task_id=task_id, payload={"autonomy": body.autonomy})
    return saved


@router.post("/api/tasks/{task_id}/control")
def task_control(task_id: UUID, body: TaskControlBody, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    _get_owned_task(task_id, principal)
    if body.action == "authentication_complete":
        if principal.actor_role != "owner":
            raise HTTPException(status_code=403, detail="Only Owner can confirm completion of human authentication.")
        try:
            saved = orchestrator.resume_after_human_auth(
                task_id=task_id,
                workspace_id=principal.workspace_id,
                owner_rules=policy_store.list_for_workspace(principal.workspace_id),
                owner_user_id=principal.user_id,
            )
        except ApprovalMismatchError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        _audit(
            principal,
            event_type="task.authentication_completed",
            task_id=saved.id,
            payload={"resulting_status": saved.status.value},
        )
        return saved.model_dump(mode="json")
    try:
        saved = orchestrator.control_task(
            task_id=task_id,
            workspace_id=principal.workspace_id,
            owner_user_id=principal.user_id,
            action=body.action,
            reason=body.reason,
            owner_rules=policy_store.list_for_workspace(principal.workspace_id),
        )
    except (InvalidTaskTransitionError, ApprovalMismatchError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(principal, event_type=f"task.{body.action}", task_id=saved.id, payload={"reason": body.reason})
    return saved.model_dump(mode="json")


@router.post("/api/policies/dry-run")
def policy_dry_run(body: PolicyDryRunBody, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    synthetic_task = orchestrator.create_task(
        workspace_id=principal.workspace_id,
        owner_user_id=principal.user_id,
        objective="Policy dry-run (no execution)",
        acceptance_criteria=[],
    )
    action = ActionRequest(
        workspace_id=principal.workspace_id,
        task_id=synthetic_task.id,
        category=body.category,
        operation=body.operation,
        risk=body.risk,
        target=body.target,
        parameters=body.parameters,
    )
    decision = orchestrator.policy_engine.evaluate(action, policy_store.list_for_workspace(principal.workspace_id))
    synthetic_task.status = TaskStatus.CANCELLED
    synthetic_task.current_step = "dry_run_complete"
    orchestrator.store.save(synthetic_task)
    _audit(principal, event_type="policy.dry_run", task_id=synthetic_task.id, payload={"category": body.category, "effect": decision.effect.value})
    return {"effect": decision.effect.value, "reason": decision.reason, "matched_rule_id": str(decision.matched_rule_id) if decision.matched_rule_id else None, "executed": False}


@router.get("/api/policies/conflicts")
def policy_conflicts(principal: Principal = Depends(require_owner)) -> list[dict[str, Any]]:
    rules = policy_store.list_for_workspace(principal.workspace_id)
    conflicts: list[dict[str, Any]] = []
    for index, first in enumerate(rules):
        for second in rules[index + 1:]:
            if first.enabled and second.enabled and first.category == second.category and first.effect != second.effect:
                conflicts.append({
                    "category": first.category,
                    "rule_ids": [str(first.id), str(second.id)],
                    "effects": [first.effect.value, second.effect.value],
                    "winner": str(first.id if first.priority <= second.priority else second.id),
                })
    return conflicts


@router.post("/api/knowledge/search")
def knowledge_search(body: KnowledgeSearchBody, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    query_tokens = _tokens(body.query)
    if not query_tokens:
        return {"query": body.query, "results": []}
    rows = _knowledge_rows(principal, limit=250)
    results: list[dict[str, Any]] = []
    allowed = set(body.namespaces)
    for row in rows:
        namespace = str(row.get("namespace", ""))
        if allowed and namespace not in allowed:
            continue
        if _is_deleted(row):
            continue
        haystack = f"{row.get('key', '')} {_text(row.get('value'))}"
        safe_haystack, _ = redact_secrets(haystack)
        hay_tokens = _tokens(safe_haystack)
        overlap = query_tokens & hay_tokens
        lowered = safe_haystack.lower()
        phrase_bonus = 5 if body.query.lower() in lowered else 0
        score = len(overlap) * 2 + phrase_bonus
        if score:
            results.append({
                "namespace": namespace,
                "key": row.get("key"),
                "score": score,
                "preview": safe_haystack[:900],
                "updated_at": row.get("updated_at"),
            })
    results.sort(key=lambda item: (item["score"], str(item.get("updated_at") or "")), reverse=True)
    return {"query": body.query, "engine": "local-lexical-v1", "results": results[: body.limit]}


@router.get("/api/automations")
def list_automations(principal: Principal = Depends(require_owner)) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    output: list[dict[str, Any]] = []
    for row in _memory_list(principal, "automation", 250):
        if _is_deleted(row):
            continue
        value = row.get("value") if isinstance(row.get("value"), dict) else {}
        output.append({**row, "next_due_at": (_next_due(value, now).isoformat() if _next_due(value, now) else None)})
    return output


@router.post("/api/automations")
def create_automation(body: AutomationBody, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    automation_id = str(uuid4())
    value = {**body.model_dump(mode="json"), "id": automation_id, "created_at": datetime.now(timezone.utc).isoformat(), "last_run_at": None, "deleted": False}
    saved = _memory_put(principal, "automation", automation_id, value)
    _audit(principal, event_type="automation.created", payload={"automation_id": automation_id, "cadence": body.cadence})
    return saved


@router.post("/api/automations/{automation_id}/run")
def run_automation(automation_id: str, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    rows = _memory_list(principal, "automation", 250)
    row = next((item for item in rows if item.get("key") == automation_id and not _is_deleted(item)), None)
    if row is None or not isinstance(row.get("value"), dict):
        raise HTTPException(status_code=404, detail="Automation not found")
    value = dict(row["value"])
    if not value.get("enabled", True):
        raise HTTPException(status_code=409, detail="Automation is disabled")
    now = datetime.now(timezone.utc).isoformat()
    result: dict[str, Any]
    if value.get("mode") == "notify_only":
        notification_id = str(uuid4())
        notification = {"id": notification_id, "title": value.get("name"), "body": value.get("prompt"), "read": False, "created_at": now, "source": "automation"}
        _memory_put(principal, "notification", notification_id, notification)
        result = {"notification_id": notification_id}
    else:
        task = orchestrator.create_task(
            workspace_id=principal.workspace_id,
            owner_user_id=principal.user_id,
            objective=str(value.get("prompt", "")),
            acceptance_criteria=[],
        )
        _audit(principal, event_type="task.created_by_automation", task_id=task.id, payload={"automation_id": automation_id})
        result = {"task_id": str(task.id)}
    value["last_run_at"] = now
    _memory_put(principal, "automation", automation_id, value)
    _audit(principal, event_type="automation.ran", payload={"automation_id": automation_id, **result})
    return {"automation_id": automation_id, "ran_at": now, **result}


@router.delete("/api/automations/{automation_id}")
def delete_automation(automation_id: str, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    rows = _memory_list(principal, "automation", 250)
    row = next((item for item in rows if item.get("key") == automation_id), None)
    if row is None or not isinstance(row.get("value"), dict):
        raise HTTPException(status_code=404, detail="Automation not found")
    value = dict(row["value"])
    value["deleted"] = True
    _memory_put(principal, "automation", automation_id, value)
    _audit(principal, event_type="automation.deleted", payload={"automation_id": automation_id})
    return {"deleted": True, "id": automation_id}


@router.get("/api/notifications")
def list_notifications(unread_only: bool = Query(default=False), principal: Principal = Depends(require_owner)) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in _memory_list(principal, "notification", 250):
        if _is_deleted(row) or not isinstance(row.get("value"), dict):
            continue
        value = row["value"]
        if unread_only and value.get("read"):
            continue
        items.append({"key": row.get("key"), **value})
    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return items


@router.post("/api/notifications/{notification_id}/read")
def read_notification(notification_id: str, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    rows = _memory_list(principal, "notification", 250)
    row = next((item for item in rows if item.get("key") == notification_id), None)
    if row is None or not isinstance(row.get("value"), dict):
        raise HTTPException(status_code=404, detail="Notification not found")
    value = dict(row["value"])
    value["read"] = True
    _memory_put(principal, "notification", notification_id, value)
    return {"read": True, "id": notification_id}


@router.get("/api/calendar")
def list_calendar(principal: Principal = Depends(require_owner)) -> list[dict[str, Any]]:
    return [row for row in _memory_list(principal, "calendar", 250) if not _is_deleted(row)]


@router.post("/api/calendar")
def create_calendar_event(body: CalendarEventBody, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    if body.ends_at and body.ends_at < body.starts_at:
        raise HTTPException(status_code=422, detail="Event end must be after start")
    event_id = str(uuid4())
    value = {**body.model_dump(mode="json"), "id": event_id, "deleted": False, "created_at": datetime.now(timezone.utc).isoformat()}
    saved = _memory_put(principal, "calendar", event_id, value)
    _audit(principal, event_type="calendar.event.created", payload={"event_id": event_id})
    return saved


@router.get("/api/contacts")
def list_contacts(principal: Principal = Depends(require_owner)) -> list[dict[str, Any]]:
    return [row for row in _memory_list(principal, "contact", 250) if not _is_deleted(row)]


@router.post("/api/contacts")
def create_contact(body: ContactBody, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    contact_id = str(uuid4())
    value = {**body.model_dump(mode="json"), "id": contact_id, "deleted": False, "created_at": datetime.now(timezone.utc).isoformat()}
    saved = _memory_put(principal, "contact", contact_id, value)
    _audit(principal, event_type="contact.created", payload={"contact_id": contact_id})
    return saved


@router.get("/api/settings")
def get_settings(principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    rows = _memory_list(principal, "settings", 10)
    row = next((item for item in rows if item.get("key") == "owner"), None)
    if row and isinstance(row.get("value"), dict):
        return row["value"]
    return SettingsBody().model_dump(mode="json")


@router.put("/api/settings")
def put_settings(body: SettingsBody, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    saved = _memory_put(principal, "settings", "owner", body.model_dump(mode="json"))
    _audit(principal, event_type="settings.updated", payload={"language": body.language, "autonomy": body.autonomy})
    return saved["value"]


def _validate_public_url(raw_url: str) -> str:
    parsed = urlparse(raw_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=422, detail="Only public http/https URLs are supported")
    host = parsed.hostname.lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise HTTPException(status_code=403, detail="Private/local destinations are blocked")
    try:
        addresses = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise HTTPException(status_code=422, detail="Host could not be resolved") from exc
    for info in addresses:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise HTTPException(status_code=403, detail="Private network destinations are blocked")
    return raw_url.strip()


def _open_public_research_url(raw_url: str):  # noqa: ANN201
    """Open a public URL while validating every redirect before following it."""
    current_url = _validate_public_url(raw_url)
    for redirect_count in range(_MAX_RESEARCH_REDIRECTS + 1):
        request = Request(
            current_url,
            headers={
                "User-Agent": "ALTER/1.0 research-reader",
                "Accept": "text/html,text/plain,application/json;q=0.9,*/*;q=0.1",
            },
            method="GET",
        )
        try:
            return _RESEARCH_OPENER.open(request, timeout=12), current_url  # noqa: S310 - every destination is validated
        except HTTPError as exc:
            if exc.code not in _RESEARCH_REDIRECT_CODES:
                exc.close()
                raise HTTPException(status_code=502, detail=f"Source returned HTTP {exc.code}") from exc
            location = exc.headers.get("Location") if exc.headers is not None else None
            exc.close()
            if not location:
                raise HTTPException(status_code=502, detail="Source returned a redirect without a destination") from exc
            if redirect_count >= _MAX_RESEARCH_REDIRECTS:
                raise HTTPException(status_code=508, detail="Source exceeded the redirect limit") from exc
            current_url = _validate_public_url(urljoin(current_url, location))
        except (URLError, TimeoutError) as exc:
            raise HTTPException(status_code=502, detail="Source is unreachable") from exc
    raise HTTPException(status_code=508, detail="Source exceeded the redirect limit")


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</(p|div|li|h[1-6]|tr)>", "\n", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@router.post("/api/research/fetch")
def research_fetch(body: ResearchUrlBody, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    try:
        response, final_url = _open_public_research_url(body.url)
        with response:
            content_type = response.headers.get("content-type", "")
            raw = response.read(1_000_001)
            final_url = response.geturl() or final_url
    except HTTPException:
        raise
    if len(raw) > 1_000_000:
        raise HTTPException(status_code=413, detail="Source is larger than the 1 MB research limit")
    charset_match = re.search(r"charset=([\w-]+)", content_type, flags=re.I)
    charset = charset_match.group(1) if charset_match else "utf-8"
    try:
        decoded = raw.decode(charset, errors="replace")
    except LookupError:
        decoded = raw.decode("utf-8", errors="replace")
    text = _html_to_text(decoded) if "html" in content_type.lower() else decoded.strip()
    safe_text, redacted = redact_secrets(text[:80_000])
    _audit(principal, event_type="research.url_fetched", payload={"host": urlparse(final_url).hostname, "chars": len(safe_text), "redacted": redacted})
    return {"url": final_url, "content_type": content_type, "text": safe_text, "truncated": len(text) > 80_000, "redacted": redacted, "browser_session": False}
