#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"
state_dir="${ALTER_RUNTIME_STATE_DIR:-$repo_root/.alter-runtime}"
token_file="$state_dir/model-runtime-token"
runtime_token=""
compose=(docker compose --project-name alter-model-runtime --file "$script_dir/docker-compose.yml")

usage() {
  cat <<'EOF'
Usage:
  codespace-worker.sh start
  codespace-worker.sh status
  codespace-worker.sh install <qwen3-8b|deepseek-r1-distill-qwen-14b|qwen2.5-coder-7b-instruct> --owner-approved
  codespace-worker.sh connection
  codespace-worker.sh publish --owner-approved
  codespace-worker.sh private

The runtime token is never printed. Model downloads and public port exposure
require an explicit owner-approved command.
EOF
}

die() {
  echo "ALTER worker error: $*" >&2
  exit 1
}

require_tool() {
  command -v "$1" >/dev/null 2>&1 || die "required command '$1' is unavailable"
}

load_runtime_token() {
  umask 077
  mkdir -p "$state_dir"

  if [[ -n "${ALTER_MODEL_RUNTIME_TOKEN:-}" ]]; then
    runtime_token="$ALTER_MODEL_RUNTIME_TOKEN"
  elif [[ -s "$token_file" ]]; then
    IFS= read -r runtime_token < "$token_file"
  else
    require_tool openssl
    runtime_token="$(openssl rand -hex 32)"
    printf '%s\n' "$runtime_token" > "$token_file"
    chmod 600 "$token_file"
    echo "ALTER created a local-only runtime credential in an ignored owner file. Its value was not printed."
  fi

  if [[ ! "$runtime_token" =~ ^[A-Za-z0-9_-]{32,256}$ ]]; then
    die "ALTER_MODEL_RUNTIME_TOKEN must contain 32-256 URL-safe characters"
  fi
  export ALTER_MODEL_RUNTIME_TOKEN="$runtime_token"
}

wait_for_docker() {
  require_tool docker
  for _attempt in $(seq 1 60); do
    if docker info >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  die "Docker did not become ready within 60 seconds; rebuild the Codespace container"
}

runtime_request() {
  local method="$1"
  local path="$2"
  local payload="${3:-}"
  local args=(--silent --show-error --fail-with-body --request "$method" --header "Authorization: Bearer $runtime_token" --header "Accept: application/json")
  if [[ -n "$payload" ]]; then
    args+=(--header "Content-Type: application/json" --data-binary "$payload")
  fi
  curl "${args[@]}" "http://127.0.0.1:8422$path"
}

wait_for_runtime() {
  for _attempt in $(seq 1 120); do
    if runtime_request GET /health >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  "${compose[@]}" ps >&2 || true
  die "model runtime did not become healthy within 120 seconds"
}

start_worker() {
  require_tool curl
  load_runtime_token
  wait_for_docker
  "${compose[@]}" up --detach --build
  wait_for_runtime
  echo "ALTER worker is online. Port 8422 remains private unless the owner explicitly publishes it."
  runtime_request GET /health
  echo
}

status_worker() {
  require_tool curl
  load_runtime_token
  wait_for_docker
  "${compose[@]}" ps
  runtime_request GET /health
  echo
}

install_model() {
  local model_id="${1:-}"
  local approval="${2:-}"
  case "$model_id" in
    qwen3-8b|deepseek-r1-distill-qwen-14b|qwen2.5-coder-7b-instruct) ;;
    *) die "model is not in the exact ALTER allowlist" ;;
  esac
  [[ "$approval" == "--owner-approved" ]] || die "model download requires the final argument --owner-approved"

  start_worker >/dev/null
  local digest
  digest="$(printf 'codespace-owner-approved:%s:%s' "$model_id" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" | sha256sum | cut -d ' ' -f 1)"
  runtime_request POST "/v1/models/$model_id/pull" "{\"approval_digest\":\"$digest\"}"
  echo
  echo "ALTER accepted the allowlisted download job. Use 'codespace-worker.sh status' to verify installation."
}

connection_info() {
  if [[ -n "${CODESPACE_NAME:-}" ]]; then
    echo "https://${CODESPACE_NAME}-8422.app.github.dev"
  else
    echo "http://127.0.0.1:8422"
  fi
  echo "The endpoint requires the runtime bearer token; the token is intentionally not printed."
}

change_visibility() {
  local visibility="$1"
  local approval="${2:-}"
  require_tool gh
  [[ -n "${CODESPACE_NAME:-}" ]] || die "port visibility can only be changed inside GitHub Codespaces"
  if [[ "$visibility" == "public" && "$approval" != "--owner-approved" ]]; then
    die "public exposure requires the final argument --owner-approved"
  fi
  gh codespace ports visibility "8422:$visibility" --codespace "$CODESPACE_NAME"
  echo "ALTER runtime port 8422 visibility is now $visibility. Bearer authentication remains mandatory."
}

command_name="${1:-}"
case "$command_name" in
  start) start_worker ;;
  status) status_worker ;;
  install) install_model "${2:-}" "${3:-}" ;;
  connection) connection_info ;;
  publish) change_visibility public "${2:-}" ;;
  private) change_visibility private ;;
  help|-h|--help|"") usage ;;
  *) usage >&2; exit 2 ;;
esac
