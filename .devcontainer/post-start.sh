#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

if ! bash ALTER/model_runtime/codespace-worker.sh start; then
  echo "ALTER model runtime did not start. Run 'bash ALTER/model_runtime/codespace-worker.sh status' for the truthful state." >&2
fi

# A runtime startup failure must not make the whole development environment unusable.
exit 0
