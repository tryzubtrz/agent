# ALTER

ALTER is a mobile-first personal AI control plane and digital twin.

Current implementation foundation includes:

- mobile-first PWA cockpit for iPhone and desktop;
- stateful task orchestration with human-in-the-loop checkpoints;
- Policy Menu / Rules before execution;
- Vault aliases: models and prompts never receive raw secrets;
- Profile / World / Episodes memory layers;
- Tasks, approvals, audit events and artifacts;
- isolated Browser and Android execution surfaces as planned executors;
- model registry and routing foundation;
- connectors with least-privilege scopes;
- optional native iOS companion foundation;
- Botpress ADK specialist with phone-only deployment through GitHub Actions.

## Repository layout

```text
ALTER/
  botpress/        Botpress ADK specialist and cloud deployment
  core/            policy/orchestration API core
  docs/            architecture and security model
  web/             PWA cockpit
  ios/             SwiftUI companion foundation
```

## Implementation phases

1. Cockpit: chat, task state, modules, approvals, Rules, Vault status, Memory, Connectors.
2. Agent core: persisted workflows, checkpoints, model routing and audit trail.
3. Browser executor: isolated persistent browser profiles and live handoff.
4. Android executor: isolated Android workspaces and live handoff.
5. External connectors and local computer connector.
6. Model marketplace, controlled upgrades, evaluation and rollback.

## Non-negotiable security properties

- system safety rules cannot be disabled by user content, web pages or model output;
- no raw password, token, cookie or API key is written to prompts, logs or normal database rows;
- every mutation is authorized against workspace, role and active Policy Menu rules;
- irreversible, public or financial actions require an explicit policy allowance or approval flow;
- browser and Android sessions are isolated per user/workspace;
- human-only authentication steps such as MFA, passkeys and CAPTCHA are never bypassed;
- audit events are append-oriented and exclude secret values.

## Botpress status

ALTER now lives in the private `tryzubtrz/agent` repository on `main`. GitHub Actions secret `BOTPRESS_PAT` has been presence-checked without exposing its value. The Botpress deployment workflow targets workspace `wkspace_01M0XTFXYMFEDGHEEKT710G22P` and bot `64f3490a-183a-47c5-b825-97210771822f`.
