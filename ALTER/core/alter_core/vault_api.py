from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException

from .auth import Principal, require_owner
from .vault_store import VaultUnavailableError, bootstrap_public_key, secret_configured

router = APIRouter()

_FIXED_ALIASES = {
    "vault:core_api": ("ALTER_API_TOKEN", "core-auth", False),
    "vault:database": ("DATABASE_URL", "database", False),
    "vault:botpress_runtime": ("BOTPRESS_RUNTIME_TOKEN", "ai-runtime", True),
    "vault:owner_web_pin": ("ALTER_WEB_PIN", "owner-auth", False),
}


def _is_configured(alias: str, env_name: str, allow_runtime_vault: bool) -> tuple[bool, str]:
    if os.getenv(env_name, "").strip():
        return True, "server-environment"
    if allow_runtime_vault and secret_configured(alias):
        return True, "encrypted-runtime-vault"
    return False, "not-configured"


@router.get("/api/vault/bootstrap/public-key")
def vault_bootstrap_public_key() -> dict[str, object]:
    """Expose only the public sealing key used for one-way secret transfer into ALTER."""
    try:
        public_key = bootstrap_public_key()
    except VaultUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Runtime vault bootstrap key is unavailable.") from exc
    return {
        "version": 1,
        "algorithm": "X25519-HKDF-SHA256+A256GCM",
        "public_key": public_key,
        "value_exposed": False,
    }


@router.get("/vault/aliases")
@router.get("/api/vault/aliases")
def list_vault_aliases(_principal: Principal = Depends(require_owner)) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for alias, (env_name, purpose, allow_runtime_vault) in _FIXED_ALIASES.items():
        configured, source = _is_configured(alias, env_name, allow_runtime_vault)
        result.append(
            {
                "alias": alias,
                "purpose": purpose,
                "configured": configured,
                "source": source,
                "value_exposed": False,
            }
        )
    return result


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
    }
