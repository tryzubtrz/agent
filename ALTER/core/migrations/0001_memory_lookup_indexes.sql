-- Run with autocommit: PostgreSQL forbids CONCURRENTLY inside a transaction block.
-- Supports owner-scoped namespace and key-prefix reads before updated_at limits.
CREATE INDEX CONCURRENTLY IF NOT EXISTS memories_workspace_user_namespace_updated_idx
    ON memories (workspace_id, user_id, namespace, updated_at DESC);
