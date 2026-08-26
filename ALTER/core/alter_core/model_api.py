from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .auth import Principal, require_owner
from .botpress_gateway import BotpressGateway

router = APIRouter()
gateway = BotpressGateway()


class RouteModelBody(BaseModel):
    purpose: Literal["chat", "reasoning", "planning", "summarization", "coding"] = "reasoning"
    mode: Literal["quick", "normal", "deep", "plan"] = "normal"


def _registry() -> list[dict[str, object]]:
    status = gateway.status()
    return [
        {
            "id": "botpress-alter-think",
            "provider": "botpress",
            "display_name": "ALTER Specialist",
            "capabilities": ["chat", "reasoning", "planning", "summarization", "coding"],
            "configured": status.configured,
            "credential_configured": status.credential_configured,
            "action": status.action,
            "side_effects": False,
            "policy_boundary": "core-policy-required",
        }
    ]


@router.get("/models")
@router.get("/api/models")
def list_models(_principal: Principal = Depends(require_owner)) -> list[dict[str, object]]:
    return _registry()


@router.post("/models/route")
@router.post("/api/models/route")
def route_model(
    body: RouteModelBody,
    _principal: Principal = Depends(require_owner),
) -> dict[str, object]:
    providers = [item for item in _registry() if item["configured"] and body.purpose in item["capabilities"]]
    if not providers:
        raise HTTPException(status_code=503, detail="No configured production model is available for this purpose")
    selected = providers[0]
    return {
        "selected": selected["id"],
        "provider": selected["provider"],
        "purpose": body.purpose,
        "mode": body.mode,
        "reason": "Only configured production-capable ALTER specialist currently available",
    }
