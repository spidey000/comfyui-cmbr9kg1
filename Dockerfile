# Krea2 image-edit worker with every node used by the original workflow.
FROM runpod/worker-comfyui:5.8.4-base

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Build-time credentials are only used while downloading gated assets.
# Pass them through the RunPod/GitHub build configuration; never commit them.
ARG HF_TOKEN=""
ARG CIVITAI_API_KEY=""
ARG KREA2EDIT_COMMIT="86f886dac23013d88996e3a2e99093ba44d322fb"

ENV PYTHONUNBUFFERED=1

# Clone exact revisions. A failed checkout must fail the image build instead of
# silently falling back to a branch whose node schema may not match the workflow.
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
    done

RUN set -eux; \
    install -d /comfyui/models/diffusion_models \
      /comfyui/models/text_encoders /comfyui/models/vae /comfyui/models/loras; \
    BACKOFFS=(10 20 30 60 90); \
    download_hf() { \
      local url="$1" relative_path="$2" filename="$3"; \
      for attempt in 1 2 3 4 5; do \
        if HF_TOKEN="$HF_TOKEN" comfy model download \
          --url "$url" --relative-path "$relative_path" --filename "$filename"; then \
          return 0; \
        fi; \
        if [[ "$attempt" == 5 ]]; then return 1; fi; \
        sleep "${BACKOFFS[$((attempt - 1))]}"; \
      done; \
    }; \
    download_hf \
      https://huggingface.co/Comfy-Org/Krea-2/resolve/main/diffusion_models/krea2_raw_int8_convrot.safetensors \
      models/diffusion_models krea2_raw_int8_convrot.safetensors; \
    download_hf \
      https://huggingface.co/Comfy-Org/Krea-2/resolve/main/text_encoders/qwen3vl_4b_bf16.safetensors \
      models/text_encoders qwen3vl_4b_bf16.safetensors; \
    download_hf \
      https://huggingface.co/Kijai/WanVideo/resolve/main/Wan2_1_VAE_fp32.safetensors \
      models/vae wan21_vae_fp32.safetensors; \
    download_hf \
      https://huggingface.co/Comfy-Org/Krea-2/resolve/main/loras/krea2_turbo_lora_rank_64_bf16.safetensors \
      models/loras krea2_turbo_lora_rank_64_bf16.safetensors; \
    download_hf \
      https://huggingface.co/conradlocke/krea2-identity-edit/resolve/main/krea2_identity_edit_v1_2.safetensors \
      models/loras krea2_identity_edit_v1_2.safetensors

# This public Civitai model currently requires an authenticated download.
# CIVITAI_API_KEY is a build argument only and is not written to the image.
RUN set -eux; \
    test -n "$CIVITAI_API_KEY" || { \
      echo "CIVITAI_API_KEY is required to include krea2filterbypass.safetensors" >&2; \
      exit 1; \
    }; \
    curl --fail --location --retry 3 --proto '=https' --tlsv1.2 \
      --header "Authorization: Bearer ${CIVITAI_API_KEY}" \
      --output /comfyui/models/loras/krea2filterbypass.safetensors \
      https://civitai.com/api/download/models/3066812

# Fail the build if any workflow node or model is missing. This prevents a
# broken image from reaching a RunPod endpoint and only failing on first use.
COPY validate_nodes.py /tmp/validate_nodes.py
RUN python3 /tmp/validate_nodes.py

# Input images are uploaded per job by the RunPod handler; no baked example.png
# is needed.
