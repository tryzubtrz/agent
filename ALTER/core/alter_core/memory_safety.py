from __future__ import annotations


def normalize_memory_namespace(namespace: str) -> str:
    """Return the canonical form used by every memory access boundary."""
    return namespace.strip().lower()


def is_protected_memory_namespace(namespace: str) -> bool:
    """Keep Vault-backed namespaces out of ordinary memory APIs."""
    normalized = normalize_memory_namespace(namespace)
    return normalized.startswith(("_vault", "vault_secure"))


def is_internal_memory_namespace(namespace: str) -> bool:
    """Keep Vault and access-control records behind their dedicated APIs."""
    normalized = normalize_memory_namespace(namespace)
    return is_protected_memory_namespace(normalized) or normalized.startswith("access.")


def is_rag_excluded_namespace(
    namespace: str,
    *,
    exclude_conversation: bool = True,
) -> bool:
    """Keep protected/internal state out of both retrieval pipelines."""
    normalized = normalize_memory_namespace(namespace)
    if not normalized:
        return True
    if is_internal_memory_namespace(normalized):
        return True
    return exclude_conversation and normalized.startswith("conversation")
