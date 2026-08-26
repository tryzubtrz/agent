# ALTER

ALTER is a mobile-first personal AI control plane and digital twin.

This branch starts the implementation from the product specification:

- mobile-first PWA cockpit for iPhone and desktop;
- stateful task orchestration with human-in-the-loop checkpoints;
- Policy Menu / Rules before execution;
- Vault aliases: models and prompts never receive raw secrets;
- Profile / World / Episodes memory layers;
- Tasks, approvals, audit events and artifacts;
- isolated Browser and Android execution surfaces;
- model registry and routing;
- connectors with least-privilege scopes;
- optional native iOS companion.

## Repository layout

```text
ALTER/
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

## Status

Foundation branch created. Botpress integration is pending account reconnection; the product architecture does not depend on Botpress and can use it as one specialist agent surface after connection is restored.
