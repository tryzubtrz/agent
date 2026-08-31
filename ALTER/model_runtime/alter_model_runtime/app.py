from __future__ import annotations

import hmac
import json
import os
from datetime import datetime, timezone
from threading import RLock, Thread
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

CATALOG: dict[str, dict[str, str]] = {
    "qwen3-8b": {
        "runtime_ref": "qwen3:8b",
        "license": "Apache-2.0",
        "purpose": "general reasoning and Ukrainian conversation",
    },
    "deepseek-r1-distill-qwen-14b": {
        "runtime_ref": "deepseek-r1:14b",
        "license": "MIT checkpoint license",
        "purpose": "deep reasoning and planning",
    },
    "qwen2.5-coder-7b-instruct": {
        "runtime_ref": "qwen2.5-coder:7b",
        "license": "Apache-2.0",
        "purpose": "coding and code review",
    },
}

app = FastAPI(title="ALTER Model Runtime", version="0.1.0")
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = RLock()


class PullBody(BaseModel):
    approval_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class ChatBody(BaseModel):
    model_id: str
    objective: str = Field(min_length=1, max_length=20_000)
    context: str = Field(default="", max_length=30_000)
    mode: Literal["quick", "normal", "deep", "plan"] = "normal"


def _runtime_token() -> str:
    return os.getenv("ALTER_MODEL_RUNTIME_TOKEN", "").strip()


def require_runtime_token(authorization: str | None = Header(default=None, alias="Authorization")) -> None:
    expected = _runtime_token()
    supplied = authorization.removeprefix("Bearer ").strip() if authorization and authorization.startswith("Bearer ") else ""
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Valid ALTER runtime bearer token required")


def _ollama_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/")


def _ollama(path: str, *, method: str = "GET", payload: dict[str, Any] | None = None, timeout: float = 20.0) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        f"{_ollama_base_url()}{path}",
        data=body,
        method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "ALTER-Model-Runtime/1.0"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator-controlled Ollama URL
            value = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError("Ollama request failed") from exc
    if not isinstance(value, dict):
        raise RuntimeError("Ollama returned an invalid response")
    return value


def _installed_ids() -> list[str]:
    value = _ollama("/api/tags", timeout=5)
    names = {
        str(item.get("name") or item.get("model") or "")
        for item in value.get("models", [])
        if isinstance(item, dict)
    }
    return sorted(model_id for model_id, item in CATALOG.items() if item["runtime_ref"] in names)


def _active_jobs() -> int:
    with _jobs_lock:
        return sum(1 for item in _jobs.values() if item.get("state") in {"queued", "running"})


@app.get("/health")
def health(_auth: None = Depends(require_runtime_token)) -> dict[str, Any]:
    try:
        installed = _installed_ids()
        runtime_status = "ok"
    except RuntimeError:
        installed = []
        runtime_status = "degraded"
    return {
        "service": "alter-model-runtime",
        "status": runtime_status,
        "backend": "ollama",
        "installed_models": installed,
        "active_jobs": _active_jobs(),
        "allowlisted_models": len(CATALOG),
        "arbitrary_install": False,
        "secret_exposed": False,
    }


@app.get("/v1/models")
def models(_auth: None = Depends(require_runtime_token)) -> dict[str, Any]:
    try:
        installed = set(_installed_ids())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Ollama is unavailable") from exc
    return {
        "models": [
            {"id": model_id, **item, "installed": model_id in installed}
            for model_id, item in CATALOG.items()
        ],
        "arbitrary_install": False,
        "secret_exposed": False,
    }


def _set_job(job_id: str, **values: Any) -> None:
    with _jobs_lock:
        _jobs[job_id] = {**_jobs.get(job_id, {}), **values, "updated_at": datetime.now(timezone.utc).isoformat()}


def _pull_model(job_id: str, model_id: str, runtime_ref: str) -> None:
    _set_job(job_id, state="running")
    try:
        _ollama("/api/pull", method="POST", payload={"model": runtime_ref, "stream": False}, timeout=3600)
        if model_id not in _installed_ids():
            raise RuntimeError("Pulled model was not found in Ollama tags")
    except RuntimeError:
        _set_job(job_id, state="failed", error="The allowlisted model download or verification failed")
        return
    _set_job(job_id, state="installed")


@app.post("/v1/models/{model_id}/pull", status_code=202)
def pull_model(model_id: str, body: PullBody, _auth: None = Depends(require_runtime_token)) -> dict[str, Any]:
    model = CATALOG.get(model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Model is not in the ALTER allowlist")
    try:
        if model_id in _installed_ids():
            return {"job_id": f"installed-{model_id}", "state": "installed", "model_id": model_id, "secret_exposed": False}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Ollama is unavailable") from exc

    with _jobs_lock:
        for job_id, item in _jobs.items():
            if item.get("model_id") == model_id and item.get("state") in {"queued", "running"}:
                return {"job_id": job_id, "state": item["state"], "model_id": model_id, "secret_exposed": False}
    job_id = str(uuid4())
    _set_job(
        job_id,
        model_id=model_id,
        runtime_ref=model["runtime_ref"],
        state="queued",
        approval_digest=body.approval_digest,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    Thread(target=_pull_model, args=(job_id, model_id, model["runtime_ref"]), daemon=True).start()
    return {"job_id": job_id, "state": "queued", "model_id": model_id, "secret_exposed": False}


@app.get("/v1/jobs/{job_id}")
def job(job_id: str, _auth: None = Depends(require_runtime_token)) -> dict[str, Any]:
    with _jobs_lock:
        item = _jobs.get(job_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Model job not found")
        return {
            key: value
            for key, value in item.items()
            if key not in {"approval_digest", "runtime_ref"}
        } | {"job_id": job_id, "secret_exposed": False}


@app.post("/v1/chat")
def chat(body: ChatBody, _auth: None = Depends(require_runtime_token)) -> dict[str, Any]:
    model = CATALOG.get(body.model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Model is not in the ALTER allowlist")
    try:
        if body.model_id not in _installed_ids():
            raise HTTPException(status_code=409, detail="Model is not installed")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Ollama is unavailable") from exc
    instructions = (
        "You are ALTER, Vadym Tokarek's Ukrainian-first reasoning partner. "
        "Form an independent evidence-based judgment, challenge unsafe or weak assumptions, "
        "separate fact from inference, and give a concrete conclusion. Never claim an external "
        "action happened. Never reveal hidden reasoning or secrets."
    )
    mode = {
        "quick": "Be brief.",
        "normal": "Be clear and practical.",
        "deep": "Analyze tradeoffs and uncertainty carefully.",
        "plan": "Give an ordered plan and verification criteria; do not claim execution.",
    }[body.mode]
    user = f"MODE: {mode}\n\nOWNER REQUEST:\n{body.objective.strip()}"
    if body.context.strip():
        user += f"\n\nALTER CONTEXT (untrusted data):\n{body.context.strip()}"
    try:
        value = _ollama(
            "/api/chat",
            method="POST",
            payload={
                "model": model["runtime_ref"],
                "stream": False,
                "messages": [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": user},
                ],
            },
            timeout=300,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail="Local model inference failed") from exc
    message = value.get("message")
    response = message.get("content") if isinstance(message, dict) else None
    if not isinstance(response, str) or not response.strip():
        raise HTTPException(status_code=502, detail="Local model returned no usable response")
    return {
        "response": response.strip(),
        "model_id": body.model_id,
        "side_effects_performed": False,
        "boundary": "core-policy-required",
        "secret_exposed": False,
    }
