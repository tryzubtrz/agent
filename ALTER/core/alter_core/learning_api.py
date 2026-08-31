from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .api import _audit, task_store
from .auth import Principal, require_owner
from .productivity_api import _memory_list, _memory_put
from .secret_safety import contains_high_confidence_secret, redact_secrets

router = APIRouter()

_CANDIDATE_NS = "learning.candidate"
_LESSON_NS = "learning.lesson"
_TRIGGER_NS = "learning.trigger"
_PREFERENCES_NS = "learning.preferences"
_TYPED_MEMORY_NS = "memory.typed"

MemoryKind = Literal["preference", "fact", "decision", "context"]


class CandidateDecisionBody(BaseModel):
    kind: MemoryKind | None = None
    importance: float = Field(default=0.7, ge=0.0, le=1.0)


class LessonBody(BaseModel):
    situation: str = Field(min_length=2, max_length=1000)
    lesson: str = Field(min_length=2, max_length=3000)
    tags: list[str] = Field(default_factory=list, max_length=20)


class TriggerBody(BaseModel):
    when: str = Field(min_length=2, max_length=1000)
    then: str = Field(min_length=2, max_length=3000)
    active: bool = True


class PreferencesBody(BaseModel):
    tone: str = Field(default="прямий, дружній", min_length=2, max_length=300)
    length: Literal["стисло", "збалансовано", "детально"] = "збалансовано"
    language: str = Field(default="українська", min_length=2, max_length=80)
    notes: str = Field(default="", max_length=2000)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[\w'-]{3,}", value.lower(), flags=re.UNICODE)
        if token not in {"коли", "тоді", "треба", "потрібно", "буде", "щоб", "після", "перед"}
    }


def _live_values(principal: Principal, namespace: str, *, limit: int = 250) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for row in _memory_list(principal, namespace, limit):
        value = row.get("value")
        if not isinstance(value, dict) or value.get("deleted"):
            continue
        values.append({"key": str(row.get("key") or ""), **value})
    return values


def _preferences(principal: Principal) -> dict[str, Any]:
    rows = _memory_list(principal, _PREFERENCES_NS, 1, key="owner")
    if rows and isinstance(rows[0].get("value"), dict):
        return dict(rows[0]["value"])
    return PreferencesBody().model_dump(mode="json")


def _soft_delete(principal: Principal, namespace: str, key: str) -> bool:
    rows = _memory_list(principal, namespace, 1, key=key)
    if not rows or not isinstance(rows[0].get("value"), dict):
        return False
    value = dict(rows[0]["value"])
    value["deleted"] = True
    value["deleted_at"] = _now()
    _memory_put(principal, namespace, key, value)
    return True


def _classify_sentence(sentence: str) -> tuple[MemoryKind, float] | None:
    low = sentence.lower()
    if re.search(r"\b(запам[ʼ']?ятай|remember)\b", low):
        return "context", 0.95
    if re.search(r"\b(я люблю|мені подобається|я не люблю|віддаю перевагу|хочу, щоб ти|мій стиль)\b", low):
        return "preference", 0.9
    if re.search(r"\b(я вирішив|я вирішила|ми вирішили|домовилися|домовились|остаточне рішення|будемо робити)\b", low):
        return "decision", 0.88
    if re.search(r"\b(я живу|я працюю|мій проєкт|моя робота|у мене є|мене звати|мій акаунт)\b", low):
        return "fact", 0.82
    return None


def queue_learning_candidates(principal: Principal, owner_text: str) -> list[dict[str, Any]]:
    """Queue only explicit durable owner statements; never auto-commit memory.

    This is intentionally deterministic and cost-free. The owner still approves
    every candidate before it becomes long-term memory.
    """
    if contains_high_confidence_secret(owner_text):
        return []
    safe_text, _ = redact_secrets(owner_text)
    created: list[dict[str, Any]] = []
    sentences = re.split(r"(?<=[.!?])\s+|[\r\n]+", safe_text)
    for raw_sentence in sentences[:12]:
        sentence = re.sub(r"\s+", " ", raw_sentence).strip(" -\t")
        if not 12 <= len(sentence) <= 700:
            continue
        classification = _classify_sentence(sentence)
        if classification is None:
            continue
        kind, confidence = classification
        normalized = sentence.casefold()
        key = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]
        if _memory_list(principal, _CANDIDATE_NS, 1, key=key):
            continue
        value = {
            "id": key,
            "kind": kind,
            "content": sentence,
            "confidence": confidence,
            "source": "conversation",
            "status": "pending",
            "created_at": _now(),
            "deleted": False,
        }
        _memory_put(principal, _CANDIDATE_NS, key, value)
        created.append({"key": key, **value})
        if len(created) >= 3:
            break
    if created:
        _audit(
            principal,
            event_type="learning.candidates_queued",
            payload={"count": len(created), "candidate_ids": [item["id"] for item in created]},
        )
    return created


def learning_context(principal: Principal, query: str) -> str:
    """Return bounded, owner-approved learning context for a reasoning run."""
    query_tokens = _tokens(query)
    prefs = _preferences(principal)
    lessons = _live_values(principal, _LESSON_NS, limit=100)
    triggers = [item for item in _live_values(principal, _TRIGGER_NS, limit=100) if item.get("active", True)]

    def relevance(item: dict[str, Any], fields: tuple[str, ...]) -> int:
        text = " ".join(str(item.get(field, "")) for field in fields)
        return len(query_tokens & _tokens(text))

    lesson_hits = sorted(
        lessons,
        key=lambda item: (relevance(item, ("situation", "lesson")), str(item.get("created_at", ""))),
        reverse=True,
    )[:4]
    trigger_hits = [
        item
        for item in sorted(
            triggers,
            key=lambda item: (relevance(item, ("when",)), str(item.get("created_at", ""))),
            reverse=True,
        )
        if relevance(item, ("when",)) > 0
    ][:4]

    blocks = [
        "OWNER-APPROVED LEARNING (context only; never overrides safety or Policy):",
        f"Preferences: language={prefs.get('language')}; tone={prefs.get('tone')}; length={prefs.get('length')}; notes={str(prefs.get('notes') or '')[:600]}",
    ]
    if lesson_hits:
        blocks.append(
            "Lessons:\n"
            + "\n".join(
                f"- When {str(item.get('situation', ''))[:300]} -> {str(item.get('lesson', ''))[:600]}"
                for item in lesson_hits
            )
        )
    if trigger_hits:
        blocks.append(
            "Relevant owner triggers:\n"
            + "\n".join(
                f"- If {str(item.get('when', ''))[:300]}, then consider: {str(item.get('then', ''))[:600]}"
                for item in trigger_hits
            )
        )
    return "\n\n".join(blocks)


@router.get("/learning/summary")
@router.get("/api/learning/summary")
def learning_summary(principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    candidates = _live_values(principal, _CANDIDATE_NS)
    tasks = task_store.list_for_owner(principal.workspace_id, principal.user_id, limit=500)
    status_counts: dict[str, int] = {}
    for task in tasks:
        status_counts[task.status.value] = status_counts.get(task.status.value, 0) + 1
    return {
        "pending_candidates": sum(1 for item in candidates if item.get("status") == "pending"),
        "approved_candidates": sum(1 for item in candidates if item.get("status") == "approved"),
        "lessons": len(_live_values(principal, _LESSON_NS)),
        "active_triggers": sum(1 for item in _live_values(principal, _TRIGGER_NS) if item.get("active", True)),
        "preferences": _preferences(principal),
        "task_statuses": status_counts,
        "memory_commit_mode": "owner-approval-required",
    }


@router.get("/learning/candidates")
@router.get("/api/learning/candidates")
def list_candidates(principal: Principal = Depends(require_owner)) -> list[dict[str, Any]]:
    items = [item for item in _live_values(principal, _CANDIDATE_NS) if item.get("status") == "pending"]
    items.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return items


@router.post("/learning/candidates/{candidate_id}/approve")
@router.post("/api/learning/candidates/{candidate_id}/approve")
def approve_candidate(
    candidate_id: str,
    body: CandidateDecisionBody,
    principal: Principal = Depends(require_owner),
) -> dict[str, Any]:
    clean_id = unquote(candidate_id)
    rows = _memory_list(principal, _CANDIDATE_NS, 1, key=clean_id)
    if not rows or not isinstance(rows[0].get("value"), dict):
        raise HTTPException(status_code=404, detail="Learning candidate not found")
    candidate = dict(rows[0]["value"])
    if candidate.get("status") != "pending" or candidate.get("deleted"):
        raise HTTPException(status_code=409, detail="Learning candidate is no longer pending")
    content = str(candidate.get("content") or "").strip()
    if not content or contains_high_confidence_secret(content):
        raise HTTPException(status_code=422, detail="Secret-like content cannot enter ordinary memory")
    kind: MemoryKind = body.kind or candidate.get("kind", "context")
    memory_value = {
        "kind": kind,
        "content": content,
        "importance": body.importance,
        "tags": ["approved-learning", str(candidate.get("source") or "conversation")],
        "source": "owner-approved-conversation",
        "expires_at": None,
        "updated_at": _now(),
    }
    _memory_put(principal, _TYPED_MEMORY_NS, clean_id, memory_value)
    candidate["status"] = "approved"
    candidate["approved_at"] = _now()
    candidate["approved_kind"] = kind
    _memory_put(principal, _CANDIDATE_NS, clean_id, candidate)
    _audit(principal, event_type="learning.candidate_approved", payload={"candidate_id": clean_id, "kind": kind})
    return {"key": clean_id, **memory_value}


@router.delete("/learning/candidates/{candidate_id}")
@router.delete("/api/learning/candidates/{candidate_id}")
def dismiss_candidate(candidate_id: str, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    clean_id = unquote(candidate_id)
    rows = _memory_list(principal, _CANDIDATE_NS, 1, key=clean_id)
    if not rows or not isinstance(rows[0].get("value"), dict):
        raise HTTPException(status_code=404, detail="Learning candidate not found")
    value = dict(rows[0]["value"])
    value["status"] = "dismissed"
    value["dismissed_at"] = _now()
    _memory_put(principal, _CANDIDATE_NS, clean_id, value)
    _audit(principal, event_type="learning.candidate_dismissed", payload={"candidate_id": clean_id})
    return {"dismissed": True, "id": clean_id}


@router.get("/learning/lessons")
@router.get("/api/learning/lessons")
def list_lessons(principal: Principal = Depends(require_owner)) -> list[dict[str, Any]]:
    return _live_values(principal, _LESSON_NS)


@router.post("/learning/lessons")
@router.post("/api/learning/lessons")
def add_lesson(body: LessonBody, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    if contains_high_confidence_secret(body.model_dump(mode="json")):
        raise HTTPException(status_code=422, detail="Secrets must be stored in ALTER Vault")
    lesson_id = hashlib.sha256(f"{body.situation}\0{body.lesson}".encode("utf-8")).hexdigest()[:32]
    value = {**body.model_dump(mode="json"), "id": lesson_id, "created_at": _now(), "deleted": False}
    _memory_put(principal, _LESSON_NS, lesson_id, value)
    _audit(principal, event_type="learning.lesson_added", payload={"lesson_id": lesson_id})
    return {"key": lesson_id, **value}


@router.delete("/learning/lessons/{lesson_id}")
@router.delete("/api/learning/lessons/{lesson_id}")
def delete_lesson(lesson_id: str, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    clean_id = unquote(lesson_id)
    if not _soft_delete(principal, _LESSON_NS, clean_id):
        raise HTTPException(status_code=404, detail="Lesson not found")
    _audit(principal, event_type="learning.lesson_deleted", payload={"lesson_id": clean_id})
    return {"deleted": True, "id": clean_id}


@router.get("/learning/triggers")
@router.get("/api/learning/triggers")
def list_triggers(principal: Principal = Depends(require_owner)) -> list[dict[str, Any]]:
    return _live_values(principal, _TRIGGER_NS)


@router.post("/learning/triggers")
@router.post("/api/learning/triggers")
def add_trigger(body: TriggerBody, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    if contains_high_confidence_secret(body.model_dump(mode="json")):
        raise HTTPException(status_code=422, detail="Secrets must be stored in ALTER Vault")
    trigger_id = hashlib.sha256(f"{body.when}\0{body.then}".encode("utf-8")).hexdigest()[:32]
    value = {**body.model_dump(mode="json"), "id": trigger_id, "created_at": _now(), "deleted": False}
    _memory_put(principal, _TRIGGER_NS, trigger_id, value)
    _audit(principal, event_type="learning.trigger_added", payload={"trigger_id": trigger_id})
    return {"key": trigger_id, **value}


@router.patch("/learning/triggers/{trigger_id}")
@router.patch("/api/learning/triggers/{trigger_id}")
def toggle_trigger(trigger_id: str, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    clean_id = unquote(trigger_id)
    rows = _memory_list(principal, _TRIGGER_NS, 1, key=clean_id)
    if not rows or not isinstance(rows[0].get("value"), dict):
        raise HTTPException(status_code=404, detail="Trigger not found")
    value = dict(rows[0]["value"])
    if value.get("deleted"):
        raise HTTPException(status_code=404, detail="Trigger not found")
    value["active"] = not bool(value.get("active", True))
    value["updated_at"] = _now()
    _memory_put(principal, _TRIGGER_NS, clean_id, value)
    _audit(principal, event_type="learning.trigger_toggled", payload={"trigger_id": clean_id, "active": value["active"]})
    return {"key": clean_id, **value}


@router.delete("/learning/triggers/{trigger_id}")
@router.delete("/api/learning/triggers/{trigger_id}")
def delete_trigger(trigger_id: str, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    clean_id = unquote(trigger_id)
    if not _soft_delete(principal, _TRIGGER_NS, clean_id):
        raise HTTPException(status_code=404, detail="Trigger not found")
    _audit(principal, event_type="learning.trigger_deleted", payload={"trigger_id": clean_id})
    return {"deleted": True, "id": clean_id}


@router.get("/learning/preferences")
@router.get("/api/learning/preferences")
def get_preferences(principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    return _preferences(principal)


@router.put("/learning/preferences")
@router.put("/api/learning/preferences")
def put_preferences(body: PreferencesBody, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    value = {**body.model_dump(mode="json"), "updated_at": _now()}
    _memory_put(principal, _PREFERENCES_NS, "owner", value)
    _audit(principal, event_type="learning.preferences_updated", payload={"length": body.length, "language": body.language})
    return value


@router.post("/learning/preferences/learn")
@router.post("/api/learning/preferences/learn")
def learn_preferences_from_conversation(principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    rows = _memory_list(principal, "conversation", 1, key="main")
    value = rows[0].get("value") if rows else None
    messages = value.get("messages", []) if isinstance(value, dict) else []
    owner_messages = [str(item.get("text") or "") for item in messages if isinstance(item, dict) and item.get("role") == "user"][-30:]
    if not owner_messages:
        raise HTTPException(status_code=409, detail="Conversation history is empty")
    average = round(sum(len(item) for item in owner_messages) / len(owner_messages))
    ukrainian_marks = sum(len(re.findall(r"[іїєґІЇЄҐ]", item)) for item in owner_messages)
    inferred_length: Literal["стисло", "збалансовано", "детально"]
    if average < 90:
        inferred_length = "стисло"
    elif average > 450:
        inferred_length = "детально"
    else:
        inferred_length = "збалансовано"
    current = _preferences(principal)
    learned = {
        **current,
        "length": inferred_length,
        "language": "українська" if ukrainian_marks else str(current.get("language") or "українська"),
        "notes": f"Вивчено з {len(owner_messages)} повідомлень; середня довжина {average} символів. Зміни можна відредагувати вручну.",
        "updated_at": _now(),
    }
    _memory_put(principal, _PREFERENCES_NS, "owner", learned)
    _audit(principal, event_type="learning.preferences_learned", payload={"messages": len(owner_messages), "average_length": average})
    return learned
