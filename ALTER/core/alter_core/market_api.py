from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from .auth import Principal, require_owner
from .botpress_gateway import BotpressGateway

router = APIRouter()
botpress = BotpressGateway()


@router.get("/api/market")
def market(_principal: Principal = Depends(require_owner)) -> dict[str, Any]:
    specialist = botpress.status()
    entries = [
        {"id": "documents", "name": "Documents Parser", "kind": "skill", "status": "installed", "risk": "low", "permissions": ["owner-files"], "rollback": "built-in"},
        {"id": "browser-ocr", "name": "Tesseract.js OCR", "kind": "model-runtime", "status": "installed", "risk": "low", "permissions": ["selected-image"], "rollback": "remove-web-dependency"},
        {"id": "voice-browser", "name": "Browser Voice STT/TTS", "kind": "skill", "status": "installed", "risk": "low", "permissions": ["microphone-when-owner-allows"], "rollback": "settings-toggle"},
        {"id": "knowledge-lexical", "name": "Knowledge Search v1", "kind": "skill", "status": "installed", "risk": "low", "permissions": ["workspace-memory"], "rollback": "built-in"},
        {"id": "automations", "name": "Automation Scheduler", "kind": "skill", "status": "installed", "risk": "medium", "permissions": ["create-internal-task", "create-in-app-notification"], "rollback": "disable-automation"},
        {"id": "research-reader", "name": "Safe Public URL Reader", "kind": "connector", "status": "installed", "risk": "medium", "permissions": ["public-http-https-read"], "rollback": "built-in"},
        {"id": "botpress-specialist", "name": "ALTER Specialist", "kind": "model", "status": "installed" if specialist.configured else "credential_required", "risk": "low", "permissions": ["reasoning-only"], "rollback": "disable-vault-alias"},
        {"id": "local-model-pack", "name": "10 Local Models Pack", "kind": "model-pack", "status": "runtime_required", "risk": "medium", "permissions": ["local-runtime"], "rollback": "model-by-model"},
    ]
    return {
        "entries": entries,
        "policy": "verify-source-permissions-license-sandbox-before-trust",
        "arbitrary_remote_install": False,
        "excluded_now": ["android", "pc-control", "telegram", "gmail", "tiktok"],
    }
