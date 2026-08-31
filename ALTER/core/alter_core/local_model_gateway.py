from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .botpress_contract import REQUIRED_SPECIALIST_BOUNDARY
from .local_model_catalog import get_local_model, installable_model_ids
from .vault_store import VaultIntegrityError, VaultUnavailableError, load_secret


class LocalModelUnavailableError(RuntimeError):
    pass


class LocalModelRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class LocalModelGatewayStatus:
    configured: bool
    connected: bool
    credential_configured: bool
    installed_models: tuple[str, ...]
    active_jobs: int
    model: str | None
    provider: str = "local-ollama"
    action: str = "localReason"


class LocalModelGateway:
    """Secret-safe client for an owner-controlled, allowlisted model runtime."""

    VAULT_ALIAS = "vault:local_model_runtime"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        default_model: str | None = None,
        timeout: float = 3.0,
    ) -> None:
        self.base_url = (base_url if base_url is not None else os.getenv("ALTER_MODEL_RUNTIME_URL", "")).strip().rstrip("/")
        self._explicit_token = token
        self.default_model = (
            default_model if default_model is not None else os.getenv("ALTER_LOCAL_MODEL_ID", "qwen3-8b")
        ).strip()
        self.timeout = timeout

    def _resolve_token(self) -> str:
        if self._explicit_token is not None:
            return self._explicit_token.strip()
        env_token = os.getenv("ALTER_MODEL_RUNTIME_TOKEN", "").strip()
        if env_token:
            return env_token
        try:
            return (load_secret(self.VAULT_ALIAS) or "").strip()
        except (VaultUnavailableError, VaultIntegrityError):
            return ""

    def _safe_url(self) -> bool:
        if not self.base_url:
            return False
        parsed = urlparse(self.base_url)
        if parsed.scheme == "https" and parsed.netloc:
            return True
        return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}

    def _request(self, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        token = self._resolve_token()
        if not self._safe_url() or not token:
            raise LocalModelUnavailableError("ALTER local model runtime is not securely configured.")
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "ALTER-Core/1.0",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - validated owner runtime URL
                value = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise LocalModelUnavailableError("ALTER local model runtime rejected its credential.") from exc
            raise LocalModelRuntimeError("ALTER local model runtime returned an error.") from exc
        except (URLError, TimeoutError, ValueError) as exc:
            raise LocalModelUnavailableError("ALTER local model runtime is unreachable.") from exc
        if not isinstance(value, dict):
            raise LocalModelRuntimeError("ALTER local model runtime returned an invalid response.")
        return value

    def status(self) -> LocalModelGatewayStatus:
        token = self._resolve_token()
        configured = bool(token and self._safe_url())
        if not configured:
            return LocalModelGatewayStatus(
                configured=False,
                connected=False,
                credential_configured=bool(token),
                installed_models=(),
                active_jobs=0,
                model=None,
            )
        try:
            value = self._request("/health")
        except (LocalModelUnavailableError, LocalModelRuntimeError):
            return LocalModelGatewayStatus(
                configured=True,
                connected=False,
                credential_configured=True,
                installed_models=(),
                active_jobs=0,
                model=None,
            )
        allowed = installable_model_ids()
        installed = tuple(
            item for item in value.get("installed_models", [])
            if isinstance(item, str) and item in allowed
        )
        selected = self.default_model if self.default_model in installed else installed[0] if installed else None
        raw_active_jobs = value.get("active_jobs", 0)
        try:
            active_jobs = max(0, int(raw_active_jobs))
        except (TypeError, ValueError):
            active_jobs = 0
        return LocalModelGatewayStatus(
            configured=True,
            connected=value.get("status") == "ok",
            credential_configured=True,
            installed_models=installed,
            active_jobs=active_jobs,
            model=selected,
        )

    def start_install(self, *, model_id: str, approval_digest: str) -> dict[str, Any]:
        model = get_local_model(model_id)
        if model is None or not model.get("runtime_ref"):
            raise LocalModelRuntimeError("Requested model is not in the ALTER install allowlist.")
        if len(approval_digest) != 64:
            raise LocalModelRuntimeError("Model installation approval digest is invalid.")
        value = self._request(
            f"/v1/models/{model_id}/pull",
            method="POST",
            payload={"approval_digest": approval_digest},
        )
        job_id = value.get("job_id")
        state = value.get("state")
        if not isinstance(job_id, str) or state not in {"queued", "running", "installed"}:
            raise LocalModelRuntimeError("Local model runtime did not accept the installation job.")
        return {"job_id": job_id, "state": state, "model_id": model_id, "secret_exposed": False}

    def think(self, *, objective: str, context: str = "", mode: str = "normal") -> dict[str, Any]:
        status = self.status()
        if not status.connected or not status.model:
            raise LocalModelUnavailableError("No trusted installed local model is available.")
        value = self._request(
            "/v1/chat",
            method="POST",
            payload={"model_id": status.model, "objective": objective, "context": context, "mode": mode},
        )
        response = value.get("response")
        if not isinstance(response, str) or not response.strip():
            raise LocalModelRuntimeError("Local model runtime returned no usable ALTER response.")
        return {
            "response": response.strip(),
            "sideEffectsPerformed": False,
            "boundary": REQUIRED_SPECIALIST_BOUNDARY,
        }
