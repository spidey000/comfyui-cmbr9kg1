# CMbr9Kg1 — Krea 2 Identity Edit

Docker image for the RunPod serverless Krea 2 image-edit workflow in
`api-workflow.json`.

The image updates the existing ComfyUI workspace to the `nightly` channel
because native Krea2 CLIPLoader/model support is required. The workflow keeps
`CLIPLoader.type = "krea2"`; do not change it to `qwen_image`.

## What changed

The image installs every non-core node used by the original workflow:

| Node | Repository | Revision |
|---|---|---|
| `ClownsharKSampler_Beta` | [RES4LYF](https://github.com/ClownsharkBatwing/RES4LYF) | `0dc91c00c4c3fb38e7874fcd7a2a327765e8882c` |
| `easy int` / `easy float` | [ComfyUI-Easy-Use](https://github.com/yolain/ComfyUI-Easy-Use) | `130c1b5796d9876a5f853fa0bea88e808cfda4ad` |
| `LayerUtility: ImageScaleByAspectRatio` | [ComfyUI_LayerStyle](https://github.com/chflame163/ComfyUI_LayerStyle) | `d94bef1ee5ed3656f5ff1bb2830a4ffd94f40935` |
| `Power Lora Loader (rgthree)` | [rgthree-comfy](https://github.com/rgthree/rgthree-comfy) | `738105af5fb14e96fbecaf406dc356e284797e8c` |
| `Krea2EditModelPatch` / `Krea2EditGroundedEncode` | [comfyui-krea2edit](https://github.com/lbouaraba/comfyui-krea2edit) | `86f886dac23013d88996e3a2e99093ba44d322fb` |

Each node pack's `requirements.txt` is installed explicitly. The image uses the
pinned RunPod base `5.8.6-base-cuda12.8.1`.
The build-time assertion verifies that native Krea2 CLIPLoader support is
available before custom nodes are installed. The build validates dependencies
only; runtime validation imports ComfyUI, checks node registration, and strictly
verifies the Network Volume assets before starting the worker. Missing assets or
model-path discovery failures block startup. `KREA2_REPORT_ONLY=1` remains
available for manual diagnostics, but the production bootstrap does not use it.

## Network Volume models

Model assets are not baked into the Docker image. Attach Network Volume
`7ppvs7a5jw` and mount it at `/runpod-volume`. It must contain this canonical
layout:

- `/runpod-volume/models/unet/lustifyNSFWCheckpoint_v10Krea2.safetensors`
- `/runpod-volume/models/clip/qwen3vl_4b_fp8_scaled.safetensors`
- `/runpod-volume/models/vae/wan21_vae_fp32.safetensors`
- `/runpod-volume/models/loras/krea2_turbo_lora_rank_64_bf16.safetensors`
- `/runpod-volume/models/loras/krea2_identity_edit_v1_2.safetensors`

The required UNET is downloaded from Civitai when missing (using `CIVITAI_API_KEY`); startup fails if it cannot be obtained. The Civitai filter-bypass LoRA is OPTIONAL at startup and is attempted only when
`CIVITAI_API_KEY` is set. Prefer pre-placing it at
`/runpod-volume/models/loras/krea2filterbypass.safetensors`.

Source links:

- UNET: https://civitai.com/api/download/models/3112728?type=Other&format=SafeTensor&fp=bf16

Bootstrap verifies the UNET is exactly 13148974712 bytes with SHA-256
`0505412ED2AC568286C4BF43F8ACE93F9F5A6DD7A607F47F1912A68767E6900D` before
atomic installation. Only after successful verification does it remove the old
`krea2_raw_int8_convrot.safetensors`; an absent old file is tolerated.
- Text encoder: https://huggingface.co/Comfy-Org/Qwen3-VL/resolve/main/text_encoders/qwen3vl_4b_fp8_scaled.safetensors
- VAE source (saved as `wan21_vae_fp32.safetensors`): https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/06e001fc51048fb03433a6fb25334de7836704a5/split_files/vae/wan_2.1_vae.safetensors
- Turbo LoRA: https://huggingface.co/Comfy-Org/Krea-2/resolve/952f49d49653cb42e7d6cf7cbfad74738073ec7d/loras/krea2_turbo_lora_rank_64_bf16.safetensors
- Identity Edit LoRA: https://huggingface.co/conradlocke/krea2-identity-edit/resolve/89e9e7a09ee2e5c9331e952063d79b1b8a703280/krea2_identity_edit_v1_2.safetensors
- Filter-bypass LoRA: https://civitai.com/api/download/models/3066812
  Alternative: https://huggingface.co/Kutches/Kr3a/resolve/main/krea2filterbypass.safetensors
The standard-Python bootstrap applies a download timeout. It skips the Civitai
download when the existing file is non-empty, and atomically replaces the target
only after a downloaded file is non-empty.

Before strict runtime validation, bootstrap idempotently creates or appends a
marked `krea2_network_volume` entry in `/comfyui/extra_model_paths.yaml`, using
`KREA2_MODEL_ROOT` (normally `/runpod-volume/models`) as its `base_path` and
mapping `unet`, `clip`, `vae`, and `loras` to ComfyUI's corresponding model
folders. Existing entries in that file are preserved.

This follows ComfyUI's extra-model-paths YAML format: category values are paths
relative to `base_path`, not absolute paths. If a custom ComfyUI build expects a
different schema or category name, adjust the runtime mapping there.

## Populate the Network Volume

Run from any worker with the volume attached at `/runpod-volume` (or a local
clone of the assets). `aria2` is used because Hugging Face Xet CDNs reject
some parallel range requests; retries are expected near the end of large
files. Expected file sizes are used as the final gate.

```bash
apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y aria2
ROOT=/runpod-volume/models
download() { # url rel size
  local final="$ROOT/$2" part="$ROOT/$2.part"
  mkdir -p "$(dirname "$final")"
  if [[ -f "$final" ]] && [[ "$(stat -c %s "$final")" == "$3" ]] \
    echo "VALID $2"; return
  fi
  rm -f "$part"
  aria2c --continue=true --auto-file-renaming=false --file-allocation=none \
    --max-connection-per-server=16 --split=16 --min-split-size=1M \
    --max-tries=10 --retry-wait=5 --dir="$(dirname "$part")" \
    --out="$(basename "$part")" "$1"
  test "$(stat -c %s "$part")" = "$3"
  mv -f "$part" "$final"; echo "READY $2"
}
# The required UNET is downloaded by bootstrap using CIVITAI_API_KEY.
download https://huggingface.co/Comfy-Org/Qwen3-VL/resolve/main/text_encoders/qwen3vl_4b_fp8_scaled.safetensors clip/qwen3vl_4b_fp8_scaled.safetensors 5242467968
download https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/06e001fc51048fb03433a6fb25334de7836704a5/split_files/vae/wan_2.1_vae.safetensors vae/wan21_vae_fp32.safetensors 253815318
download https://huggingface.co/Comfy-Org/Krea-2/resolve/952f49d49653cb42e7d6cf7cbfad74738073ec7d/loras/krea2_turbo_lora_rank_64_bf16.safetensors loras/krea2_turbo_lora_rank_64_bf16.safetensors 469423778
download https://huggingface.co/conradlocke/krea2-identity-edit/resolve/89e9e7a09ee2e5c9331e952063d79b1b8a703280/krea2_identity_edit_v1_2.safetensors loras/krea2_identity_edit_v1_2.safetensors 1828256432
```

## Build locally

```bash
docker build -t krea2-edit .
```

The build validates dependencies only. Populate the Network Volume before
deployment; runtime validates node registration and all volume assets.

## Run locally

```bash
docker run --rm --gpus all -p 8188:8188 krea2-edit
```

The worker receives the source image through the RunPod job's `input.images`
array. No `example.png` is baked into the image.

Optional `input.lora_downloads` accepts 1–7 `{url, strength}` objects (HTTPS
Hugging Face or Civitai URLs, strength 0–2). `input.civitai_token` may provide
per-job Civitai authorization; downloaded LoRAs are removed after the job.

## Deploy on RunPod

1. Push this branch to GitHub after reviewing the diff.
2. In RunPod Serverless choose **Deploy from GitHub** and attach the configured
   Network Volume at `/runpod-volume`.
3. Select this repository and branch.
4. Configure the endpoint runtime environment exactly as:
   `CIVITAI_API_KEY={{ RUNPOD_SECRET_CIVITAI_API_KEY }}` and
   `KREA2_MODEL_ROOT=/runpod-volume/models`. Startup validates the volume,
   seeds the Civitai LoRA, and validates assets before ComfyUI starts.
5. Use `api-workflow.json` as the handler's workflow payload. It is the
   complete API-format conversion of the source workflow. Each
   `input.images[].name` must exactly match the corresponding
   `LoadImage.image`; the fixture uses `example.png`, but a client may send a
   different filename when all references are changed consistently.

Do not place RunPod, GitHub, Hugging Face, or Civitai tokens in the repository.
The GitHub repository is public, so cloning it does not require a GitHub token.

## Files

- `Dockerfile` — pinned custom nodes and strict validation.
- `bootstrap.sh` — runtime optional download and worker startup.
- `validate_nodes.py` — strict runtime node-registration and model-volume check.
- `api-workflow.json` — ComfyUI API workflow.
- `workflow.json` — original canvas workflow.

## Release gates

Expected file sizes for public model assets and the GPU smoke E2E test are
release gates. If they are not automated in the release pipeline yet, run and
record both checks manually before publishing an image.
