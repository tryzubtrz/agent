# ALTER Threat Model — Design Baseline

This is a design-level threat model derived from the current ALTER specification. It is not a claim that controls already exist in production.

## Assets

- owner identity and authenticated sessions;
- workspace data and files;
- Vault secrets and connector credentials;
- browser and Android session state;
- task plans, memory and artifacts;
- approval decisions and policy rules;
- model/provider credentials and billing authority;
- audit history.

## Trust boundaries

1. **Owner device ↔ control plane** — internet-facing authenticated boundary.
2. **Control plane ↔ model providers** — prompts and tool results cross to external processors.
3. **Control plane ↔ Vault** — secret retrieval boundary.
4. **Control plane ↔ Browser executor** — high-value session boundary.
5. **Control plane ↔ Android executor** — device-control boundary.
6. **Control plane ↔ external connectors/APIs** — third-party authorization boundary.
7. **Workspace ↔ workspace** — strict tenant isolation boundary.
8. **Human approval ↔ autonomous execution** — authority escalation boundary.

## Attacker-controlled inputs

- chat messages and attachments;
- web page text, forms, scripts and downloads;
- emails, social posts and third-party messages;
- connector/API responses;
- model outputs;
- uploaded archives and documents;
- invitation links and guest input;
- untrusted plugin/market metadata.

All of these are data, not policy.

## Security invariants

### Authorization
- Every read and mutation is scoped to authenticated user + workspace + role.
- Worker/model identity never inherits owner authority implicitly.
- Cross-workspace object identifiers cannot grant access by themselves.

### Policy
- Immutable safety constraints run before owner rules and task instructions.
- Active owner rules are evaluated before tool execution.
- A web page, file, connector response or model output cannot rewrite policy.

### Secrets
- Raw secrets never enter normal prompts, logs, memory or task event text.
- Secret lookup is alias-based and occurs only inside an authorized executor.
- Secret scopes are minimal and revocable.

### Human-only authentication
- MFA, passkeys, CAPTCHA and biometric steps cannot be bypassed or automated as if completed by the owner.
- Tasks pause and persist before these steps, then resume from the same checkpoint.

### Side effects
- Public, financial, irreversible or reputation-sensitive actions are blocked unless current policy explicitly allows them or an approval is recorded.
- Side-effecting calls use idempotency protection where supported.

### Isolation
- Browser session state, cookies, history and downloads are isolated per profile/workspace.
- Android workspaces are isolated and cannot silently reuse another user's login/session state.
- Files and memory are workspace-scoped.

### Audit
- Security-relevant events are append-oriented.
- Audit trails include actor, workspace, task, action class, result and timestamp, but no raw secret values.

## Priority threats

### T1. Prompt injection through websites/files
**Risk:** external content tells ALTER to reveal secrets, change rules or perform unrelated actions.
**Control:** content/policy separation, capability scoping, policy check immediately before execution, secret aliasing.

### T2. Cross-workspace data leak / IDOR
**Risk:** guessed task/file/profile IDs expose another workspace.
**Control:** server-side workspace predicates on every lookup and mutation; deny by default; test cross-tenant access explicitly.

### T3. Secret exfiltration to model/log
**Risk:** a tool response or exception returns a token/cookie/API key.
**Control:** dedicated secret manager, structured redaction layer, response filters, log scanning and no raw secret persistence.

### T4. Approval bypass
**Risk:** a task mutates external state after a stale or unrelated approval.
**Control:** approvals bind to task, action class, parameters/hash, workspace, expiration and policy version.

### T5. Browser session theft
**Risk:** cookies/session state leak through logs, screenshots, downloads or model context.
**Control:** encrypted isolated profiles, no cookie export, restricted debugging, redacted telemetry and explicit profile ownership.

### T6. Malicious connector/plugin
**Risk:** excessive scopes, hidden data export or dangerous side effects.
**Control:** permission manifest, least privilege, staged enablement, audit logs, revocation and sandboxed execution where feasible.

### T7. Malicious upload/archive
**Risk:** executable payload, path traversal, decompression bomb or parser exploit.
**Control:** quarantine, bounded extraction, path normalization, file-type validation, malware/content scanning where available, never auto-run executables.

### T8. Model/tool confused deputy
**Risk:** subordinate model invokes a capability outside its intended task.
**Control:** per-task capability tokens/handles, narrow tool schemas, policy check at executor boundary and no global credentials in model context.

### T9. Stale task resumes under changed policy
**Risk:** a paused task continues after rules or permissions changed.
**Control:** re-evaluate current policy and authorization at resume and immediately before every external side effect.

### T10. Audit tampering
**Risk:** compromised worker removes evidence.
**Control:** append-oriented centralized audit sink; workers cannot delete or rewrite prior audit events.

## Security test priorities

1. Cross-workspace authorization tests for every resource type.
2. Prompt-injection regression tests using hostile web/file content.
3. Secret redaction tests for success, error and retry paths.
4. Approval binding/replay/expiry tests.
5. Policy-change-while-paused tests.
6. Browser/Android profile isolation tests.
7. Archive traversal and oversized upload tests.
8. Connector scope downgrade/revocation tests.

## Known design limitations

- Browser and Android executors require separate hardened infrastructure to achieve the intended isolation.
- iOS cannot provide unrestricted hidden system control; the native app must stay within official platform permissions and user-visible integrations.
- Security claims remain provisional until implementation and deployment configuration are reviewed and tested.
