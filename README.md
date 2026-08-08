# CMbr9Kg1 — Krea 2 Identity Edit

Docker image for the RunPod serverless Krea 2 image-edit workflow in
`api-workflow.json`.

## What changed

The image now installs and validates every non-core node used by the original
workflow:

| Node | Repository | Revision |
|---|---|---|
| `ClownsharKSampler_Beta` | [RES4LYF](https://github.com/ClownsharkBatwing/RES4LYF) | `0dc91c00c4c3fb38e7874fcd7a2a327765e8882c` |
| `easy int` / `easy float` | [ComfyUI-Easy-Use](https://github.com/yolain/ComfyUI-Easy-Use) | `130c1b5796d9876a5f853fa0bea88e808cfda4ad` |
| `LayerUtility: ImageScaleByAspectRatio` | [ComfyUI_LayerStyle](https://github.com/chflame163/ComfyUI_LayerStyle) | `d94bef1ee5ed3656f5ff1bb2830a4ffd94f40935` |
| `Power Lora Loader (rgthree)` | [rgthree-comfy](https://github.com/rgthree/rgthree-comfy) | `738105af5fb14e96fbecaf406dc356e284797e8c` |
| `Krea2EditModelPatch` / `Krea2EditGroundedEncode` | [comfyui-krea2edit](https://github.com/lbouaraba/comfyui-krea2edit) | `86f886dac23013d88996e3a2e99093ba44d322fb` |

Each node pack's `requirements.txt` is installed explicitly. The build runs
`validate_nodes.py` and fails if a required node registration or model file is
missing. This avoids deploying an image that only fails when the first job is
submitted.

## Models and LoRAs included

The Dockerfile downloads the exact files expected by the API workflow:

- `models/diffusion_models/krea2_raw_int8_convrot.safetensors`
- `models/text_encoders/qwen3vl_4b_bf16.safetensors`
- `models/vae/wan21_vae_fp32.safetensors`
- `models/loras/krea2_turbo_lora_rank_64_bf16.safetensors`
- `models/loras/krea2filterbypass.safetensors`
- `models/loras/krea2_identity_edit_v1_2.safetensors`

Source links:

- UNET: https://huggingface.co/Comfy-Org/Krea-2/resolve/main/diffusion_models/krea2_raw_int8_convrot.safetensors
- Text encoder: https://huggingface.co/Comfy-Org/Krea-2/resolve/main/text_encoders/qwen3vl_4b_bf16.safetensors
- VAE source (saved as `wan21_vae_fp32.safetensors`): https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors
- Turbo LoRA: https://huggingface.co/Comfy-Org/Krea-2/resolve/main/loras/krea2_turbo_lora_rank_64_bf16.safetensors
- Identity Edit LoRA: https://huggingface.co/conradlocke/krea2-identity-edit/resolve/main/krea2_identity_edit_v1_2.safetensors
- Filter-bypass LoRA: https://civitai.com/api/download/models/3066812

The Civitai download requires `CIVITAI_API_KEY`. `HF_TOKEN` is optional because
the official Comfy-Org VAE mirror is public. Build-time credentials must not be
committed or written into the image. The GitHub token is unrelated to Civitai
and must not be used as a substitute.

## Build locally

```bash
export HF_TOKEN='optional_huggingface_read_token'
export CIVITAI_API_KEY='civitai_api_key'

docker build \
  --build-arg HF_TOKEN="$HF_TOKEN" \
  --build-arg CIVITAI_API_KEY="$CIVITAI_API_KEY" \
  -t krea2-edit .
```

The build is intentionally strict: without the Civitai credential, or if a
download produces no non-empty file, it stops rather than creating an image that
cannot execute the original workflow. The resulting image is large; use
sufficient RunPod container/network-volume storage.

## Run locally

```bash
docker run --rm --gpus all -p 8188:8188 krea2-edit
```

The worker receives the source image through the RunPod job's `input.images`
array. No `example.png` is baked into the image.

## Deploy on RunPod

1. Push this branch to GitHub after reviewing the diff.
2. In RunPod Serverless choose **Deploy from GitHub**.
3. Select this repository and branch.
4. Configure the build argument/secret `CIVITAI_API_KEY` (`HF_TOKEN` is optional).
5. Use `api-workflow.json` as the handler's workflow payload.

Do not place RunPod, GitHub, Hugging Face, or Civitai tokens in the repository.
The GitHub repository is public, so cloning it does not require a GitHub token.

## Files

- `Dockerfile` — pinned custom nodes, model/LoRA downloads, strict validation.
- `validate_nodes.py` — build-time registration and asset check.
- `api-workflow.json` — ComfyUI API workflow.
- `workflow.json` — original canvas workflow.
