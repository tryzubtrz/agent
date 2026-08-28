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
from .vault_store import VaultIntegrityError, VaultUnavailableError, load_secret

router = APIRouter()
botpress = BotpressGateway()

_POSTHOG_PROJECT_KEY = "phc_z9CGwpT6bvMMD3BNaqb3XMUfSHvDbqR2kfbNENKgvTrf"
_POSTHOG_CAPTURE_URL = "https://us.i.posthog.com/capture/"
_GITHUB_REPOSITORY_URL = "https://api.github.com/repos/tryzubtrz/agent"
_VERCEL_PROJECT_URL = "https://api.vercel.com/v9/projects/prj_1Zqum253Ac7DPRLMBV4U56HERp0W?teamId=team_gJ5e2cC36eMxaFiQTVL7LKGd"
_SECRET_WORDS = ("token", "secret", "password", "key", "cookie", "authorization")

ConnectorKey = Literal["neon", "posthog", "botpress", "github", "vercel"]


class TelemetryEventBody(BaseModel):
    event: Literal[
        "alter_connector_test",
        "alter_system_check",
        "alter_task_completed",
        "alter_task_failed",
        "alter_page_view",
        "alter_client_error",
    ]
    properties: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


def _credential(env_name: str, alias: str) -> str | None:
    env = os.getenv(env_name, "").strip()
    if env:
        return env
    try:
        return load_secret(alias)
    except (VaultUnavailableError, VaultIntegrityError):
        return None


def _safe_properties(properties: dict[str, str | int | float | bool | None]) -> dict[str, str | int | float | bool | None]:
    return {
        key[:80]: value
        for key, value in list(properties.items())[:30]
        if not any(secret_word in key.lower() for secret_word in _SECRET_WORDS)
    }


def capture_posthog_system_event(
    event: str,
    properties: dict[str, str | int | float | bool | None] | None = None,
    *,
    distinct_id: str = "alter-owner-system",
    surface: str = "core",
) -> dict[str, object]:
    safe_properties = _safe_properties(properties or {})
    payload = {
        "api_key": _POSTHOG_PROJECT_KEY,
        "event": event[:120],
        "properties": {
            "distinct_id": distinct_id[:120],
            "app": "ALTER",
            "surface": surface[:40],
            **safe_properties,
        },
    }
    request = Request(
        _POSTHOG_CAPTURE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "ALTER-Core/0.6"},
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
    return {"accepted": True, "connector": "posthog", "event": event[:120]}


def _provider_json(url: str, token: str, *, provider: str) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "ALTER-Connector-Gateway/0.6",
    }
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=12) as response:  # noqa: S310 - caller supplies only fixed provider URLs
            if int(response.status) < 200 or int(response.status) >= 300:
                raise HTTPException(status_code=502, detail=f"{provider} connector returned an unsuccessful response")
            value = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise HTTPException(status_code=503, detail=f"{provider} connector credential was rejected") from exc
        raise HTTPException(status_code=502, detail=f"{provider} connector self-test failed") from exc
    except (URLError, TimeoutError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"{provider} connector is unreachable or returned invalid data") from exc
    if not isinstance(value, dict):
        raise HTTPException(status_code=502, detail=f"{provider} connector returned invalid data")
    return value


def _gateway_registry() -> list[dict[str, Any]]:
    botpress_status = botpress.status()
    github_configured = bool(_credential("GITHUB_CONNECTOR_TOKEN", "vault:github_connector"))
    vercel_configured = bool(_credential("VERCEL_CONNECTOR_TOKEN", "vault:vercel_connector"))
    return [
        {
            "key": "neon",
            "label": "Neon Postgres",
            "status": "connected" if STORAGE_MODE == "postgres" else "degraded",
            "capabilities": ["tasks", "memory", "audit", "files_v1", "policies"],
            "credential_source": "server-database-runtime",
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
            "status": "connected" if botpress_status.configured else "credential_required",
            "capabilities": ["chat", "reasoning", "planning"],
            "credential_source": "vault:botpress_runtime",
            "write_boundary": "alterThink-only-no-side-effects",
        },
        {
            "key": "github",
            "label": "GitHub",
            "status": "connected" if github_configured else "credential_required",
            "capabilities": ["repository_read"],
            "credential_source": "vault:github_connector",
            "write_boundary": "read-only-self-test; mutations require separate policy-governed executor",
        },
        {
            "key": "vercel",
            "label": "Vercel",
            "status": "connected" if vercel_configured else "credential_required",
            "capabilities": ["project_read", "deployment_observation"],
            "credential_source": "vault:vercel_connector",
            "write_boundary": "read-only-self-test; deploy mutations remain outside runtime gateway",
        },
    ]


@router.get("/gateway/connectors")
@router.get("/api/gateway/connectors")
def gateway_connectors(_principal: Principal = Depends(require_owner)) -> list[dict[str, Any]]:
    return _gateway_registry()


@router.post("/gateway/connectors/{connector_key}/test")
@router.post("/api/gateway/connectors/{connector_key}/test")
def test_connector(connector_key: ConnectorKey, principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    if principal.actor_role != "owner":
        raise HTTPException(status_code=403, detail="Only Owner can run connector credential tests")

    if connector_key == "neon":
        if STORAGE_MODE != "postgres":
            raise HTTPException(status_code=503, detail="Neon/Postgres runtime is not connected")
        result: dict[str, Any] = {"connector": "neon", "ok": True, "storage": "postgres", "secret_exposed": False}
    elif connector_key == "posthog":
        captured = capture_posthog_system_event("alter_connector_test", {"connector": "posthog", "source": "runtime_self_test"})
        result = {"connector": "posthog", "ok": captured.get("accepted") is True, "secret_exposed": False}
    elif connector_key == "botpress":
        status = botpress.status()
        if not status.configured:
            raise HTTPException(status_code=503, detail="Botpress runtime credential is not configured")
        result = {"connector": "botpress", "ok": True, "action": status.action, "paid_model_call": False, "secret_exposed": False}
    elif connector_key == "github":
        token = _credential("GITHUB_CONNECTOR_TOKEN", "vault:github_connector")
        if not token:
            raise HTTPException(status_code=503, detail="GitHub runtime connector credential is not configured in ALTER Vault")
        provider = _provider_json(_GITHUB_REPOSITORY_URL, token, provider="GitHub")
        result = {
            "connector": "github",
            "ok": True,
            "repository": str(provider.get("full_name") or "tryzubtrz/agent")[:160],
            "private": bool(provider.get("private", True)),
            "default_branch": str(provider.get("default_branch") or "")[:100],
            "secret_exposed": False,
        }
    else:
        token = _credential("VERCEL_CONNECTOR_TOKEN", "vault:vercel_connector")
        if not token:
            raise HTTPException(status_code=503, detail="Vercel runtime connector credential is not configured in ALTER Vault")
        provider = _provider_json(_VERCEL_PROJECT_URL, token, provider="Vercel")
        result = {
            "connector": "vercel",
            "ok": True,
            "project_id": str(provider.get("id") or "")[:160],
            "project_name": str(provider.get("name") or "")[:160],
            "framework": str(provider.get("framework") or "")[:80],
            "secret_exposed": False,
        }

    _audit(principal, event_type="connector.self_test", payload={"connector": connector_key, "ok": True})
    return result


@router.post("/gateway/posthog/capture")
@router.post("/api/gateway/posthog/capture")
def capture_posthog_event(
    body: TelemetryEventBody,
    principal: Principal = Depends(require_owner),
) -> dict[str, object]:
    safe_properties = _safe_properties(body.properties)
    result = capture_posthog_system_event(
        body.event,
        safe_properties,
        distinct_id=f"alter-{principal.actor_role}-{principal.actor_id}"[:120],
        surface="web" if body.event in {"alter_page_view", "alter_client_error"} else "core",
    )
    _audit(
        principal,
        event_type="connector.posthog.capture",
        payload={"event": body.event, "property_count": len(safe_properties)},
    )
    return result
