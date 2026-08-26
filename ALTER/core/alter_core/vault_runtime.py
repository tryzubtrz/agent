from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from psycopg import connect
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class VaultRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class VaultIdentity:
    workspace_id: UUID
    user_id: UUID


class VaultRuntimeStore:
    """Encrypted owner-scoped secret store backed by the existing memories table.

    Plaintext secret values are encrypted before they are written to Postgres.
    The encryption key is deterministically derived from the server-only
    ALTER_API_TOKEN so no additional database migration or browser-visible key
    is required. No API in this module returns plaintext to clients.
    """

    namespace = "vault_secure"

    def __init__(
        self,
        *,
        dsn: str | None = None,
        master_material: str | None = None,
        workspace_id: str | UUID | None = None,
        user_id: str | UUID | None = None,
    ) -> None:
        self.dsn = (dsn if dsn is not None else os.getenv("DATABASE_URL", "")).strip()
        self.master_material = (
            master_material if master_material is not None else os.getenv("ALTER_API_TOKEN", "")
        ).strip()
        workspace_value = workspace_id if workspace_id is not None else os.getenv("ALTER_OWNER_WORKSPACE_ID", "")
        user_value = user_id if user_id is not None else os.getenv("ALTER_OWNER_USER_ID", "")
        self.identity = self._identity(workspace_value, user_value)

    @staticmethod
    def _identity(workspace_id: str | UUID | None, user_id: str | UUID | None) -> VaultIdentity | None:
        try:
            if not workspace_id or not user_id:
                return None
            return VaultIdentity(UUID(str(workspace_id)), UUID(str(user_id)))
        except (TypeError, ValueError):
            return None

    @property
    def configured(self) -> bool:
        return bool(self.dsn and self.master_material and self.identity)

    def _fernet(self) -> Fernet:
        if not self.master_material:
            raise VaultRuntimeError("Vault encryption material is not configured.")
        digest = hashlib.sha256(
            b"ALTER_VAULT_RUNTIME_V1\x00" + self.master_material.encode("utf-8")
        ).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    @staticmethod
    def normalize_alias(alias: str) -> str:
        value = alias.strip().lower()
        if not value.startswith("vault:"):
            value = f"vault:{value}"
        if len(value) < 7 or len(value) > 160:
            raise VaultRuntimeError("Invalid Vault alias.")
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789:_-." )
        if any(char not in allowed for char in value):
            raise VaultRuntimeError("Vault alias contains unsupported characters.")
        return value

    def put(self, *, alias: str, value: str, purpose: str = "connector") -> dict[str, Any]:
        if not self.configured or self.identity is None:
            raise VaultRuntimeError("Encrypted Vault is not configured.")
        if not value or len(value) > 20_000:
            raise VaultRuntimeError("Secret value is empty or too large.")
        normalized = self.normalize_alias(alias)
        ciphertext = self._fernet().encrypt(value.encode("utf-8")).decode("ascii")
        safe_value = {
            "ciphertext": ciphertext,
            "purpose": purpose.strip()[:160] or "connector",
            "version": 1,
            "algorithm": "fernet-aes128-cbc-hmac-sha256",
        }
        with connect(self.dsn, row_factory=dict_row) as conn:
            conn.execute(
                """
                INSERT INTO workspaces (id, name)
                VALUES (%s, %s)
                ON CONFLICT (id) DO UPDATE SET updated_at = now()
                """,
                (self.identity.workspace_id, "ALTER"),
            )
            row = conn.execute(
                """
                INSERT INTO memories (workspace_id, user_id, namespace, key, value)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (workspace_id, user_id, namespace, key)
                DO UPDATE SET value = EXCLUDED.value, updated_at = now()
                RETURNING key, value, created_at, updated_at
                """,
                (
                    self.identity.workspace_id,
                    self.identity.user_id,
                    self.namespace,
                    normalized,
                    Jsonb(safe_value),
                ),
            ).fetchone()
        assert row is not None
        return {
            "alias": normalized,
            "purpose": safe_value["purpose"],
            "configured": True,
            "encrypted": True,
            "value_exposed": False,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def resolve(self, alias: str) -> str | None:
        if not self.configured or self.identity is None:
            return None
        normalized = self.normalize_alias(alias)
        with connect(self.dsn, row_factory=dict_row) as conn:
            row = conn.execute(
                """
                SELECT value
                FROM memories
                WHERE workspace_id = %s AND user_id = %s
                  AND namespace = %s AND key = %s
                LIMIT 1
                """,
                (
                    self.identity.workspace_id,
                    self.identity.user_id,
                    self.namespace,
                    normalized,
                ),
            ).fetchone()
        if row is None:
            return None
        stored = row.get("value")
        if not isinstance(stored, dict) or not isinstance(stored.get("ciphertext"), str):
            raise VaultRuntimeError("Vault entry is malformed.")
        try:
            return self._fernet().decrypt(stored["ciphertext"].encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError, ValueError) as exc:
            raise VaultRuntimeError("Vault entry could not be decrypted.") from exc

    def list_entries(self) -> list[dict[str, Any]]:
        if not self.configured or self.identity is None:
            return []
        with connect(self.dsn, row_factory=dict_row) as conn:
            rows = conn.execute(
                """
                SELECT key, value, created_at, updated_at
                FROM memories
                WHERE workspace_id = %s AND user_id = %s AND namespace = %s
                ORDER BY updated_at DESC
                LIMIT 250
                """,
                (self.identity.workspace_id, self.identity.user_id, self.namespace),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            stored = row.get("value")
            purpose = stored.get("purpose", "connector") if isinstance(stored, dict) else "connector"
            result.append(
                {
                    "alias": row["key"],
                    "purpose": purpose,
                    "configured": True,
                    "encrypted": True,
                    "value_exposed": False,
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        return result

    def delete(self, alias: str) -> bool:
        if not self.configured or self.identity is None:
            raise VaultRuntimeError("Encrypted Vault is not configured.")
        normalized = self.normalize_alias(alias)
        with connect(self.dsn) as conn:
            cursor = conn.execute(
                """
                DELETE FROM memories
                WHERE workspace_id = %s AND user_id = %s
                  AND namespace = %s AND key = %s
                """,
                (
                    self.identity.workspace_id,
                    self.identity.user_id,
                    self.namespace,
                    normalized,
                ),
            )
            return cursor.rowcount > 0


def resolve_owner_vault_secret(alias: str) -> str | None:
    """Resolve an owner Vault secret for server-side adapters only.

    Errors fail closed and never include secret material.
    """
    try:
        return VaultRuntimeStore().resolve(alias)
    except Exception:
        return None
