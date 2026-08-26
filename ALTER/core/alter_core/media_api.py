from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .api import _audit, _memory_fallback, memory_store
from .auth import Principal, require_owner
from .vault_store import VaultIntegrityError, VaultUnavailableError, load_secret

router = APIRouter()
_BASE = "https://api.dev.runwayml.com"
_VERSION = "2024-11-06"


class GenerateBody(BaseModel):
    kind: Literal["image", "video"]
    prompt: str = Field(min_length=1, max_length=1000)
    ratio: Literal["square", "landscape", "portrait"] = "square"
    duration: Literal[5, 10] = 5
    confirm_external_cost: bool = False


def _secret() -> str | None:
    env = os.getenv("RUNWAYML_API_SECRET", "").strip()
    if env: return env
    try: return load_secret("vault:runway")
    except (VaultUnavailableError, VaultIntegrityError): return None


def _put(principal: Principal, key: str, value: dict[str, Any]) -> None:
    if memory_store is not None:
        memory_store.upsert(workspace_id=principal.workspace_id, user_id=principal.user_id, namespace="media.job", key=key, value=value)
    else:
        _memory_fallback[(principal.workspace_id, principal.user_id, "media.job", key)] = value


def _call(path: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    secret = _secret()
    if not secret: raise HTTPException(status_code=503, detail="Runway provider credential is not configured in ALTER Vault")
    headers = {"Authorization": f"Bearer {secret}", "X-Runway-Version": _VERSION, "Accept": "application/json"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"; data = json.dumps(payload).encode("utf-8")
    request = Request(f"{_BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=25) as response:  # noqa: S310 - fixed Runway API host
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise HTTPException(status_code=502, detail=f"Runway API returned HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise HTTPException(status_code=502, detail="Runway API is unreachable") from exc


@router.get("/api/media/status")
def media_status(_principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    configured = bool(_secret())
    return {
        "provider": "runway",
        "configured": configured,
        "state": "ready" if configured else "credential_required",
        "capabilities": ["text_to_image", "text_to_video"],
        "cost_confirmation_required": True,
        "api_version": _VERSION,
        "output_persistence": "provider URLs are ephemeral; external durable object storage is not configured",
        "local_candidates": ["FLUX.1 schnell", "Wan2.1-T2V-1.3B"],
        "local_runtime_connected": False,
    }


@router.post("/api/media/generate")
def generate_media(body: GenerateBody, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    if principal.actor_role != "owner": raise HTTPException(status_code=403, detail="Only Owner can authorize external media credit usage")
    if not body.confirm_external_cost: raise HTTPException(status_code=409, detail="Explicit external credit confirmation is required")
    if not _secret(): raise HTTPException(status_code=503, detail="Runway provider credential is not configured in ALTER Vault")

    if body.kind == "image":
        ratios = {"square": "1024:1024", "landscape": "1920:1080", "portrait": "1080:1920"}
        payload = {"model": "gen4_image", "promptText": body.prompt, "ratio": ratios[body.ratio]}
        response = _call("/v1/text_to_image", method="POST", payload=payload)
    else:
        ratios = {"square": "1280:720", "landscape": "1280:720", "portrait": "720:1280"}
        payload = {"model": "gen4.5", "promptText": body.prompt, "ratio": ratios[body.ratio], "duration": body.duration}
        response = _call("/v1/text_to_video", method="POST", payload=payload)

    task_id = str(response.get("id") or "")
    if not task_id: raise HTTPException(status_code=502, detail="Media provider returned no task id")
    local_id = str(uuid4())
    record = {"id": local_id, "provider_task_id": task_id, "provider": "runway", "kind": body.kind, "prompt": body.prompt, "ratio": body.ratio, "duration": body.duration if body.kind == "video" else None, "status": "PENDING", "created_at": datetime.now(timezone.utc).isoformat(), "estimated_cost": response.get("estimatedCost")}
    _put(principal, local_id, record)
    _audit(principal, event_type="media.generation.started", payload={"media_id": local_id, "kind": body.kind, "provider": "runway", "cost_confirmed": True})
    return record


@router.get("/api/media/tasks/{provider_task_id}")
def media_task(provider_task_id: str, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    if principal.actor_role != "owner": raise HTTPException(status_code=403, detail="Only Owner can inspect media provider tasks")
    result = _call(f"/v1/tasks/{provider_task_id}")
    output = result.get("output") if isinstance(result.get("output"), list) else []
    _audit(principal, event_type="media.generation.checked", payload={"provider_task_id": provider_task_id, "status": result.get("status"), "output_count": len(output)})
    return {"id": result.get("id") or provider_task_id, "status": result.get("status"), "output": output, "failure": result.get("failure"), "provider": "runway", "output_urls_ephemeral": True}
