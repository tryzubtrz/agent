from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .persistence import PostgresMemoryStore

_VAULT_NAMESPACE = "_vault.runtime"
_VERSION = 1


class VaultUnavailableError(RuntimeError):
    pass


class VaultIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True)
class VaultContext:
    workspace_id: UUID
    user_id: UUID
    database_url: str
    api_token: str


def _context_from_env() -> VaultContext:
    database_url = os.getenv("DATABASE_URL", "").strip()
    api_token = os.getenv("ALTER_API_TOKEN", "").strip()
    workspace_raw = os.getenv("ALTER_OWNER_WORKSPACE_ID", "").strip()
    user_raw = os.getenv("ALTER_OWNER_USER_ID", "").strip()
    if not (database_url and api_token and workspace_raw and user_raw):
        raise VaultUnavailableError("ALTER runtime vault is not fully configured.")
    try:
        return VaultContext(
            workspace_id=UUID(workspace_raw),
            user_id=UUID(user_raw),
            database_url=database_url,
            api_token=api_token,
        )
    except ValueError as exc:
        raise VaultUnavailableError("ALTER runtime vault identity is invalid.") from exc


def _key(context: VaultContext) -> bytes:
    material = (
        b"ALTER-Vault-v1\x00"
        + context.workspace_id.bytes
        + b"\x00"
        + context.api_token.encode("utf-8")
    )
    return hashlib.sha256(material).digest()


def _aad(context: VaultContext, alias: str) -> bytes:
    return f"{_VERSION}:{context.workspace_id}:{alias}".encode("utf-8")


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def _decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data.encode("ascii"))


def store_secret(alias: str, secret: str) -> None:
    context = _context_from_env()
    if not alias.startswith("vault:"):
        raise ValueError("Vault aliases must start with 'vault:'.")
    if not secret:
        raise ValueError("Secret must not be empty.")

    nonce = os.urandom(12)
    cipher = AESGCM(_key(context))
    ciphertext = cipher.encrypt(nonce, secret.encode("utf-8"), _aad(context, alias))
    envelope = {
        "version": _VERSION,
        "algorithm": "AES-256-GCM",
        "nonce": _encode(nonce),
        "ciphertext": _encode(ciphertext),
    }
    PostgresMemoryStore(context.database_url).upsert(
        workspace_id=context.workspace_id,
        user_id=context.user_id,
        namespace=_VAULT_NAMESPACE,
        key=alias,
        value=envelope,
    )


def load_secret(alias: str) -> str | None:
    context = _context_from_env()
    rows = PostgresMemoryStore(context.database_url).list_for_user(
        workspace_id=context.workspace_id,
        user_id=context.user_id,
        namespace=_VAULT_NAMESPACE,
        limit=100,
    )
    row = next((item for item in rows if item.get("key") == alias), None)
    if row is None:
        return None
    value = row.get("value")
    if not isinstance(value, dict) or value.get("version") != _VERSION:
        raise VaultIntegrityError("Vault envelope is invalid.")
    try:
        nonce = _decode(str(value["nonce"]))
        ciphertext = _decode(str(value["ciphertext"]))
        plaintext = AESGCM(_key(context)).decrypt(
            nonce,
            ciphertext,
            _aad(context, alias),
        )
        return plaintext.decode("utf-8")
    except Exception as exc:  # provider details must never reach callers
        raise VaultIntegrityError("Vault secret could not be decrypted.") from exc


def secret_configured(alias: str) -> bool:
    try:
        return bool(load_secret(alias))
    except (VaultUnavailableError, VaultIntegrityError):
        return False
