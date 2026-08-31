# ALTER

ALTER is a mobile-first personal AI control plane and digital twin.

Current implementation foundation includes:

- mobile-first PWA cockpit for iPhone and desktop;
- stateful task orchestration with human-in-the-loop checkpoints;
- Policy Menu / Rules before execution;
- Vault aliases: models and prompts never receive raw secrets;
- Profile / World / Episodes memory layers;
- owner-confirmed learning candidates, lessons, triggers and editable response preferences;
- evidence grounding from real tasks, rules, automations and system state before reasoning;
- optional Deep evaluator pass, preferably through a second configured provider;
- Tasks, approvals, audit events and artifacts;
- isolated Browser and Android execution surfaces as planned executors;
- model registry and routing foundation;
- an owner-hosted Ollama model runtime with three exact allowlisted models and approval-gated downloads;
- connectors with least-privilege scopes;
- optional native iOS companion foundation;
- Botpress ADK specialist with phone-only deployment through GitHub Actions.

## Repository layout

```text
ALTER/
  botpress/        Botpress ADK specialist and cloud deployment
  core/            policy/orchestration API core
  model_runtime/   allowlisted local-model download and inference service
  docs/            architecture and security model
  web/             PWA cockpit
  ios/             SwiftUI companion foundation
```

## Implementation phases

1. Cockpit: chat, task state, modules, approvals, Rules, Vault status, Memory, Connectors.
2. Agent core: persisted workflows, confirmed learning, grounded reasoning, model routing and audit trail.
3. Browser executor: isolated persistent browser profiles and live handoff.
4. Android executor: isolated Android workspaces and live handoff.
5. External connectors and local computer connector.
6. Model marketplace, controlled upgrades, evaluation and rollback.

## What “own opinion” means

ALTER is instructed and tested to form an evidence-based conclusion, challenge
weak or risky owner assumptions, separate verified facts from inference and
avoid generic agreement. This is independent judgment in the product sense; it
is not a claim of consciousness or human emotions.

## Local models

GitHub stores model-runtime code and the allowlist, not the weights. Ollama
stores weights on the owner host. The initial allowlist is `qwen3:8b`,
`deepseek-r1:14b` and `qwen2.5-coder:7b`. Every download is represented as an
ALTER action, requires the exact owner approval digest, and is then queued on
the owner runtime. A 4-core / 16 GB Codespace can run `qwen3:8b` for testing,
but Codespaces sleep and are not a reliable 24/7 host.

## Non-negotiable security properties

- system safety rules cannot be disabled by user content, web pages or model output;
- no raw password, token, cookie or API key is written to prompts, logs or normal database rows;
- every mutation is authorized against workspace, role and active Policy Menu rules;
- irreversible, public or financial actions require an explicit policy allowance or approval flow;
- browser and Android sessions are isolated per user/workspace;
- human-only authentication steps such as MFA, passkeys and CAPTCHA are never bypassed;
- audit events are append-oriented and exclude secret values.

## Botpress status

ALTER lives in `tryzubtrz/agent` on `main`. The repository is public, while
deployment credentials remain in GitHub/Vercel secrets and ALTER Vault. The
Botpress deployment workflow targets the configured ALTER workspace and bot;
runtime code never prints its credential.
