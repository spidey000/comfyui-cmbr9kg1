#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${KREA2_MODEL_ROOT:-}" ]]; then KREA2_MODEL_ROOT=/runpod-volume/models; echo "WARNING: KREA2_MODEL_ROOT unset; defaulting to $KREA2_MODEL_ROOT" >&2; fi
[[ "$KREA2_MODEL_ROOT" == "/runpod-volume/models" ]] || echo "WARNING: KREA2_MODEL_ROOT is not /runpod-volume/models" >&2
grep -Eq '[[:space:]]/runpod-volume[[:space:]]' /proc/mounts || echo "WARNING: RunPod volume mount is not present" >&2
[[ -d /runpod-volume && -d "$KREA2_MODEL_ROOT" && -d "$KREA2_MODEL_ROOT/loras" ]] || echo "WARNING: RunPod model volume is not mounted" >&2
target="$KREA2_MODEL_ROOT/loras/krea2filterbypass.safetensors"
filter_size=160
filter_sha256=ac6114d7112ae2397eb26b9e6e9623aad059d346fc285ea050ffb042c7c6748e
unet_target="$KREA2_MODEL_ROOT/unet/lustifyNSFWCheckpoint_v10Krea2.safetensors"
dir=${target%/*}
tmp=''
cleanup() { [[ -z "$tmp" ]] || rm -f -- "$tmp"; }
trap cleanup EXIT

if [[ -f "$target" ]] && [[ "$(stat -c %s "$target")" == "$filter_size" ]] && [[ "$(sha256sum "$target" | cut -d' ' -f1)" == "$filter_sha256" ]]; then
  echo "OK: required filter-bypass LoRA already present"
elif [[ -z "${CIVITAI_API_KEY:-}" ]]; then
  echo "ERROR: CIVITAI_API_KEY is required because the required filter-bypass LoRA is missing or invalid" >&2
  exit 1
else
  if tmp=$(mktemp "$dir/.krea2filterbypass.XXXXXX" 2>/dev/null); then
    download_status=0
    if python3 - "$tmp" <<'PY'
import os
import sys
import urllib.request

destination = sys.argv[1]
request = urllib.request.Request(
    "https://civitai.com/api/download/models/3066812",
    headers={"Authorization": f"Bearer {os.environ['CIVITAI_API_KEY']}"},
)
try:
    with urllib.request.urlopen(request, timeout=120) as response, open(destination, "wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
except Exception as exc:
    status = getattr(exc, "code", None)
    print(f"ERROR: required Civitai filter-bypass LoRA download failed{f' (HTTP {status})' if status else ''}: {exc}", file=sys.stderr)
    raise SystemExit(1)
PY
    then
      :
    else
      download_status=$?
      echo "ERROR: required Civitai filter-bypass LoRA download command failed (status $download_status)" >&2
    fi
    if [[ "$download_status" -eq 0 ]] && python3 - "$tmp" "$filter_size" "$filter_sha256" <<'PY'
import hashlib, sys
path, size, expected = sys.argv[1], int(sys.argv[2]), sys.argv[3]
digest = hashlib.sha256()
with open(path, "rb") as source:
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
        digest.update(chunk)
if __import__("os").path.getsize(path) != size or digest.hexdigest() != expected:
    print("ERROR: downloaded filter-bypass LoRA failed size or SHA-256 verification", file=sys.stderr)
    raise SystemExit(1)
PY
    then
      if mv -- "$tmp" "$target"; then
        tmp=''
        echo "OK: required filter-bypass LoRA downloaded"
      else
        echo "ERROR: unable to atomically install required filter-bypass LoRA" >&2
        exit 1
      fi
    else
      echo "ERROR: Civitai download produced no verified required filter-bypass LoRA file" >&2
      exit 1
    fi
  else
    echo "ERROR: unable to create temporary file for required filter-bypass LoRA" >&2
    exit 1
  fi
fi

unet_old="$KREA2_MODEL_ROOT/unet/krea2_raw_int8_convrot.safetensors"
unet_sha256=0505412ED2AC568286C4BF43F8ACE93F9F5A6DD7A607F47F1912A68767E6900D
unet_size=13148974712
unet_valid=0
if [[ -f "$unet_target" ]] && [[ "$(stat -c %s "$unet_target")" == "$unet_size" ]] && [[ "$(sha256sum "$unet_target" | cut -d' ' -f1)" == "${unet_sha256,,}" ]]; then
  unet_valid=1
fi
if (( ! unet_valid )); then
  [[ -n "${CIVITAI_API_KEY:-}" ]] || { echo "ERROR: CIVITAI_API_KEY is required because the required UNET is missing or invalid" >&2; exit 1; }
  unet_dir=${unet_target%/*}; mkdir -p "$unet_dir"
  unet_tmp=$(mktemp "$unet_dir/.lustifyNSFWCheckpoint_v10Krea2.XXXXXX"); tmp="$unet_tmp"
  python3 - "$unet_tmp" "$unet_size" "$unet_sha256" <<'PY'
import hashlib, os, sys, urllib.request
destination, expected_size, expected_hash = sys.argv[1], int(sys.argv[2]), sys.argv[3].lower()
request = urllib.request.Request("https://civitai.com/api/download/models/3112728?type=Other&format=SafeTensor&fp=bf16", headers={"Authorization": f"Bearer {os.environ['CIVITAI_API_KEY']}"})
try:
    with urllib.request.urlopen(request, timeout=120) as response, open(destination, "wb") as output:
        while chunk := response.read(1024 * 1024): output.write(chunk)
except Exception as exc:
    status = getattr(exc, "code", None)
    print(f"ERROR: required UNET download failed{f' (HTTP {status})' if status else ''}", file=sys.stderr)
    raise SystemExit(1)
actual_size = os.path.getsize(destination)
digest = hashlib.sha256()
with open(destination, "rb") as verified:
    while chunk := verified.read(1024 * 1024): digest.update(chunk)
actual_hash = digest.hexdigest()
if actual_size != expected_size or actual_hash != expected_hash:
    print("ERROR: downloaded UNET failed size or SHA-256 verification", file=sys.stderr)
    raise SystemExit(1)
PY
  mv -- "$unet_tmp" "$unet_target"; tmp=''; unet_valid=1
fi
if (( unet_valid )); then rm -f -- "$unet_old"; fi

# Register the Network Volume with ComfyUI without replacing any existing
# manifests. The marked block makes this safe to run on every container start.
python3 - <<'PY'
import os
import tempfile

path = "/comfyui/extra_model_paths.yaml"
marker = "# KREA2_NETWORK_VOLUME_BEGIN"
root = os.environ.get("KREA2_MODEL_ROOT", "/runpod-volume/models")
block = f"""{marker}
krea2_network_volume:
  base_path: {root}
  diffusion_models: unet
  text_encoders: clip
  vae: vae
  loras: loras
# KREA2_NETWORK_VOLUME_END
"""

try:
    with open(path, encoding="utf-8") as existing:
        content = existing.read()
except FileNotFoundError:
    content = ""

if marker not in content:
    prefix = content if not content or content.endswith("\n") else content + "\n"
    updated = prefix + ("\n" if prefix else "") + block
    directory = os.path.dirname(path) or "."
    fd, temporary = tempfile.mkstemp(prefix=".extra_model_paths.", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(updated)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
PY

# Runtime assets and nodes are strict prerequisites for the bundled workflow.
# Keep report-only unset so it cannot mask startup failures.
KREA2_MODEL_ROOT="$KREA2_MODEL_ROOT" KREA2_VALIDATE_MODEL_ASSETS=1 KREA2_VALIDATE_RUNTIME_ASSETS=1 KREA2_SKIP_NODE_CHECK=0 KREA2_REPORT_ONLY=0 python3 /tmp/validate_nodes.py
if (($# == 0)); then
  set -- /start.sh
fi
exec "$@"
