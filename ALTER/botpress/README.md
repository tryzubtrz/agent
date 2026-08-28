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
4. Name the secret exactly `BOTPRESS_PAT` and paste the PAT as its value. This credential is used only by the ADK deployment steps.
5. Obtain the deployed bot's least-privileged Bot Access Key (BAK), which Botpress limits to Runtime, Tables, and Files APIs.
6. Add the BAK as a second GitHub Actions secret named exactly `BOTPRESS_RUNTIME_TOKEN`.
7. Tell ChatGPT only that both secrets have been added. Do not send either token itself.
8. ChatGPT can then update `ALTER/botpress/deploy.request`; that push triggers the cloud deployment workflow.

## Security

A Botpress PAT has account-level access. It lives only in GitHub Actions Secrets, is provided solely to the ADK deployment steps, and must never be used by ALTER Runtime. The repository contains only the non-secret workspace and bot identifiers.

Runtime contract checks and ALTER Core use the separate `BOTPRESS_RUNTIME_TOKEN` Bot Access Key. GitHub Actions seals that BAK into `vault:botpress_runtime`; production Core resolves only the Vault alias. Explicit constructor tokens and environment fallback are limited to local/test execution.

## Current scope

This first ADK deployment establishes ALTER identity, priority rules, prompt-injection resistance, policy/approval boundaries, secret handling rules, workspace isolation, recovery behavior and a verified-done criterion. Browser live-view, Android execution, production Vault injection and external side-effect tools remain separate executors and must not be simulated by the Botpress agent.
