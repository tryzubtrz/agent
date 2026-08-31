from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .api import _audit
from .auth import Principal, require_owner
from .vault_store import (
    VaultUnavailableError,
    bootstrap_public_key,
    secret_configured,
    store_secret,
)

router = APIRouter()

_FIXED_ALIASES = {
    "vault:core_api": ("ALTER_API_TOKEN", "core-auth", False),
    "vault:database": ("DATABASE_URL", "database", False),
    "vault:botpress_runtime": ("BOTPRESS_RUNTIME_TOKEN", "ai-runtime", True),
    "vault:openai_api": ("OPENAI_API_KEY", "openai-agents-sdk", True),
    "vault:local_model_runtime": ("ALTER_MODEL_RUNTIME_TOKEN", "local-model-runtime", True),
    "vault:runway": ("RUNWAYML_API_SECRET", "media-generation", True),
    "vault:owner_web_pin": ("ALTER_WEB_PIN", "owner-auth", False),
}
_OWNER_WRITABLE = {
    "vault:botpress_runtime",
    "vault:openai_api",
    "vault:local_model_runtime",
    "vault:runway",
}


class SecretWriteBody(BaseModel):
    value: str = Field(min_length=8, max_length=20_000)


def _is_configured(alias: str, env_name: str, allow_runtime_vault: bool) -> tuple[bool, str]:
    if os.getenv(env_name, "").strip():
        return True, "server-environment"
    if allow_runtime_vault and secret_configured(alias):
        return True, "encrypted-runtime-vault"
    return False, "not-configured"


@router.get("/api/vault/bootstrap/public-key")
def vault_bootstrap_public_key() -> dict[str, object]:
    try:
        public_key = bootstrap_public_key()
    except VaultUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Runtime vault bootstrap key is unavailable.") from exc
    return {"version": 1, "algorithm": "X25519-HKDF-SHA256+A256GCM", "public_key": public_key, "value_exposed": False}


@router.get("/vault/aliases")
@router.get("/api/vault/aliases")
def list_vault_aliases(_principal: Principal = Depends(require_owner)) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for alias, (env_name, purpose, allow_runtime_vault) in _FIXED_ALIASES.items():
        configured, source = _is_configured(alias, env_name, allow_runtime_vault)
        result.append({
            "alias": alias,
            "purpose": purpose,
            "configured": configured,
            "source": source,
            "owner_writable": alias in _OWNER_WRITABLE,
            "value_exposed": False,
        })
    return result


@router.put("/api/vault/secrets/{alias_name}")
def write_runtime_secret(alias_name: str, body: SecretWriteBody, principal: Principal = Depends(require_owner)) -> dict[str, object]:
    if principal.actor_role != "owner":
        raise HTTPException(status_code=403, detail="Only Owner can write ALTER Vault secrets")
    alias = f"vault:{alias_name.strip()}"
    if alias not in _OWNER_WRITABLE:
        raise HTTPException(status_code=403, detail="This Vault alias is server-managed and cannot be changed from the web UI")
    value = body.value.strip()
    if len(value) < 8:
        raise HTTPException(status_code=422, detail="Secret value is too short")
    try:
        store_secret(alias, value)
    except VaultUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Encrypted runtime Vault is unavailable") from exc
    _audit(principal, event_type="vault.secret.rotated", payload={"alias": alias, "rotated_at": datetime.now(timezone.utc).isoformat(), "value_exposed": False})
    return {"alias": alias, "configured": True, "source": "encrypted-runtime-vault", "value_exposed": False}


@router.get("/vault/health")
@router.get("/api/vault/health")
def vault_health(_principal: Principal = Depends(require_owner)) -> dict[str, object]:
    aliases = list_vault_aliases(_principal)
    return {
        "status": "ok",
        "aliases": len(aliases),
        "configured": sum(1 for item in aliases if item["configured"]),
        "raw_secret_exposure": False,
        "encrypted_runtime_storage": True,
        "bootstrap_transport": "sealed-public-key-only",
        "owner_rotation": True,
    }
