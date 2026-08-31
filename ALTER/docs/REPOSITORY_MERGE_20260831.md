# ALTER repository merge audit — 2026-08-31

## Source repositories

| Repository | Audited state | Merge decision |
| --- | --- | --- |
| `tryzubtrz/agent` | Production Core + PWA + PostgreSQL + Policy/Approval/Vault + Vercel/Botpress workflows | Canonical base |
| `tryzubtrz/Agent-ai` | One initial commit containing only `README.md` | No implementation to import |
| `tryzubtrz/Agent-2` | Emergent FastAPI/Mongo backend and React UI with useful learning/agent-loop prototypes | Port useful behavior, not the duplicate stack |

## Capabilities ported into the canonical agent

1. Confirmed learning candidates from explicit durable owner statements.
2. Owner approval before any candidate becomes long-term typed memory.
3. Lessons learned from corrections and failures.
4. Contextual “when → consider” triggers.
5. Editable tone/language/length preferences and deterministic learning from chat statistics.
6. Read-only grounding from real tasks, policy rules, automations and system status.
7. A Deep critic pass that prefers a second configured reasoning provider.
8. Independent-judgment instructions: challenge weak assumptions, distinguish fact/inference/recommendation, give a conclusion.
9. A real local-model runtime with exact Ollama references, approval-bound jobs and no arbitrary model or shell input.
10. A Learning Center and model-install approval flow in the PWA.

## Existing canonical capabilities retained

- owner/workspace isolation and RBAC;
- PostgreSQL task, memory, policy and audit persistence;
- action digests, attempt IDs, approval re-check and evidence-bound completion;
- encrypted Vault aliases and prompt/log secret redaction;
- Botpress and OpenAI Agents SDK reasoning providers;
- task inspector, scheduler, automations, knowledge retrieval, documents, OCR surface, media and connectors;
- GitHub PR/CI and Vercel deployment workflow.

## Code deliberately not copied

### Arbitrary shell PC connector

`Agent-2` generated a connector that accepts a remote string and executes it via
`subprocess.run(..., shell=True)`. It had no per-command allowlist, filesystem
scope, action digest, owner approval or durable execution lease. Copying it would
turn a leaked pairing token into remote code execution. The canonical agent
continues to report Remote PC as unavailable until a scoped executor exists.

### Runtime `importlib` self-patching

`Agent-2` wrote model-generated Python to a writable directory and imported it
inside the live server after only `py_compile`. Syntax checking is not a sandbox,
and Vercel filesystem changes are ephemeral. Canonical self-patching therefore
stays behind GitHub branches, CI tests, review, deployment verification and
rollback. No model-generated code is imported into the live Core process.

### Duplicate Mongo/React application

The single-file Mongo backend and second UI were not copied because doing so
would discard the stronger existing ownership, policy, approval, persistence and
deployment contracts. Their useful behavior was reimplemented as isolated
FastAPI routers and Next.js modules.

## Verification at merge time

- ALTER Core: 116 tests passed.
- Local model runtime: 3 tests passed.
- TypeScript: `tsc --noEmit` passed.
- Next.js optimized production build passed, including `/learning` and `/models`.
- No `.env`, raw secret, owner memory export or model weight is tracked.
