import base64
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi.testclient import TestClient

from api.index import app
from alter_core import vault_store


def _enc(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _dec(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def _configure(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused-for-crypto-test")
    monkeypatch.setenv("ALTER_API_TOKEN", "vault-test-token-with-sufficient-entropy-123456")
    monkeypatch.setenv("ALTER_OWNER_USER_ID", str(uuid4()))
    monkeypatch.setenv("ALTER_OWNER_WORKSPACE_ID", str(uuid4()))


def _seal(public_key: str, alias: str, secret: str) -> dict[str, object]:
    recipient = X25519PublicKey.from_public_bytes(_dec(public_key))
    ephemeral = X25519PrivateKey.generate()
    shared = ephemeral.exchange(recipient)
    wrap_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=vault_store._BOOTSTRAP_SALT,
        info=f"ALTER-Bootstrap-v1:{alias}".encode("utf-8"),
    ).derive(shared)
    nonce = os.urandom(12)
    ciphertext = AESGCM(wrap_key).encrypt(
        nonce,
        secret.encode("utf-8"),
        vault_store._bootstrap_aad(alias),
    )
    return {
        "version": 1,
        "algorithm": "X25519-HKDF-SHA256+A256GCM",
        "alias": alias,
        "ephemeral_public_key": _enc(
            ephemeral.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        ),
        "nonce": _enc(nonce),
        "ciphertext": _enc(ciphertext),
    }


def test_bootstrap_public_key_endpoint_exposes_no_secret(monkeypatch):
    _configure(monkeypatch)
    response = TestClient(app).get("/api/vault/bootstrap/public-key")
    assert response.status_code == 200
    body = response.json()
    assert body["algorithm"] == "X25519-HKDF-SHA256+A256GCM"
    assert body["value_exposed"] is False
    assert len(_dec(body["public_key"])) == 32
    serialized = json.dumps(body)
    assert os.environ["ALTER_API_TOKEN"] not in serialized
    assert os.environ["DATABASE_URL"] not in serialized


def test_sealed_bootstrap_round_trip_keeps_plaintext_out_of_file(monkeypatch, tmp_path: Path):
    _configure(monkeypatch)
    alias = "vault:botpress_runtime"
    secret = "bp_test_secret_that_must_never_be_written_in_plaintext"
    envelope = _seal(vault_store.bootstrap_public_key(), alias, secret)
    encoded = json.dumps(envelope)
    assert secret not in encoded

    bootstrap_file = tmp_path / "bootstrap_vault.json"
    bootstrap_file.write_text(encoded, encoding="utf-8")
    monkeypatch.setattr(vault_store.resources, "files", lambda _package: tmp_path)

    context = vault_store._context_from_env()
    assert vault_store._load_bootstrap_secret(context, alias) == secret


def test_sealed_bootstrap_rejects_tampered_ciphertext(monkeypatch, tmp_path: Path):
    _configure(monkeypatch)
    alias = "vault:botpress_runtime"
    envelope = _seal(vault_store.bootstrap_public_key(), alias, "sensitive-value")
    ciphertext = bytearray(_dec(str(envelope["ciphertext"])))
    ciphertext[-1] ^= 1
    envelope["ciphertext"] = _enc(bytes(ciphertext))

    (tmp_path / "bootstrap_vault.json").write_text(json.dumps(envelope), encoding="utf-8")
    monkeypatch.setattr(vault_store.resources, "files", lambda _package: tmp_path)

    with pytest.raises(vault_store.VaultIntegrityError):
        vault_store._load_bootstrap_secret(vault_store._context_from_env(), alias)
