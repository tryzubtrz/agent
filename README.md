# ALTER Agent

Private home repository for **ALTER — Universal Digital Twin**.

The product source lives in `ALTER/`:
- `ALTER/web` — mobile-first PWA cockpit
- `ALTER/core` — policy/orchestration API core
- `ALTER/botpress` — Botpress ADK specialist and cloud deployment
- `ALTER/ios` — SwiftUI companion foundation
- `ALTER/docs` — architecture and threat model

Botpress deployment is targeted at the configured ALTER workspace/bot and reads `BOTPRESS_PAT` only from GitHub Actions Secrets.
