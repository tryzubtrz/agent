from __future__ import annotations

import base64
import json
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

_ISSUER = "https://token.actions.githubusercontent.com"
_JWKS_URL = "https://token.actions.githubusercontent.com/.well-known/jwks"
_AUDIENCE = "alter-vault-bootstrap"
_REPOSITORY = "tryzubtrz/agent"
_REF = "refs/heads/main"


class GitHubOIDCError(RuntimeError):
    pass


def _b64url_decode(value: str) -> bytes:
    padding_len = (-len(value)) % 4
    return base64.urlsafe_b64decode((value + ("=" * padding_len)).encode("ascii"))


def _json_segment(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(_b64url_decode(value))
    except Exception as exc:
        raise GitHubOIDCError("Invalid GitHub OIDC token encoding.") from exc
    if not isinstance(parsed, dict):
        raise GitHubOIDCError("Invalid GitHub OIDC token payload.")
    return parsed


def _load_jwks() -> list[dict[str, Any]]:
    request = Request(_JWKS_URL, headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 - fixed GitHub issuer URL
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GitHubOIDCError("GitHub OIDC signing keys are unavailable.") from exc
    keys = payload.get("keys") if isinstance(payload, dict) else None
    if not isinstance(keys, list):
        raise GitHubOIDCError("GitHub OIDC signing keys are invalid.")
    return [item for item in keys if isinstance(item, dict)]


def _verify_signature(token: str, header: dict[str, Any]) -> None:
    if header.get("alg") != "RS256":
        raise GitHubOIDCError("Unsupported GitHub OIDC signing algorithm.")
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise GitHubOIDCError("GitHub OIDC key identifier is missing.")
    key_data = next((item for item in _load_jwks() if item.get("kid") == kid), None)
    if key_data is None:
        raise GitHubOIDCError("GitHub OIDC signing key was not found.")
    try:
        n = int.from_bytes(_b64url_decode(str(key_data["n"])), "big")
        e = int.from_bytes(_b64url_decode(str(key_data["e"])), "big")
        public_key = rsa.RSAPublicNumbers(e, n).public_key()
        signing_input, signature_segment = token.rsplit(".", 1)
        signature = _b64url_decode(signature_segment)
        public_key.verify(
            signature,
            signing_input.encode("ascii"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except Exception as exc:
        raise GitHubOIDCError("GitHub OIDC signature verification failed.") from exc


def validate_github_actions_oidc(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise GitHubOIDCError("Invalid GitHub OIDC token.")
    header = _json_segment(parts[0])
    claims = _json_segment(parts[1])
    _verify_signature(token, header)

    now = int(time.time())
    if claims.get("iss") != _ISSUER:
        raise GitHubOIDCError("GitHub OIDC issuer mismatch.")
    audience = claims.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]
    if _AUDIENCE not in audiences:
        raise GitHubOIDCError("GitHub OIDC audience mismatch.")
    try:
        exp = int(claims.get("exp", 0))
        nbf = int(claims.get("nbf", 0))
    except (TypeError, ValueError) as exc:
        raise GitHubOIDCError("GitHub OIDC time claims are invalid.") from exc
    if exp <= now or nbf > now + 30:
        raise GitHubOIDCError("GitHub OIDC token is expired or not active.")
    if claims.get("repository") != _REPOSITORY:
        raise GitHubOIDCError("GitHub OIDC repository is not authorized.")
    if claims.get("ref") != _REF:
        raise GitHubOIDCError("GitHub OIDC ref is not authorized.")
    expected_sub = f"repo:{_REPOSITORY}:ref:{_REF}"
    if claims.get("sub") != expected_sub:
        raise GitHubOIDCError("GitHub OIDC subject is not authorized.")
    return claims
