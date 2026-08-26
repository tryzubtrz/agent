from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .auth import Principal, require_owner
from .botpress_gateway import BotpressGateway

router = APIRouter()
gateway = BotpressGateway()

Purpose = Literal[
    "chat", "reasoning", "planning", "summarization", "coding",
    "vision", "image", "video", "speech_to_text", "text_to_speech",
    "ocr", "retrieval",
]


class RouteModelBody(BaseModel):
    purpose: Purpose = "reasoning"
    mode: Literal["quick", "normal", "deep", "plan"] = "normal"


_LOCAL_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": "qwen3-8b",
        "display_name": "Qwen3-8B",
        "capabilities": ["chat", "reasoning", "planning", "summarization"],
        "license": "Apache-2.0",
        "requirements": "16 GB RAM or ~8 GB VRAM for a practical Q4 setup",
    },
    {
        "id": "deepseek-r1-distill-qwen-14b",
        "display_name": "DeepSeek-R1-Distill-Qwen-14B",
        "capabilities": ["reasoning", "planning"],
        "license": "checkpoint license must be verified before install",
        "requirements": "16–24 GB RAM or ~12–16 GB VRAM in Q4",
    },
    {
        "id": "qwen2.5-coder-7b-instruct",
        "display_name": "Qwen2.5-Coder-7B-Instruct",
        "capabilities": ["coding", "reasoning"],
        "license": "Apache-2.0",
        "requirements": "16 GB RAM or ~8 GB VRAM in Q4",
    },
    {
        "id": "qwen3-vl-8b-instruct",
        "display_name": "Qwen3-VL-8B-Instruct",
        "capabilities": ["vision", "ocr"],
        "license": "Apache-2.0",
        "requirements": "12–16 GB VRAM recommended",
    },
    {
        "id": "bge-m3",
        "display_name": "BGE-M3",
        "capabilities": ["retrieval"],
        "license": "MIT",
        "requirements": "4–8 GB system RAM; GPU optional",
    },
    {
        "id": "flux-1-schnell",
        "display_name": "FLUX.1 [schnell]",
        "capabilities": ["image"],
        "license": "Apache-2.0",
        "requirements": "~12 GB VRAM comfortable; CPU offload is slower",
    },
    {
        "id": "wan2.1-t2v-1.3b",
        "display_name": "Wan2.1-T2V-1.3B",
        "capabilities": ["video"],
        "license": "Apache-2.0",
        "requirements": "~8.2 GB VRAM for 480p-class use",
    },
    {
        "id": "whisper-turbo",
        "display_name": "Whisper Turbo",
        "capabilities": ["speech_to_text"],
        "license": "MIT",
        "requirements": "~6 GB VRAM; CPU supported but slower",
    },
    {
        "id": "kokoro-82m",
        "display_name": "Kokoro-82M",
        "capabilities": ["text_to_speech"],
        "license": "Apache-2.0",
        "requirements": "CPU-capable; Ukrainian voice quality requires validation",
    },
    {
        "id": "paddleocr",
        "display_name": "PaddleOCR / PaddleOCR-VL",
        "capabilities": ["ocr", "vision"],
        "license": "Apache-2.0",
        "requirements": "base OCR can run on CPU; VL path benefits from 8–12 GB VRAM",
    },
)


def _registry() -> list[dict[str, Any]]:
    status = gateway.status()
    live: list[dict[str, Any]] = [
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
            "source": "cloud",
            "install_state": "ready" if status.configured else "credential_required",
            "license": "service",
            "requirements": "Botpress Runtime credential in ALTER Vault",
        }
    ]
    local = [
        {
            **item,
            "provider": "local",
            "configured": False,
            "credential_configured": False,
            "action": "local-runtime-required",
            "side_effects": False,
            "policy_boundary": "core-policy-required",
            "source": "local",
            "install_state": "requires_local_runtime",
        }
        for item in _LOCAL_CATALOG
    ]
    return [*live, *local]


@router.get("/models")
@router.get("/api/models")
def list_models(_principal: Principal = Depends(require_owner)) -> list[dict[str, Any]]:
    return _registry()


@router.get("/api/models/catalog")
def model_catalog(_principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    models = _registry()
    return {
        "models": models,
        "configured": sum(1 for model in models if model["configured"]),
        "local_runtime_connected": False,
        "installation_policy": "hardware-license-check-sandbox-benchmark-owner-trust",
    }


@router.post("/models/route")
@router.post("/api/models/route")
def route_model(
    body: RouteModelBody,
    _principal: Principal = Depends(require_owner),
) -> dict[str, object]:
    providers = [item for item in _registry() if item["configured"] and body.purpose in item["capabilities"]]
    if not providers:
        candidates = [item["id"] for item in _registry() if body.purpose in item["capabilities"]]
        raise HTTPException(
            status_code=503,
            detail={
                "message": "No configured production model is available for this purpose",
                "purpose": body.purpose,
                "known_candidates": candidates,
            },
        )
    selected = providers[0]
    return {
        "selected": selected["id"],
        "provider": selected["provider"],
        "purpose": body.purpose,
        "mode": body.mode,
        "reason": "Selected from configured production-capable ALTER providers only",
    }
