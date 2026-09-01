#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

python -m pip install --disable-pip-version-check \
  -e 'ALTER/core[dev]' \
  -e 'ALTER/model_runtime[dev]'

(
  cd ALTER/web
  npm install --no-audit --no-fund --no-package-lock
)

(
  cd ALTER/botpress
  npm install --no-audit --no-fund --no-package-lock
)

echo "ALTER development dependencies are ready. Model weights were not downloaded."
