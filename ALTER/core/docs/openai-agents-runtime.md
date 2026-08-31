# ALTER OpenAI Agents SDK runtime

ALTER Core uses a single, no-side-effect OpenAI Agents SDK agent for chat,
reasoning and planning. This is intentionally the smallest agent loop that
proves the integration before any tools or handoffs are added.

## Contract

- provider: `openai-agents-sdk`;
- default model: `gpt-5.6`, override with `ALTER_OPENAI_MODEL`;
- credential: `vault:openai_api` or server-side `OPENAI_API_KEY`;
- output boundary: `core-policy-required`;
- side effects: always `false` in the reasoning run;
- fallback: configured Botpress `alterThink` specialist;
- external actions: only through ALTER Core Policy, Approval, Executor and
  verification-evidence paths.

The model never receives the API key. Runtime errors are normalized before they
reach the API so provider details and credentials are not leaked.

## Verification

```bash
cd ALTER/core
python -m pip install -e ".[dev]"
pytest -q
```

A live model call is valid only after `/api/agent/status` reports
`provider=openai-agents-sdk` and `configured=true`.
