from __future__ import annotations

import base64
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
from .botpress_gateway import BotpressGateway

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
    valid = (
        claims.get("iss") == _ISSUER
        and _AUDIENCE in audiences
        and claims.get("repository") == _REPOSITORY
        and claims.get("ref") == _REF
        and claims.get("workflow_ref") == _WORKFLOW_REF
        and claims.get("event_name") in {"schedule", "workflow_dispatch", "push"}
        and str(claims.get("sub") or "").startswith(f"repo:{_REPOSITORY}:")
        and now - 60 <= exp
        and now - 900 <= iat <= now + 60
    )
    if not valid:
        raise HTTPException(status_code=403, detail="Scheduler token claims do not match ALTER policy")
    return claims


@router.post("/api/scheduler/tick")
def github_scheduler_tick(authorization: str | None = Header(default=None, alias="Authorization")) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="GitHub OIDC bearer token required")
    claims = _verify_oidc(authorization.removeprefix("Bearer ").strip())
    principal = system_principal("github-actions-scheduler")
    result = tick_automations(principal)
    agent_status = BotpressGateway().status()
    return {
        **result,
        "scheduler": "github-actions-oidc",
        "repository": claims.get("repository"),
        "run_id": claims.get("run_id"),
        "static_scheduler_secret": False,
        "agent_configured": agent_status.configured,
        "agent_action": agent_status.action,
        "secret_exposed": False,
    }
