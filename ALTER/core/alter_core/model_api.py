from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .api import _audit, orchestrator, policy_store
from .auth import Principal, require_owner
from .botpress_gateway import BotpressGateway
from .local_model_catalog import LOCAL_MODEL_CATALOG, get_local_model
from .local_model_gateway import LocalModelGateway
from .models import ActionRequest, ActionRisk, TaskStatus
from .openai_agents_gateway import OpenAIAgentsGateway
from .orchestrator import InvalidTaskTransitionError

router = APIRouter()
gateway = BotpressGateway()
openai_gateway = OpenAIAgentsGateway()
local_gateway = LocalModelGateway()

Purpose = Literal[
    "chat", "reasoning", "planning", "summarization", "coding",
    "vision", "image", "video", "speech_to_text", "text_to_speech",
    "ocr", "retrieval",
]


class RouteModelBody(BaseModel):
    purpose: Purpose = "reasoning"
    mode: Literal["quick", "normal", "deep", "plan"] = "normal"


def _registry() -> list[dict[str, Any]]:
    status = gateway.status()
    openai_status = openai_gateway.status()
    local_status = local_gateway.status()
    live: list[dict[str, Any]] = [
        {
            "id": f"openai-{openai_status.model}",
            "provider": openai_status.provider,
            "display_name": f"ALTER · {openai_status.model}",
            "capabilities": ["chat", "reasoning", "planning", "summarization", "coding"],
            "configured": openai_status.configured,
            "credential_configured": openai_status.credential_configured,
            "action": openai_status.action,
            "side_effects": False,
            "policy_boundary": "core-policy-required",
            "source": "cloud",
            "install_state": "ready" if openai_status.configured else "credential_required",
            "license": "service",
            "requirements": "OpenAI API key in vault:openai_api or server runtime",
        },
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
    installed = set(local_status.installed_models)
    local: list[dict[str, Any]] = []
    for item in LOCAL_MODEL_CATALOG:
        installable = bool(item.get("runtime_ref"))
        configured = item["id"] in installed
        if configured:
            install_state = "ready"
        elif local_status.connected and installable:
            install_state = "available_to_install"
        elif local_status.configured and not local_status.connected and installable:
            install_state = "runtime_unreachable"
        elif not local_status.connected:
            install_state = "requires_local_runtime"
        elif not installable:
            install_state = "backend_not_added"
        else:
            install_state = "requires_local_runtime"
        local.append({
            **item,
            "provider": local_status.provider,
            "configured": configured,
            "credential_configured": local_status.credential_configured,
            "action": local_status.action if configured else "install-via-owner-runtime",
            "side_effects": False,
            "policy_boundary": "core-policy-required",
            "source": "local",
            "installable": installable,
            "install_state": install_state,
        })
    return [*live, *local]


@router.get("/models")
@router.get("/api/models")
def list_models(_principal: Principal = Depends(require_owner)) -> list[dict[str, Any]]:
    return _registry()


@router.get("/api/models/catalog")
def model_catalog(_principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    models = _registry()
    local_status = local_gateway.status()
    return {
        "models": models,
        "configured": sum(1 for model in models if model["configured"]),
        "local_runtime_connected": local_status.connected,
        "local_runtime": {
            "configured": local_status.configured,
            "connected": local_status.connected,
            "installed": len(local_status.installed_models),
            "active_jobs": local_status.active_jobs,
            "selected_model": local_status.model,
            "secret_exposed": False,
        },
        "installation_policy": "hardware-license-check-sandbox-benchmark-owner-trust",
    }


@router.post("/models/{model_id}/install-request")
@router.post("/api/models/{model_id}/install-request")
def request_model_install(
    model_id: str,
    principal: Principal = Depends(require_owner),
) -> dict[str, Any]:
    if principal.actor_role != "owner":
        raise HTTPException(status_code=403, detail="Only Owner can request a model installation")
    model = get_local_model(model_id)
    if model is None or not model.get("runtime_ref"):
        raise HTTPException(status_code=404, detail="Model is not available through an approved ALTER runtime")
    runtime = local_gateway.status()
    if not runtime.connected:
        raise HTTPException(status_code=503, detail="Connect an owner-controlled ALTER model runtime first")
    if model_id in runtime.installed_models:
        return {"already_installed": True, "model_id": model_id, "task": None}

    task = orchestrator.create_task(
        workspace_id=principal.workspace_id,
        owner_user_id=principal.user_id,
        objective=f"Install trusted local model {model['display_name']}",
        acceptance_criteria=[
            "Runtime accepts only the allowlisted immutable model reference.",
            "Owner approval digest is recorded before download starts.",
            "Installed model becomes visible in the live model registry.",
        ],
    )
    try:
        task = orchestrator.mark_ready(task.id)
        task = orchestrator.request_action(
            ActionRequest(
                workspace_id=principal.workspace_id,
                task_id=task.id,
                category="model_install",
                operation="pull_allowlisted_model",
                risk=ActionRisk.REVERSIBLE,
                target=model_id,
                parameters={
                    "runtime_ref": model["runtime_ref"],
                    "license": model["license"],
                    "requirements": model["requirements"],
                },
            ),
            owner_rules=policy_store.list_for_workspace(principal.workspace_id),
            owner_user_id=principal.user_id,
        )
    except InvalidTaskTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(
        principal,
        event_type="model.install_requested",
        task_id=task.id,
        payload={
            "model_id": model_id,
            "runtime_backend": model["runtime_backend"],
            "status": task.status.value,
            "owner_approval_required": task.status == TaskStatus.AWAITING_APPROVAL,
        },
    )
    return {
        "already_installed": False,
        "model_id": model_id,
        "task": task.model_dump(mode="json"),
        "owner_approval_required": task.status == TaskStatus.AWAITING_APPROVAL,
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
