# Krea2 image-edit worker with every node used by the original workflow.
FROM runpod/worker-comfyui:5.8.4-base@sha256:81db5414200d8c5c8163e7e0da5fe4fbb6c49bd80cb1632417e0ab4ce1329ac6

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG KREA2EDIT_COMMIT="86f886dac23013d88996e3a2e99093ba44d322fb"
ARG KREA2_SKIP_NODE_CHECK=0

ENV PYTHONUNBUFFERED=1

RUN set -eux; \
    for command in bash python python3 sha256sum mktemp awk comfy git readlink sleep stat; do command -v "$command"; done; \
    test -d /comfyui; \
    test -x /start.sh; \
    python_path="$(readlink -f "$(command -v python)")"; \
    python3_path="$(readlink -f "$(command -v python3)")"; \
    test "$python_path" = "$python3_path"; \
    python -c 'import sys; assert sys.executable == "'"$python_path"'"'

# Clone exact revisions. A failed checkout must fail the image build instead of
# silently falling back to a branch whose node schema may not match the workflow.
# The VAE keeps the filename expected by the original workflow while using the
# public official Comfy-Org repackaged Wan VAE instead of the gated Kijai URL.
RUN set -eux; \
    install -d /comfyui/custom_nodes; \
    clone_node() { \
      local repo="$1" dest="$2" commit="$3"; \
      git clone --depth=1 "https://github.com/${repo}.git" "$dest"; \
      git -C "$dest" fetch --depth=1 origin "$commit"; \
      git -C "$dest" checkout --detach "$commit"; \
    }; \
    clone_node "ClownsharkBatwing/RES4LYF" \
      /comfyui/custom_nodes/RES4LYF \
      0dc91c00c4c3fb38e7874fcd7a2a327765e8882c; \
    clone_node "yolain/ComfyUI-Easy-Use" \
      /comfyui/custom_nodes/ComfyUI-Easy-Use \
      130c1b5796d9876a5f853fa0bea88e808cfda4ad; \
    clone_node "chflame163/ComfyUI_LayerStyle" \
      /comfyui/custom_nodes/ComfyUI_LayerStyle \
      d94bef1ee5ed3656f5ff1bb2830a4ffd94f40935; \
    clone_node "rgthree/rgthree-comfy" \
      /comfyui/custom_nodes/rgthree-comfy \
      738105af5fb14e96fbecaf406dc356e284797e8c; \
    clone_node "lbouaraba/comfyui-krea2edit" \
      /comfyui/custom_nodes/comfyui-krea2edit \
      "$KREA2EDIT_COMMIT"

# Compatibility alias: preserve the literal `beta` scheduler used by the
# source Pastebin workflow with the pinned RES4LYF commit.
RUN python3 - <<'PY'
from pathlib import Path
import ast
import re

root = Path("/comfyui/custom_nodes/RES4LYF")
helper = root / "helper.py"
samplers = root / "beta" / "samplers.py"
for path in (helper, samplers):
    if not path.is_file():
        raise SystemExit(f"Expected RES4LYF file is missing: {path}")

helper_text = helper.read_text()
helper_tree = ast.parse(helper_text, filename=str(helper))
helper_node = next(
    (node for node in ast.walk(helper_tree)
     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
     and node.name == "get_res4lyf_scheduler_list"),
    None,
)
if helper_node is None or not hasattr(helper_node, "end_lineno"):
    raise SystemExit("RES4LYF scheduler helper structure changed")
helper_lines = helper_text.splitlines(keepends=True)
start, end = helper_node.lineno - 1, helper_node.end_lineno
body = "".join(helper_lines[start:end])
block_pattern = re.compile(
    r"(?m)^(?P<indent>[ \t]*)if (?P<quote>['\"])beta57(?P=quote) not in scheduler_names:\n"
    r"(?P=indent)[ \t]+scheduler_names\.append\((?P=quote)beta57(?P=quote)\)"
)
block_matches = list(block_pattern.finditer(body))
if len(block_matches) != 1:
    raise SystemExit("Expected exactly one beta57 scheduler block")
match = block_matches[0]
indent, quote = match.group("indent"), match.group("quote")
replacement = (
    f"{indent}if {quote}beta{quote} not in scheduler_names:\n"
    f"{indent}    scheduler_names.append({quote}beta{quote})\n"
    f"{indent}if {quote}beta57{quote} not in scheduler_names:\n"
    f"{indent}    scheduler_names.append({quote}beta57{quote})"
)
updated_body = body[:match.start()] + replacement + body[match.end():]
helper.write_text("".join(helper_lines[:start]) + updated_body + "".join(helper_lines[end:]))

helper_tree = ast.parse(helper.read_text(), filename=str(helper))
literal_values = {
    node.value for node in ast.walk(helper_tree)
    if isinstance(node, ast.Constant) and isinstance(node.value, str)
}
if not {"beta", "beta57"} <= literal_values:
    raise SystemExit("Helper does not contain separate beta scheduler literals")
if any(
    isinstance(node, ast.Call)
    and isinstance(node.func, ast.Attribute)
    and node.func.attr == "append"
    and len(node.args) == 2
    and all(isinstance(arg, ast.Constant) for arg in node.args)
    and [arg.value for arg in node.args] == ["beta", "beta57"]
    for node in ast.walk(helper_tree)
):
    raise SystemExit("Helper contains an invalid multi-argument append")

samplers_text = samplers.read_text()
samplers_tree = ast.parse(samplers_text, filename=str(samplers))
sigmas = next(
    (node for node in ast.walk(samplers_tree)
     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
     and node.name == "get_sigmas"),
    None,
)
if sigmas is None or not hasattr(sigmas, "end_lineno"):
    raise SystemExit("RES4LYF get_sigmas structure changed")
sampler_lines = samplers_text.splitlines(keepends=True)
start, end = sigmas.lineno - 1, sigmas.end_lineno
body = "".join(sampler_lines[start:end])
pattern = re.compile(r"scheduler == (['\"])beta57\1")
matches = list(pattern.finditer(body))
if len(matches) != 1:
    raise SystemExit("Unexpected beta57 condition in RES4LYF get_sigmas")
body = body[:matches[0].start()] + "scheduler in ('beta', 'beta57')" + body[matches[0].end():]
samplers.write_text("".join(sampler_lines[:start]) + body + "".join(sampler_lines[end:]))
ast.parse(samplers.read_text(), filename=str(samplers))
PY

# Install every dependency declared by the custom node packs. The previous
# image only cloned some repositories, so import failures were invisible until
# the first serverless job.
RUN set -eux; \
    for requirements in /comfyui/custom_nodes/*/requirements.txt; do \
      if [[ -f "$requirements" ]]; then \
        python3 -m pip install --no-cache-dir -r "$requirements"; \
      fi; \
    done; \
    python -m pip check

RUN set -eux; \
    install -d /comfyui/models/diffusion_models \
      /comfyui/models/text_encoders /comfyui/models/vae /comfyui/models/loras; \
    BACKOFFS=(10 20 30 60 90); \
    download_hf() { \
      local url="$1" relative_path="$2" filename="$3" expected_size="$4" expected_sha256="$5"; \
      local target="/comfyui/${relative_path}/${filename}"; \
      for attempt in 1 2 3 4 5; do \
        rm -f "$target"; \
        if comfy model download \
          --url "$url" --relative-path "$relative_path" --filename "$filename" \
          && [[ -s "$target" ]] \
          && [[ "$(stat -c '%s' "$target")" == "$expected_size" ]] \
          && printf '%s  %s\n' "$expected_sha256" "$target" | sha256sum -c -; then \
          return 0; \
        fi; \
        echo "Download failed or produced no file: $filename (attempt $attempt/5)" >&2; \
        if [[ "$attempt" == 5 ]]; then return 1; fi; \
        sleep "${BACKOFFS[$((attempt - 1))]}"; \
      done; \
    }; \
    download_hf \
      https://huggingface.co/Comfy-Org/Krea-2/resolve/952f49d49653cb42e7d6cf7cbfad74738073ec7d/diffusion_models/krea2_raw_int8_convrot.safetensors \
      models/diffusion_models krea2_raw_int8_convrot.safetensors 13492686496 5585a4a38c4bcfb6fde2d480a4aa6edf7f665721ebde56d30662c35a45f5fa5c; \
    download_hf \
      https://huggingface.co/Comfy-Org/Krea-2/resolve/952f49d49653cb42e7d6cf7cbfad74738073ec7d/text_encoders/qwen3vl_4b_bf16.safetensors \
      models/text_encoders qwen3vl_4b_bf16.safetensors 8875719384 36f3ff447ef59201722e8f9ce6020c9819fdcfba6aa2608c4e09b1c0ce114e34; \
    download_hf \
      https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/06e001fc51048fb03433a6fb25334de7836704a5/split_files/vae/wan_2.1_vae.safetensors \
      models/vae wan21_vae_fp32.safetensors 253815318 2fc39d31359a4b0a64f55876d8ff7fa8d780956ae2cb13463b0223e15148976b; \
    download_hf \
      https://huggingface.co/Comfy-Org/Krea-2/resolve/952f49d49653cb42e7d6cf7cbfad74738073ec7d/loras/krea2_turbo_lora_rank_64_bf16.safetensors \
      models/loras krea2_turbo_lora_rank_64_bf16.safetensors 469423778 db8c5bae0a415d448da9d842111d6e51f7d32e47143a3118eb267e5c4773de87; \
    download_hf \
      https://huggingface.co/conradlocke/krea2-identity-edit/resolve/89e9e7a09ee2e5c9331e952063d79b1b8a703280/krea2_identity_edit_v1_2.safetensors \
      models/loras krea2_identity_edit_v1_2.safetensors 1828256432 6adf9a69cc9502d286db7b69964d37da7e9cfe4b05b4d004bc275f087d3fd3cf

# Fail the build if any workflow node or model is missing. This prevents a
# broken image from reaching a RunPod endpoint and only failing on first use.
COPY validate_nodes.py /tmp/validate_nodes.py
RUN KREA2_SKIP_NODE_CHECK="$KREA2_SKIP_NODE_CHECK" python3 /tmp/validate_nodes.py
COPY bootstrap.sh /usr/local/bin/krea2-runtime-init
RUN chmod +x /usr/local/bin/krea2-runtime-init
ENTRYPOINT ["/usr/local/bin/krea2-runtime-init"]

# Input images are uploaded per job by the RunPod handler; no baked example.png
# is needed.
