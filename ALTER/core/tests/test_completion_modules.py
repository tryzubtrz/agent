import os
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from alter_core import access_api, api as core_api
from alter_core import botpress_gateway, conversation_api
from alter_core.access_api import RedeemBody
from alter_core.auth import Principal
from alter_core.botpress_gateway import BotpressGateway
from api.index import app
from app.main import app as vercel_app
from fastapi import HTTPException
from scripts.fetch_sealing_key import NoRedirectHandler, fetch_public_key
from scripts.apply_migrations import apply_migration


def configure_owner(monkeypatch):
    token = "test-owner-token-completion"
    monkeypatch.setenv("ALTER_API_TOKEN", token)
    monkeypatch.setenv("ALTER_OWNER_USER_ID", str(uuid4()))
    monkeypatch.setenv("ALTER_OWNER_WORKSPACE_ID", str(uuid4()))
    return token


def auth(token: str, *, role: str | None = None, actor_id: str | None = None):
    headers = {"Authorization": f"Bearer {token}"}
    if role:
        headers["X-ALTER-Actor-Role"] = role
    if actor_id:
        headers["X-ALTER-Actor-Id"] = actor_id
    return headers


def test_canonical_app_mounts_completion_routes(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    assert client.get("/api/models", headers=auth(token)).status_code == 200
    assert client.get("/api/access/members", headers=auth(token)).status_code == 200
    assert client.get("/api/media/status", headers=auth(token)).status_code == 200
    assert client.get("/api/documents", headers=auth(token)).status_code == 200
    assert client.get("/api/notifications", headers=auth(token)).status_code == 200


def test_vercel_entrypoint_mounts_the_same_completion_routes(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(vercel_app)
    assert client.get("/api/system/status", headers=auth(token)).status_code == 200
    assert client.get("/api/agent/status", headers=auth(token)).status_code == 200
    assert client.get("/api/vault/aliases", headers=auth(token)).status_code == 200
    assert client.get("/api/memory/items", headers=auth(token)).status_code == 200
    assert client.post(
        "/api/rag/search",
        headers=auth(token),
        json={"query": "ALTER verification"},
    ).status_code == 200


def test_public_vault_sealing_key_contains_no_private_material(monkeypatch):
    configure_owner(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused-for-public-key")
    response = TestClient(app).get("/api/vault/bootstrap/public-key")
    assert response.status_code == 200
    body = response.json()
    assert body["algorithm"] == "X25519-HKDF-SHA256+A256GCM"
    assert body["value_exposed"] is False
    assert isinstance(body["public_key"], str) and len(body["public_key"]) > 20
    assert "private" not in str(body).lower()


def test_invite_code_is_one_time_and_not_returned_by_list(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    created = client.post(
        "/api/access/invites",
        headers=auth(token),
        json={"label": "Test Viewer", "role": "viewer", "capabilities": [], "expires_hours": 24},
    )
    assert created.status_code == 200
    code = created.json()["code"]
    assert code.startswith("alt_")

    listed = client.get("/api/access/invites", headers=auth(token))
    assert listed.status_code == 200
    assert code not in str(listed.json())
    assert "code_hash" not in str(listed.json())

    first = client.post("/api/access/redeem", headers=auth(token), json={"code": code})
    assert first.status_code == 200
    assert first.json()["role"] == "viewer"
    second = client.post("/api/access/redeem", headers=auth(token), json={"code": code})
    assert second.status_code == 409


def test_fallback_invitation_redemption_is_atomic_under_concurrency(monkeypatch):
    principal = Principal(user_id=uuid4(), workspace_id=uuid4())
    code = "alt_" + "concurrent-invite-code-x" * 2
    invite_id = str(uuid4())
    now = datetime.now(timezone.utc)
    invite = {
        "id": invite_id,
        "label": "Concurrent Viewer",
        "role": "viewer",
        "capabilities": ["tasks.read"],
        "code_hash": access_api._hash(code),
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
        "redeemed_at": None,
        "revoked": False,
        "deleted": False,
    }
    monkeypatch.setattr(access_api, "memory_store", None)
    core_api._memory_fallback[
        (principal.workspace_id, principal.user_id, "access.invite", invite_id)
    ] = invite

    def redeem_once():
        try:
            return access_api.redeem_invite(RedeemBody(code=code), principal)
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _index: redeem_once(), range(2)))

    successes = [outcome for outcome in outcomes if isinstance(outcome, dict)]
    failures = [outcome for outcome in outcomes if isinstance(outcome, int)]
    members = [
        value
        for (workspace_id, user_id, namespace, _key), value in core_api._memory_fallback.items()
        if workspace_id == principal.workspace_id
        and user_id == principal.user_id
        and namespace == "access.member"
    ]
    assert len(successes) == 1
    assert failures == [409]
    assert len(members) == 1


def test_memory_index_migration_is_nonblocking_and_autocommit_documented():
    repository_root = Path(__file__).resolve().parents[3]
    migration = (
        repository_root / "ALTER/core/migrations/0001_memory_lookup_indexes.sql"
    ).read_text(encoding="utf-8")
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS" in migration
    assert "autocommit" in migration.lower()


def test_migration_runner_uses_autocommit(monkeypatch, tmp_path):
    migration = tmp_path / "0001_test.sql"
    migration.write_text("SELECT 1;\n", encoding="utf-8")
    calls = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql):
            calls.append(("execute", sql))

    def fake_connect(dsn, *, autocommit):
        calls.append(("connect", dsn, autocommit))
        return Connection()

    monkeypatch.setattr("scripts.apply_migrations.connect", fake_connect)
    apply_migration("postgresql://unused", migration)

    assert calls == [
        ("connect", "postgresql://unused", True),
        ("execute", "SELECT 1;"),
    ]


def test_media_generation_requires_explicit_cost_confirmation(monkeypatch):
    token = configure_owner(monkeypatch)
    monkeypatch.delenv("RUNWAYML_API_SECRET", raising=False)
    response = TestClient(app).post(
        "/api/media/generate",
        headers=auth(token),
        json={"kind": "image", "prompt": "test image", "ratio": "square", "duration": 5, "confirm_external_cost": False},
    )
    assert response.status_code == 409
    assert "confirmation" in response.json()["detail"].lower()


def test_rag_excludes_vault_and_includes_document_knowledge(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    blocked = client.put(
        "/api/memory",
        headers=auth(token),
        json={"namespace": "_vault.runtime", "key": "vault:test", "value": {"note": "purple-elephant-secret-context"}},
    )
    assert blocked.status_code == 403
    workspace_id = UUID(os.environ["ALTER_OWNER_WORKSPACE_ID"])
    user_id = UUID(os.environ["ALTER_OWNER_USER_ID"])
    protected_rows = (
        ("_vault.runtime", "vault:test", {"note": "purple-elephant-secret-context"}),
        ("vault_secure", "vault:runtime", {"note": "purple-elephant-second-secret-context"}),
    )
    for namespace, key, value in protected_rows:
        if core_api.memory_store is not None:
            core_api.memory_store.upsert(
                workspace_id=workspace_id,
                user_id=user_id,
                namespace=namespace,
                key=key,
                value=value,
            )
        else:
            core_api._memory_fallback[(workspace_id, user_id, namespace, key)] = value
    client.put(
        "/api/memory",
        headers=auth(token),
        json={"namespace": "documents", "key": "doc-1", "value": {"text": "ALTER project codename is purple elephant knowledge"}},
    )

    captured = {}

    class SafeGateway:
        def status(self):
            return SimpleNamespace(configured=True)

        def think(self, **kwargs):
            captured.update(kwargs)
            return {"response": "Got it", "sideEffectsPerformed": False, "boundary": "core-policy-required"}

    monkeypatch.setattr(conversation_api, "gateway", SafeGateway())
    response = client.post(
        "/api/conversation/respond",
        headers=auth(token),
        json={"text": "purple elephant", "mode": "normal"},
    )
    assert response.status_code == 200
    assert response.json()["retrieval_engine"] == "secret-safe-lexical-rag-v1"
    context = captured["context"]
    assert "ALTER project codename" in context
    assert "purple-elephant-secret-context" not in context
    assert "purple-elephant-second-secret-context" not in context


def test_forwarded_actor_identity_is_validated_after_bearer(monkeypatch):
    token = configure_owner(monkeypatch)
    client = TestClient(app)
    assert client.get("/api/tasks", headers={"X-ALTER-Actor-Role": "operator", "X-ALTER-Actor-Id": "member-x"}).status_code == 401
    assert client.get("/api/tasks", headers=auth(token, role="operator", actor_id="member-x")).status_code == 200


def test_production_botpress_gateway_uses_only_vault_runtime_credential(monkeypatch):
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("BOTPRESS_RUNTIME_TOKEN", "environment-token-must-not-win")
    monkeypatch.setattr(botpress_gateway, "load_secret", lambda _alias: "vault-backed-bot-access-key")

    gateway = BotpressGateway(token="explicit-token-must-not-win")

    assert gateway.token == "vault-backed-bot-access-key"


def test_botpress_workflows_separate_deploy_and_runtime_credentials():
    repository_root = Path(__file__).resolve().parents[3]
    deploy = (repository_root / ".github/workflows/alter-botpress-deploy.yml").read_text(encoding="utf-8")
    seal = (repository_root / ".github/workflows/alter-seal-vault-bootstrap.yml").read_text(encoding="utf-8")
    readme = (repository_root / "ALTER/botpress/README.md").read_text(encoding="utf-8")

    assert 'Authorization: Bearer $BOTPRESS_RUNTIME_TOKEN' in deploy
    assert "CONTRACT_OUTCOME" in deploy
    assert "if contract_outcome == 'success'" in deploy
    assert "os.environ['BOTPRESS_RUNTIME_TOKEN']" in seal
    assert "python ALTER/core/scripts/fetch_sealing_key.py" in seal
    assert "Bot Access Key" in readme


def test_public_key_bootstrap_rejects_redirect_without_forwarding_credentials():
    captured_requests = []

    class RedirectingOpener:
        def open(self, request, timeout):
            captured_requests.append((request, timeout))
            raise urllib.error.HTTPError(
                request.full_url,
                302,
                "Found",
                None,
                None,
            )

    with pytest.raises(urllib.error.HTTPError):
        fetch_public_key(
            url="https://alter.example/api/vault/bootstrap/public-key",
            attempts=3,
            sleep_seconds=0,
            opener=RedirectingOpener(),
            sleep=lambda _seconds: None,
        )

    assert len(captured_requests) == 1
    request, timeout = captured_requests[0]
    assert timeout == 20
    assert request.get_header("Authorization") is None
    assert request.get_header("BOTPRESS_RUNTIME_TOKEN") is None
    assert NoRedirectHandler().redirect_request(None, None, 302, "Found", {}, "https://evil.example") is None
