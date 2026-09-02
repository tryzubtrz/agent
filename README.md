# ALTER Agent

Canonical repository for **ALTER — Universal Digital Twin**.

> This repository is currently public. Never commit API keys, owner memory,
> database exports, `.env` files or downloaded model weights. Runtime secrets
> stay behind Vault aliases and live memory stays in owner-scoped PostgreSQL.

The product source lives in `ALTER/`:
- `ALTER/web` — mobile-first PWA cockpit
- `ALTER/core` — policy/orchestration API core
- `ALTER/model_runtime` — owner-controlled Ollama runtime with an exact model allowlist
- `ALTER/botpress` — Botpress ADK specialist and cloud deployment
- `ALTER/ios` — SwiftUI companion foundation
- `ALTER/docs` — architecture and threat model

GitHub Codespaces can now run ALTER's owner-controlled Ollama worker on a
4-core / 16 GB machine. It is an on-demand reasoning node, while Vercel Core and
PostgreSQL remain the durable control plane. Setup and honest lifecycle limits
are documented in `ALTER/docs/CODESPACES_WORKER.md`.

The useful code from `tryzubtrz/Agent-2` has been merged into this stronger
Core architecture: confirmed learning candidates, lessons, contextual triggers,
editable preferences, deterministic read-only grounding and an optional Deep
critic pass. `tryzubtrz/Agent-ai` contains only its initial README and had no
implementation to import. See `ALTER/docs/REPOSITORY_MERGE_20260831.md`.

Botpress deployment is targeted at the configured ALTER workspace/bot and reads `BOTPRESS_PAT` only from GitHub Actions Secrets.
