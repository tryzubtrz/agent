from __future__ import annotations

import os

from fastapi import APIRouter, Depends

from .auth import Principal, require_owner

router = APIRouter()

_FIXED_ALIASES = {
    "vault:core_api": ("ALTER_API_TOKEN", "core-auth"),
    "vault:database": ("DATABASE_URL", "database"),
    "vault:botpress_runtime": ("BOTPRESS_RUNTIME_TOKEN", "ai-runtime"),
    "vault:owner_web_pin": ("ALTER_WEB_PIN", "owner-auth"),
}


@router.get("/vault/aliases")
@router.get("/api/vault/aliases")
def list_vault_aliases(_principal: Principal = Depends(require_owner)) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for alias, (env_name, purpose) in _FIXED_ALIASES.items():
        configured = bool(os.getenv(env_name, "").strip())
        result.append(
            {
                "alias": alias,
                "purpose": purpose,
                "configured": configured,
                "source": "server-environment",
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
    }
