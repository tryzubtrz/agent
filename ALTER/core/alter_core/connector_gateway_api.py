from __future__ import annotations

import json
import os
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .api import STORAGE_MODE, _audit
from .auth import Principal, require_owner
from .botpress_gateway import BotpressGateway

router = APIRouter()
botpress = BotpressGateway()

_POSTHOG_PROJECT_KEY = "phc_z9CGwpT6bvMMD3BNaqb3XMUfSHvDbqR2kfbNENKgvTrf"
_POSTHOG_CAPTURE_URL = "https://us.i.posthog.com/capture/"


class TelemetryEventBody(BaseModel):
    event: Literal[
        "alter_connector_test",
        "alter_system_check",
        "alter_task_completed",
        "alter_task_failed",
    ]
    properties: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


def _configured(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def _gateway_registry() -> list[dict[str, Any]]:
    botpress_status = botpress.status()
    return [
        {
            "key": "neon",
            "label": "Neon Postgres",
            "status": "connected" if STORAGE_MODE == "postgres" else "degraded",
            "capabilities": ["tasks", "memory", "audit", "files_v1", "policies"],
            "credential_source": "vault:database",
            "write_boundary": "core-owned-data-only",
        },
        {
            "key": "posthog",
            "label": "PostHog",
            "status": "connected",
            "capabilities": ["telemetry_capture"],
            "credential_source": "public-project-key",
            "write_boundary": "whitelisted-events-only",
        },
        {
            "key": "botpress",
            "label": "Botpress",
            "status": "connected" if botpress_status.configured else "available",
            "capabilities": ["chat", "reasoning", "planning"],
            "credential_source": "vault:botpress_runtime",
            "write_boundary": "alterThink-only-no-side-effects",
        },
        {
            "key": "github",
            "label": "GitHub",
            "status": "connected" if _configured("GITHUB_CONNECTOR_TOKEN") else "not_configured",
            "capabilities": ["repository_read", "workflow_dispatch"],
            "credential_source": "vault:github_connector",
            "write_boundary": "scoped-token-required",
        },
        {
            "key": "vercel",
            "label": "Vercel",
            "status": "connected" if _configured("VERCEL_CONNECTOR_TOKEN") else "not_configured",
            "capabilities": ["projects_read", "deployments_read", "deploy_trigger"],
            "credential_source": "vault:vercel_connector",
            "write_boundary": "scoped-token-required",
        },
    ]


@router.get("/gateway/connectors")
@router.get("/api/gateway/connectors")
def gateway_connectors(_principal: Principal = Depends(require_owner)) -> list[dict[str, Any]]:
    return _gateway_registry()


@router.post("/gateway/posthog/capture")
@router.post("/api/gateway/posthog/capture")
def capture_posthog_event(
    body: TelemetryEventBody,
    principal: Principal = Depends(require_owner),
) -> dict[str, object]:
    safe_properties = {
        key[:80]: value
        for key, value in list(body.properties.items())[:30]
        if not any(secret_word in key.lower() for secret_word in ("token", "secret", "password", "key", "cookie", "authorization"))
    }
    payload = {
        "api_key": _POSTHOG_PROJECT_KEY,
        "event": body.event,
        "properties": {
            "distinct_id": "alter-owner-system",
            "app": "ALTER",
            "surface": "core",
            **safe_properties,
        },
    }
    request = Request(
        _POSTHOG_CAPTURE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 - fixed PostHog HTTPS host
            status_code = int(response.status)
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"PostHog capture returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise HTTPException(status_code=502, detail="PostHog capture endpoint is unreachable") from exc

    if status_code < 200 or status_code >= 300:
        raise HTTPException(status_code=502, detail="PostHog capture was not accepted")

    _audit(
        principal,
        event_type="connector.posthog.capture",
        payload={"event": body.event, "property_count": len(safe_properties)},
    )
    return {"accepted": True, "connector": "posthog", "event": body.event}
