# ALTER × Botpress (phone-only deployment)

This folder is the Botpress ADK cloud specialist for ALTER. It is intentionally subordinate to ALTER's owner policy, Vault and approval boundaries.

## Fixed deployment target

- Workspace: `wkspace_01M0XTFXYMFEDGHEEKT710G22P`
- Bot: `64f3490a-183a-47c5-b825-97210771822f`
- Git branch while the foundation is under review: `main`

## Why this works without a PC

GitHub Actions acts as the temporary cloud computer. The workflow installs the Botpress ADK CLI, authenticates with a GitHub Actions secret, links this ADK project to the existing Botpress workspace/bot, validates it, and deploys it.

## One-time setup from iPhone

1. In Botpress, open Profile Settings and create a Personal Access Token (PAT).
2. Copy it once. Never paste it into chat, source code, an issue, a commit, or `deploy.request`.
3. In GitHub open `tryzubtrz/agent` → Settings → Secrets and variables → Actions → New repository secret.
4. Name the secret exactly `BOTPRESS_PAT` and paste the PAT as its value.
5. Tell ChatGPT only that the secret has been added. Do not send the token itself.
6. ChatGPT can then update `ALTER/botpress/deploy.request`; that push triggers the cloud deployment workflow.

## Security

A Botpress PAT has account-level access. It lives only in GitHub Actions Secrets and is provided to the runner at deployment time. The repository contains only the non-secret workspace and bot identifiers.

## Current scope

This first ADK deployment establishes ALTER identity, priority rules, prompt-injection resistance, policy/approval boundaries, secret handling rules, workspace isolation, recovery behavior and a verified-done criterion. Browser live-view, Android execution, production Vault injection and external side-effect tools remain separate executors and must not be simulated by the Botpress agent.
