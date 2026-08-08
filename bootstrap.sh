#!/usr/bin/env bash
set -euo pipefail

target=/comfyui/models/loras/krea2filterbypass.safetensors
dir=${target%/*}
expected_sha256=AC6114D7112AE2397EB26B9E6E9623AAD059D346FC285EA050FFB042C7C6748E
tmp=''
cleanup() { [[ -z "$tmp" ]] || rm -f -- "$tmp"; }
trap cleanup EXIT

current_sha256=''
if [[ -s "$target" ]]; then
  current_sha256=$(sha256sum "$target" | awk '{print toupper($1)}')
fi
if [[ "$current_sha256" != "$expected_sha256" ]]; then
  [[ -n "${CIVITAI_API_KEY:-}" ]] || { echo "CIVITAI_API_KEY is required for the runtime Civitai download" >&2; exit 1; }
  tmp=$(mktemp "$dir/.krea2filterbypass.XXXXXX")
  curl --fail --location --retry 3 --proto '=https' --tlsv1.2 \
    --header "Authorization: Bearer ${CIVITAI_API_KEY}" \
    --output "$tmp" https://civitai.com/api/download/models/3066812
  [[ -s "$tmp" ]] || { echo "Civitai download produced no file" >&2; exit 1; }
  downloaded_sha256=$(sha256sum "$tmp" | awk '{print toupper($1)}')
  [[ "$downloaded_sha256" == "$expected_sha256" ]] || { echo "Civitai download checksum mismatch" >&2; exit 1; }
  mv -- "$tmp" "$target"
  tmp=''
fi

KREA2_VALIDATE_RUNTIME_ASSETS=1 python3 /tmp/validate_nodes.py
if (($# == 0)); then
  set -- /start.sh
fi
exec "$@"
