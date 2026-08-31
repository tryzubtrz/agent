from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends

from .api import STORAGE_MODE, connector_store, task_store
from .auth import Principal, require_owner
from .reasoning_gateway import ReasoningGateway

router = APIRouter()
gateway = ReasoningGateway()


def _capability(
    number: int,
    key: str,
    label: str,
    status: str,
    evidence: str,
    next_step: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "number": number,
        "key": key,
        "label": label,
        "status": status,
        "evidence": evidence,
    }
    if next_step:
        item["next_step"] = next_step
    return item


def _catalog(principal: Principal) -> list[dict[str, Any]]:
    agent = gateway.status()
    connectors: list[dict[str, Any]] = []
    if connector_store is not None:
        connectors = connector_store.list_for_workspace(principal.workspace_id)

    vault_envs = (
        "ALTER_API_TOKEN",
        "DATABASE_URL",
        "BOTPRESS_RUNTIME_TOKEN",
        "OPENAI_API_KEY",
        "ALTER_WEB_PIN",
    )
    vault_configured = sum(1 for name in vault_envs if os.getenv(name, "").strip())
    storage_ready = STORAGE_MODE == "postgres"

    return [
        _capability(1, "self_audit", "Чесний самоаудит", "ready", "Owner-only /api/system/status + this capability audit endpoint."),
        _capability(2, "remote_pc", "Remote Desktop & Console", "waiting", "No healthy owner PC/shell executor is registered in production.", "Connect an owner-controlled host runtime with heartbeat, scoped filesystem and shell permissions."),
        _capability(3, "browser", "Shared Chromium live session", "deferred", "Browser side-effect executor is intentionally not enabled.", "Provision isolated Chromium runtime, live-view and owner auth handoff."),
        _capability(4, "android", "Virtual Android / AVD", "deferred", "Android/ADB executor is intentionally not enabled.", "Provision isolated AVD host, ADB policy boundary and live stream."),
        _capability(5, "policy_menu", "Кімната правил", "ready", "Policy store, policy evaluation and owner UI are present."),
        _capability(6, "model_install", "Автономне встановлення reasoning-моделей", "waiting", "Local model catalog exists, but no verified CPU/GPU runtime is connected.", "Connect model host and require hardware/license/sandbox/benchmark checks before trust."),
        _capability(7, "self_patching", "Self-Patching", "partial", "GitHub/Vercel delivery workflow exists, but ALTER does not yet own a general-purpose production coding executor.", "Bind a scoped GitHub coding executor with tests, checkpoint and deploy verification."),
        _capability(8, "connector_builder", "Автоматична розбудова конекторів", "partial", f"Connector gateway exists; {len(connectors)} connector records are currently visible to the workspace.", "Add connector scaffolder + OAuth/credential workflow generator behind approvals."),
        _capability(9, "vault", "Secrets Firewall & Vault aliases", "ready" if vault_configured >= 2 else "waiting", f"{vault_configured}/{len(vault_envs)} server-side aliases are configured; raw-secret exposure is forbidden."),
        _capability(10, "approvals", "Approval Cards", "ready", "Owner-scoped approval API with action digest validation is present."),
        _capability(11, "voice", "Двохрежимний голосовий контур", "planned", "No verified end-to-end dictation + live duplex voice runtime is registered."),
        _capability(12, "content_pipeline", "Універсальний content pipeline", "partial", "Media/productivity surfaces exist; autonomous multi-provider generation and publishing are not verified end-to-end."),
        _capability(13, "finance", "Гібридне управління фінансами", "planned", "No production financial execution connector is declared by this audit."),
        _capability(14, "model_sandbox", "Sandbox-тестування моделей", "planned", "Model catalog is present; benchmark sandbox executor is not connected."),
        _capability(15, "model_inspector", "Порівняльний інспектор моделей", "partial", "Models UI/catalog and routing exist; live benchmark comparison is not yet wired."),
        _capability(16, "memory", "Трирівнева структурована пам'ять", "ready" if storage_ready else "degraded", f"Memory v2/admin APIs are mounted; storage mode is {STORAGE_MODE}."),
        _capability(17, "rbac", "RBAC Owner / Partner / Guest", "ready", "Access and member-auth routers are mounted with owner boundaries and revocation checks."),
        _capability(18, "self_healing", "Self-Healing", "partial", "Task model includes recovery states and executor recovery paths; deterministic host watchdog is not yet registered."),
        _capability(19, "morning_brief", "Проактивний ранковий brief", "partial", "Scheduler/productivity APIs exist; a verified owner-configured daily brief workflow is not guaranteed by core alone."),
        _capability(20, "local_coding", "Автономний coding у локальних репозиторіях", "waiting", "No healthy local shell/IDE executor is registered."),
        _capability(21, "visual_action", "Visual Action Agent", "planned", "No browser/Android vision click executor is connected."),
        _capability(22, "zip_inspection", "ZIP inspection & safe unpack", "planned", "Document ingestion exists, but a dedicated sandboxed ZIP extraction contract is not verified."),
        _capability(23, "audit_timeline", "Task audit timeline", "ready" if storage_ready else "degraded", f"Audit events are persisted through the configured {STORAGE_MODE} storage boundary."),
        _capability(24, "checkpoints", "Checkpoints & rollback", "planned", "Git revisions exist externally, but task-level atomic runtime checkpoints are not exposed as a verified capability."),
        _capability(25, "scheduler", "Cron Scheduler", "ready" if storage_ready else "degraded", "Scheduler and automation tick routers are mounted."),
        _capability(26, "fact_check", "Багатоджерельний фактчекінг", "partial", f"Reasoning provider is {agent.provider}; mandatory multi-source retrieval is not enforced for every answer."),
        _capability(27, "ocr", "OCR & document structuring", "partial", "Document pipeline exists and OCR candidates are catalogued; dedicated local OCR runtime is not verified."),
        _capability(28, "market", "Market Sandbox", "partial", "Market API is mounted; automatic install/test/trust lifecycle for arbitrary plugins is not complete."),
        _capability(29, "hard_stop", "Emergency Hard-Stop", "planned", "No global verified kill-switch endpoint currently owns all remote workers/sessions."),
        _capability(30, "personalization", "Глибока персоналізація", "partial", "Persistent memory and owner context exist; automatic preference learning remains bounded and editable."),
    ]


@router.get("/system/capabilities")
@router.get("/api/system/capabilities")
def system_capabilities(principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    capabilities = _catalog(principal)
    counts: dict[str, int] = {}
    for capability in capabilities:
        status = str(capability["status"])
        counts[status] = counts.get(status, 0) + 1

    return {
        "spec_version": "1.0",
        "runtime_truth_contract": True,
        "agent_configured": gateway.status().configured,
        "agent_provider": gateway.status().provider,
        "storage": STORAGE_MODE,
        "counts": counts,
        "capabilities": capabilities,
    }
