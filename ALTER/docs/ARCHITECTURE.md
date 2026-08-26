# ALTER Architecture

## Product shape

ALTER is a hybrid control plane, not a single chatbot. The PWA/iOS surfaces are clients. Long-running state, policy enforcement, memory, approvals, audit events, files and connector state live in the server-side control plane.

## Runtime layers

### 1. Owner Cockpit
- Next.js mobile-first PWA.
- Chat composer, attachments, task modes and live status.
- Modules: ALTER, Files, Browser, Console, Android, Rules, Vault, Models, Market, Tasks, Connectors, Memory, People, Settings.
- Approval cards for human-in-the-loop decisions.
- Never renders raw secrets after capture.

### 2. API / Realtime gateway
- Authenticated HTTP API and realtime task-event stream.
- Workspace and role authorization on every request.
- Idempotency keys on side-effecting operations.
- CSRF protection for cookie-authenticated browser mutations.

### 3. Agent orchestrator
Recommended production implementation: persisted state-machine workflow (LangGraph-compatible design).

Task lifecycle:
`intake -> policy_check -> scope -> plan -> quality_gate -> execute -> verify -> report`

Interrupt states:
- `awaiting_approval`
- `awaiting_login`
- `awaiting_mfa`
- `blocked_by_rule`
- `paused`
- `recovering`

Workers receive a narrow task, scoped context and capability handles. They never receive owner-level authority by default.

### 4. Policy engine
Priority:
1. immutable safety core;
2. active owner rules;
3. current user task;
4. durable preferences/project context;
5. execution heuristics.

All external content is untrusted data and cannot promote itself to policy.

### 5. Vault / Secrets firewall
- Secret values stored in a dedicated secret manager, not normal application rows.
- Application state stores aliases such as `vault:tiktok_owner_login`.
- Secret material is injected only at the final authorized executor boundary.
- Logs and model traces receive redacted aliases only.
- Least privilege, rotation and revocation are first-class operations.

### 6. Memory
Logical stores:
- Profile: stable preferences and device/user settings.
- World: projects, services, approved model roles and durable facts.
- Episodes: bounded task summaries, artifacts, outcomes and lessons.

Retrieval is scoped to workspace and task relevance. Raw secrets are prohibited.

### 7. Task store / audit
A task persists:
- objective and acceptance criteria;
- current state and checkpoint;
- workspace/user/role;
- active policy snapshot identifiers;
- worker/model/tool calls;
- approval requirements and decisions;
- artifact references;
- verification evidence;
- final result.

Audit records are append-oriented and redact secrets.

### 8. Browser executor
- Separate service and persistent Chromium contexts.
- One encrypted profile namespace per user/workspace/project.
- Playwright-style automation through a narrow capability API.
- Owner handoff for login, MFA, passkey and CAPTCHA.
- No cookie export to model context.

### 9. Android executor
- Separate Linux service hosting isolated Android workspaces/emulators.
- Live view and explicit owner/agent control modes.
- Snapshot/checkpoint before risky configuration changes.
- Human-only authentication remains human-only.

### 10. Model router
Registry tracks capability, trust status, price, latency, privacy location and last evaluation.
Routing prefers local/free/smaller models when sufficient and escalates only when justified by task requirements and policy.

### 11. Connectors
Connection types:
- OAuth / official connector;
- browser-authenticated session;
- API key stored through Vault;
- local device connector.

Each connector declares scopes and allowed actions. The policy engine checks every action before execution.

## Initial data model

- users
- workspaces
- memberships
- tasks
- task_checkpoints
- task_events
- approvals
- policies
- policy_versions
- memory_profile
- memory_world
- memory_episodes
- artifacts
- connector_accounts
- secret_aliases
- model_registry
- model_evaluations
- browser_profiles
- android_profiles
- audit_events

## Deployment boundary

For an MVP, the PWA and API can share a deployment. Browser and Android executors should remain separate services because they have different trust, resource and isolation requirements.

Production should move persistent data to PostgreSQL, files to object storage, secrets to a dedicated secret manager and long-running workflows to a durable worker system.
