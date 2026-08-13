# Krea2 image-edit worker with every node used by the original workflow.
FROM runpod/worker-comfyui:5.8.6-base-cuda12.8.1

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG KREA2EDIT_COMMIT="86f886dac23013d88996e3a2e99093ba44d322fb"
ARG COMFYUI_VERSION="nightly"

ENV PYTHONUNBUFFERED=1

RUN set -eux; \
    for command in bash python python3 mktemp awk comfy git readlink sleep stat; do command -v "$command"; done; \
    test -d /comfyui; \
    test -f /comfyui/extra_model_paths.yaml; \
    test -x /start.sh; \
    python_path="$(readlink -f "$(command -v python)")"; \
    python3_path="$(readlink -f "$(command -v python3)")"; \
    test "$python_path" = "$python3_path"; \
    python -c 'import sys; p = sys.executable; assert p == "/opt/venv/bin/python" or p == "/usr/bin/python3.12" or "/opt/venv" in p, p'

# Native Krea2 CLIP support is required by the workflow. The base image ships
# with a detached ComfyUI checkout, so update that checkout explicitly before
# restoring its dependencies. No model assets are downloaded here.
RUN set -eux; \
    git -C /comfyui fetch --depth=1 origin master; \
    git -C /comfyui reset --hard FETCH_HEAD; \
    comfy --skip-prompt --workspace /comfyui install --version "$COMFYUI_VERSION" --nvidia --restore; \
    python3 -m pip install --no-cache-dir -r /comfyui/requirements.txt; \
    python3 -c 'import sys; sys.path.insert(0, "/comfyui"); import comfy.options; comfy.options.args_parsing = True; sys.argv = ["krea2-build-check", "--cpu"]; import nodes; accepted = nodes.CLIPLoader.INPUT_TYPES()["required"]["type"][0]; print("CLIPLoader accepted types:", accepted); assert "krea2" in accepted, accepted'

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

# Install every dependency declared by the custom node packs. The previous
# image only cloned some repositories, so import failures were invisible until
# the first serverless job.
RUN set -eux; \
    for requirements in /comfyui/custom_nodes/*/requirements.txt; do \
      if [[ -f "$requirements" ]]; then \
        python3 -m pip install --no-cache-dir -r "$requirements"; \
      fi; \
    done; \
    python3 -m pip uninstall -y \
      opencv-python opencv-python-headless \
      opencv-contrib-python-headless opencv-contrib-python || true; \
    python3 -m pip install --no-cache-dir \
      opencv-python opencv-python-headless opencv-contrib-python-headless; \
    python3 -m pip install --no-cache-dir opencv-contrib-python; \
    python3 -c 'from cv2.ximgproc import guidedFilter; print("OpenCV guidedFilter:", guidedFilter)'; \
    python -m pip check

# Dependency validation only; node imports and model assets are deferred to the
# mounted Network Volume and runtime startup.
COPY validate_nodes.py /tmp/validate_nodes.py
COPY krea2_lora.py /handler.py /
COPY api-workflow.json /api-workflow.json
RUN KREA2_SKIP_NODE_CHECK=1 KREA2_VALIDATE_MODEL_ASSETS=0 python3 /tmp/validate_nodes.py
COPY bootstrap.sh /usr/local/bin/krea2-runtime-init
RUN chmod +x /usr/local/bin/krea2-runtime-init
ENTRYPOINT ["/usr/local/bin/krea2-runtime-init"]

# Input images are uploaded per job by the RunPod handler; no baked example.png
# is needed.
