from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from importlib import resources
from uuid import UUID

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .persistence import PostgresMemoryStore

_VAULT_NAMESPACE = "_vault.runtime"
_VERSION = 1
_BOOTSTRAP_FILE = "bootstrap_vault.json"


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


def _bootstrap_private_key(context: VaultContext) -> X25519PrivateKey:
    seed = hashlib.sha256(
        b"ALTER-Vault-Bootstrap-X25519-v1\x00"
        + context.workspace_id.bytes
        + b"\x00"
        + context.api_token.encode("utf-8")
    ).digest()
    return X25519PrivateKey.from_private_bytes(seed)


def bootstrap_public_key() -> str:
    context = _context_from_env()
    public = _bootstrap_private_key(context).public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return _encode(public)


def _bootstrap_wrap_key(context: VaultContext, alias: str, shared_secret: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=hashlib.sha256(context.workspace_id.bytes).digest(),
        info=f"ALTER-Bootstrap-v1:{alias}".encode("utf-8"),
    ).derive(shared_secret)


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


def _load_persisted_secret(context: VaultContext, alias: str) -> str | None:
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
    except Exception as exc:
        raise VaultIntegrityError("Vault secret could not be decrypted.") from exc


def _load_bootstrap_secret(context: VaultContext, alias: str) -> str | None:
    try:
        candidate = resources.files("alter_core").joinpath(_BOOTSTRAP_FILE)
        if not candidate.is_file():
            return None
        envelope = json.loads(candidate.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(envelope, dict) or envelope.get("alias") != alias or envelope.get("version") != _VERSION:
        return None
    try:
        ephemeral = X25519PublicKey.from_public_bytes(_decode(str(envelope["ephemeral_public_key"])))
        shared = _bootstrap_private_key(context).exchange(ephemeral)
        wrap_key = _bootstrap_wrap_key(context, alias, shared)
        nonce = _decode(str(envelope["nonce"]))
        ciphertext = _decode(str(envelope["ciphertext"]))
        plaintext = AESGCM(wrap_key).decrypt(nonce, ciphertext, _aad(context, alias))
        return plaintext.decode("utf-8")
    except Exception as exc:
        raise VaultIntegrityError("Bootstrap vault envelope could not be decrypted.") from exc


def load_secret(alias: str) -> str | None:
    context = _context_from_env()
    persisted = _load_persisted_secret(context, alias)
    if persisted:
        return persisted

    bootstrapped = _load_bootstrap_secret(context, alias)
    if not bootstrapped:
        return None

    # Best-effort migration from the sealed deployment envelope into Neon.
    # Failure to persist must not reveal or log the secret value.
    try:
        store_secret(alias, bootstrapped)
    except Exception:
        pass
    return bootstrapped


def secret_configured(alias: str) -> bool:
    try:
        return bool(load_secret(alias))
    except (VaultUnavailableError, VaultIntegrityError):
        return False
