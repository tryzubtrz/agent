from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .auth import Principal, require_owner
from .botpress_gateway import BotpressGateway, BotpressRuntimeError, BotpressUnavailableError

router = APIRouter()
gateway = BotpressGateway()


class ThinkBody(BaseModel):
    objective: str = Field(min_length=1, max_length=10_000)
    context: str = Field(default="", max_length=20_000)
    mode: Literal["quick", "normal", "deep", "plan"] = "normal"


@router.get("/agent/status")
@router.get("/api/agent/status")
def agent_status(_principal: Principal = Depends(require_owner)) -> dict[str, object]:
    status = gateway.status()
    return {
        "provider": "botpress",
        "configured": status.configured,
        "bot_id_configured": status.bot_id_configured,
        "credential_configured": status.credential_configured,
        "action": status.action,
        "side_effect_boundary": "core-policy-required",
    }


@router.post("/agent/think")
@router.post("/api/agent/think")
def agent_think(
    body: ThinkBody,
    _principal: Principal = Depends(require_owner),
) -> dict[str, object]:
    try:
        output = gateway.think(
            objective=body.objective,
            context=body.context,
            mode=body.mode,
        )
    except BotpressUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BotpressRuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    response = output.get("response")
    if not isinstance(response, str) or not response.strip():
        raise HTTPException(status_code=502, detail="Botpress specialist returned no usable response.")

    return {
        "provider": "botpress",
        "response": response,
        "side_effects_performed": False,
        "boundary": "core-policy-required",
    }
