# ALTER Codespaces worker

## Production role

GitHub Codespaces is an on-demand compute worker for ALTER, not its permanent
24/7 control plane:

- Vercel Core and Cockpit remain the always-available control plane.
- PostgreSQL remains the durable owner memory and task state.
- The Codespace runs Ollama and the allowlisted local model runtime while the
  Codespace is active.
- Ollama weights persist in the Codespace Docker volume across stops and normal
  restarts. They disappear if the Codespace is deleted.

GitHub stops an inactive Codespace, so a sleeping worker is reported as
unreachable while ALTER continues with its configured cloud reasoning
providers. When online, the local model can serve as a separate Deep reviewer
and an owner-controlled fallback.

## Machine fit

The dev container requests at least 4 CPU cores, 16 GB RAM and 32 GB storage.
That matches the owner's existing `turbo carnival` Codespace.

Install `qwen3-8b` first. The Ollama image plus this model fit the 32 GB worker.
Installing all three current models would leave too little safety margin for
the repository, Docker layers and package caches.

## Apply to an existing Codespace

1. Pull the latest `main` branch in the Codespace.
2. Run **Codespaces: Rebuild Container** from the command palette.
3. Verify with:

   ```bash
   bash ALTER/model_runtime/codespace-worker.sh status
   ```

4. Download the recommended model only after owner approval:

   ```bash
   bash ALTER/model_runtime/codespace-worker.sh install qwen3-8b --owner-approved
   ```

The runtime starts automatically on later Codespace starts. No model is
downloaded automatically and no secret is committed.

## Connect the production Core

Keep port 8422 private for Codespace-only work. To let the Vercel Core call the
worker, use the same long random `ALTER_MODEL_RUNTIME_TOKEN` as a GitHub
Codespaces secret and as the Core Vault value for
`vault:local_model_runtime`. Then, from inside the Codespace:

```bash
bash ALTER/model_runtime/codespace-worker.sh publish --owner-approved
bash ALTER/model_runtime/codespace-worker.sh connection
```

Set the printed HTTPS URL as `ALTER_MODEL_RUNTIME_URL` in Core. The public URL
still rejects every request without the bearer token. Restore private access
with:

```bash
bash ALTER/model_runtime/codespace-worker.sh private
```

Publishing the port and changing production secrets are deliberately not
automatic because they change an external access boundary.

## Honest limits

- Codespaces is CPU-only for this machine; local responses will be slower than
  a GPU server.
- It stops after the configured idle timeout and cannot be treated as 24/7.
- A stopped Codespace preserves storage but does not run processes.
- A deleted Codespace removes its model weights; code remains in GitHub and
  durable memory remains in PostgreSQL.
