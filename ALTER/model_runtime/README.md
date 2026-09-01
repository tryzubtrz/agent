# ALTER local model runtime

This owner-controlled service is the only component allowed to download and run
local model weights. GitHub stores its code and allowlist; Ollama stores model
weights on the runtime volume. Vercel, prompts and ordinary memory never receive
the runtime token.

## What is real in this release

- three exact Ollama references are allowlisted;
- arbitrary model names and shell commands are rejected;
- every pull requires an ALTER approval digest;
- downloads run as background jobs and are reported truthfully as queued,
  running, installed or failed;
- installed models can answer through the no-side-effect ALTER reasoning
  contract;
- the runtime can run in the 4-core / 16 GB Codespace shown by the owner, but a
  Codespace sleeps and is not a reliable 24/7 production host.

## Start on an owner PC, server or Codespace

```bash
cd ALTER/model_runtime
cp .env.example .env
# Replace the placeholder in .env with a long random token.
docker compose up -d --build
```

Expose port `8422` only through owner-controlled HTTPS. Configure ALTER Core
with `ALTER_MODEL_RUNTIME_URL`, store the matching token in
`vault:local_model_runtime`, and optionally set
`ALTER_LOCAL_MODEL_ID=qwen3-8b`.

Recommended first model for a 16 GB Codespace: `qwen3-8b` (about 5.2 GB model
download). `deepseek-r1:14b` is about 9 GB and will be much slower on CPU.

Do not commit `.env`, Ollama data or downloaded weights.

## GitHub Codespaces worker

The repository dev container now provisions a 4-core / 16 GB / 32 GB ALTER
worker and starts this runtime whenever the Codespace starts. It creates a
local-only ignored credential when no Codespaces secret is configured; the
credential value is never printed.

```bash
# Truthful container + model status
bash ALTER/model_runtime/codespace-worker.sh status

# Recommended first download (about 5.2 GB)
bash ALTER/model_runtime/codespace-worker.sh install qwen3-8b --owner-approved

# Show the stable Codespaces HTTPS endpoint without revealing its token
bash ALTER/model_runtime/codespace-worker.sh connection
```

Port 8422 is private by default. Publishing it so the Vercel Core can call it
is a separate owner-approved operation. See `ALTER/docs/CODESPACES_WORKER.md`.
