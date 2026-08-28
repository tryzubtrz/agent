# ALTER — Replit Agent audit handoff

Work only on branch `replit/alter-audit-fixes`. Do not commit directly to `main` and do not deploy production.

## Goal
Audit and improve the existing ALTER agent without rebuilding it from scratch. Preserve working architecture and behavior.

## Production references
- Web: https://alter-live.vercel.app
- Core: https://alter-app-three.vercel.app

## Priorities
1. Core ALTER agent loop and execution contract.
2. Botpress specialist integration and fail-closed behavior.
3. Documents / RAG and secret-safe retrieval.
4. Typed memory and model routing.
5. Approvals, RBAC, Vault boundaries and security.
6. Observability and connector status/self-tests.
7. Web/PWA UX, especially mobile.

Do NOT prioritize Android, browser/computer control, Telegram, Gmail, TikTok, or other deferred integrations.

## Required audit approach
Before changing anything, identify:
- what is already working;
- what is partial;
- what is broken or inconsistent;
- what is missing;
- what should be fixed next.

Then make minimal, production-safe fixes. Do not remove working features unnecessarily.

## External UX findings to verify/fix
- Empty auth form should not behave like a dead button; disable submit or show a local validation error.
- Properly associate labels with auth inputs and provide accessible names.
- Clarify Owner vs invited Operator/Viewer terminology; avoid ambiguous “Member” wording.
- Make localization intentional and consistent.
- Add/verify Content-Security-Policy where compatible with the current app.
- Verify favicon, robots.txt, sitemap.xml behavior.
- Keep auth failure behavior consistent where reasonable without weakening security.
- Verify mobile layout at narrow widths.

## Security constraints
- Never print, log, expose, or commit secrets.
- Do not modify or reveal Vault values.
- Do not weaken bearer auth, RBAC, approval policy, immutable denies, OIDC verification, or secret-safety rules.
- External actions must remain policy/approval mediated.
- Botpress remains a reasoning specialist and must not perform side effects directly.
- Do not claim a feature works unless a test verifies it.

## Verification required before finishing
- Core tests pass.
- Web production build/check passes.
- Botpress TypeScript/check passes if Botpress files change.
- No secret-like values added to repository.
- Summarize every changed behavior and remaining blocker.
- Do not deploy; leave changes on this branch for review and merge by the ALTER maintainer.
