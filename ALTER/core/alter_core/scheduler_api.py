from __future__ import annotations

import base64
import hashlib
import json
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import APIRouter, Header, HTTPException

from .auth import system_principal
from .automation_tick_api import tick_automations
from .botpress_contract import BotpressContractError, validate_specialist_output
from .botpress_gateway import BotpressRuntimeError, BotpressUnavailableError
from .connector_gateway_api import capture_posthog_system_event
from .local_model_gateway import LocalModelRuntimeError, LocalModelUnavailableError
from .openai_agents_gateway import (
    OpenAIAgentsRuntimeError,
    OpenAIAgentsUnavailableError,
)
from .rag_engine import retrieve_rows
from .reasoning_gateway import ReasoningGateway

router = APIRouter()

_ISSUER = "https://token.actions.githubusercontent.com"
_AUDIENCE = "alter-scheduler"
_REPOSITORY = "tryzubtrz/agent"
_REF = "refs/heads/main"
_WORKFLOW_REF = "tryzubtrz/agent/.github/workflows/alter-scheduler.yml@refs/heads/main"
_JWKS_URL = f"{_ISSUER}/.well-known/jwks"


def _b64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _json_segment(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(_b64url(value).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - normalized auth failure
        raise HTTPException(status_code=401, detail="Invalid scheduler token") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=401, detail="Invalid scheduler token")
    return parsed


def _fetch_jwks() -> dict[str, Any]:
    try:
        request = Request(_JWKS_URL, headers={"Accept": "application/json", "User-Agent": "ALTER-Scheduler/1.0"})
        with urlopen(request, timeout=10) as response:  # noqa: S310 - fixed GitHub OIDC endpoint
            value = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="GitHub OIDC verification service is unavailable") from exc
    if not isinstance(value, dict) or not isinstance(value.get("keys"), list):
        raise HTTPException(status_code=503, detail="GitHub OIDC key set is invalid")
    return value


def _verify_oidc(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=401, detail="Invalid scheduler token")
    header = _json_segment(parts[0])
    claims = _json_segment(parts[1])
    if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
        raise HTTPException(status_code=401, detail="Unsupported scheduler token algorithm")

    jwk = next((item for item in _fetch_jwks()["keys"] if isinstance(item, dict) and item.get("kid") == header["kid"]), None)
    if jwk is None or jwk.get("kty") != "RSA":
        raise HTTPException(status_code=401, detail="Scheduler signing key was not found")
    try:
        n = int.from_bytes(_b64url(str(jwk["n"])), "big")
        e = int.from_bytes(_b64url(str(jwk["e"])), "big")
        public_key = rsa.RSAPublicNumbers(e, n).public_key()
        public_key.verify(_b64url(parts[2]), f"{parts[0]}.{parts[1]}".encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    except Exception as exc:  # noqa: BLE001 - normalized auth failure
        raise HTTPException(status_code=401, detail="Scheduler token signature is invalid") from exc

    now = int(time.time())
    exp = int(claims.get("exp") or 0)
    iat = int(claims.get("iat") or 0)
    audience = claims.get("aud")
    audiences = {audience} if isinstance(audience, str) else set(audience or []) if isinstance(audience, list) else set()
    subject = str(claims.get("sub") or "")
    valid = (
        claims.get("iss") == _ISSUER
        and _AUDIENCE in audiences
        and claims.get("repository") == _REPOSITORY
        and claims.get("ref") == _REF
        and claims.get("workflow_ref") == _WORKFLOW_REF
        and claims.get("event_name") in {"schedule", "workflow_dispatch", "push"}
        and subject.startswith("repo:")
        and subject.endswith(f":ref:{_REF}")
        and now - 60 <= exp
        and now - 900 <= iat <= now + 60
    )
    if not valid:
        raise HTTPException(status_code=403, detail="Scheduler token claims do not match ALTER policy")
    return claims


def _claims_from_authorization(authorization: str | None) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="GitHub OIDC bearer token required")
    return _verify_oidc(authorization.removeprefix("Bearer ").strip())


@router.post("/api/scheduler/tick")
def github_scheduler_tick(authorization: str | None = Header(default=None, alias="Authorization")) -> dict[str, Any]:
    claims = _claims_from_authorization(authorization)
    principal = system_principal("github-actions-scheduler")
    result = tick_automations(principal)
    agent_status = ReasoningGateway().status()
    telemetry_state = "accepted"
    try:
        capture_posthog_system_event(
            "alter_system_check",
            {"source": "scheduler_tick", "storage": "postgres", "agent_configured": agent_status.configured},
            distinct_id="alter-scheduler",
            surface="core",
        )
    except HTTPException:
        telemetry_state = "degraded"
    return {
        **result,
        "scheduler": "github-actions-oidc",
        "repository": claims.get("repository"),
        "run_id": claims.get("run_id"),
        "static_scheduler_secret": False,
        "agent_configured": agent_status.configured,
        "agent_provider": agent_status.provider,
        "agent_action": agent_status.action,
        "telemetry": telemetry_state,
        "secret_exposed": False,
    }


@router.post("/api/scheduler/smoke")
def github_production_smoke(authorization: str | None = Header(default=None, alias="Authorization")) -> dict[str, Any]:
    claims = _claims_from_authorization(authorization)

    synthetic_rows = [
        {"namespace": "documents", "key": "smoke-doc", "value": {"text": "ALTER smoke knowledge phrase cobalt orchard"}},
        {"namespace": "vault_secure", "key": "smoke-secret", "value": {"text": "cobalt orchard must never leak from vault"}},
    ]
    rag_hits = retrieve_rows(synthetic_rows, "cobalt orchard", limit=5)
    rag_ok = bool(rag_hits) and any(item.get("key") == "smoke-doc" for item in rag_hits) and all(
        item.get("namespace") != "vault_secure" for item in rag_hits
    )
    if not rag_ok:
        raise HTTPException(status_code=500, detail="Secret-safe RAG smoke failed")

    gateway = ReasoningGateway()
    status = gateway.status()
    if not status.configured:
        raise HTTPException(status_code=503, detail="No ALTER reasoning runtime is configured")
    try:
        output = gateway.think(
            objective="Reply with a brief confirmation that ALTER specialist reasoning is online. Do not perform or claim any side effect.",
            context="Production smoke from GitHub OIDC through ALTER Core and Vault.",
            mode="quick",
        )
        response = validate_specialist_output(output)
    except (BotpressUnavailableError, OpenAIAgentsUnavailableError, LocalModelUnavailableError) as exc:
        raise HTTPException(status_code=503, detail="ALTER reasoning runtime is unavailable") from exc
    except (BotpressRuntimeError, OpenAIAgentsRuntimeError, LocalModelRuntimeError, BotpressContractError) as exc:
        raise HTTPException(status_code=502, detail="ALTER reasoning production smoke failed") from exc

    telemetry = capture_posthog_system_event(
        "alter_system_check",
        {
            "source": "production_smoke",
            "reasoning_ok": True,
            "provider": status.provider,
            "rag_ok": True,
            "secret_exposed": False,
        },
        distinct_id="alter-production-smoke",
        surface="core",
    )

    return {
        "ok": True,
        "scheduler_oidc": True,
        "repository": claims.get("repository"),
        "run_id": claims.get("run_id"),
        "reasoning": {
            "configured": True,
            "contract_ok": True,
            "provider": status.provider,
            "model": status.model,
            "action": status.action,
            "boundary": output.get("boundary"),
            "side_effects_performed": output.get("sideEffectsPerformed"),
            "response_present": bool(response),
            "response_sha256": hashlib.sha256(response.encode("utf-8")).hexdigest(),
        },
        "rag": {"ok": True, "engine": "secret-safe-rag-v2", "hits": len(rag_hits)},
        "telemetry": telemetry,
        "secret_exposed": False,
    }
