#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${KREA2_MODEL_ROOT:-}" ]]; then KREA2_MODEL_ROOT=/runpod-volume/models; echo "WARNING: KREA2_MODEL_ROOT unset; defaulting to $KREA2_MODEL_ROOT" >&2; fi
[[ "$KREA2_MODEL_ROOT" == "/runpod-volume/models" ]] || echo "WARNING: KREA2_MODEL_ROOT is not /runpod-volume/models" >&2
grep -Eq '[[:space:]]/runpod-volume[[:space:]]' /proc/mounts || echo "WARNING: RunPod volume mount is not present" >&2
[[ -d /runpod-volume && -d "$KREA2_MODEL_ROOT" && -d "$KREA2_MODEL_ROOT/loras" ]] || echo "WARNING: RunPod model volume is not mounted" >&2
target="$KREA2_MODEL_ROOT/loras/krea2filterbypass.safetensors"
dir=${target%/*}
tmp=''
cleanup() { [[ -z "$tmp" ]] || rm -f -- "$tmp"; }
trap cleanup EXIT

# Load the targeted logger customization in /start.sh and its child process.
export PYTHONPATH="/opt/krea2${PYTHONPATH:+:$PYTHONPATH}"

if [[ -s "$target" ]]; then
  echo "OK: optional filter-bypass LoRA already present"
elif [[ -z "${CIVITAI_API_KEY:-}" ]]; then
  echo "WARNING: CIVITAI_API_KEY not set; skipping optional filter-bypass LoRA download" >&2
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
    print(f"WARNING: optional Civitai filter-bypass LoRA download failed{f' (HTTP {status})' if status else ''}: {exc}", file=sys.stderr)
PY
    then
      :
    else
      download_status=$?
      echo "WARNING: optional Civitai filter-bypass LoRA download command failed (status $download_status)" >&2
    fi
    if [[ -s "$tmp" ]]; then
      if mv -- "$tmp" "$target"; then
        tmp=''
        echo "OK: optional filter-bypass LoRA downloaded"
      else
        echo "WARNING: unable to atomically install optional filter-bypass LoRA" >&2
      fi
    else
      echo "WARNING: Civitai download produced no file" >&2
    fi
  else
    echo "WARNING: unable to create temporary file for optional filter-bypass LoRA" >&2
  fi
fi

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

# Optional runtime assets warn and are skipped; required assets and nodes still
# fail bootstrap.  Keep report-only unset so it cannot mask startup failures.
KREA2_MODEL_ROOT="$KREA2_MODEL_ROOT" KREA2_VALIDATE_MODEL_ASSETS=1 KREA2_VALIDATE_RUNTIME_ASSETS=1 KREA2_SKIP_NODE_CHECK=0 KREA2_REPORT_ONLY=0 python3 /tmp/validate_nodes.py
if (($# == 0)); then
  set -- /start.sh
fi
exec "$@"
