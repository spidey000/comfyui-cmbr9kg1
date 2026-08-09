# CMbr9Kg1 — Krea 2 Identity Edit

Docker image for the RunPod serverless Krea 2 image-edit workflow in
`api-workflow.json`.

## What changed

The image installs every non-core node used by the original workflow:

| Node | Repository | Revision |
|---|---|---|
| `ClownsharKSampler_Beta` | [RES4LYF](https://github.com/ClownsharkBatwing/RES4LYF) | `0dc91c00c4c3fb38e7874fcd7a2a327765e8882c` |
| `easy int` / `easy float` | [ComfyUI-Easy-Use](https://github.com/yolain/ComfyUI-Easy-Use) | `130c1b5796d9876a5f853fa0bea88e808cfda4ad` |
| `LayerUtility: ImageScaleByAspectRatio` | [ComfyUI_LayerStyle](https://github.com/chflame163/ComfyUI_LayerStyle) | `d94bef1ee5ed3656f5ff1bb2830a4ffd94f40935` |
| `Power Lora Loader (rgthree)` | [rgthree-comfy](https://github.com/rgthree/rgthree-comfy) | `738105af5fb14e96fbecaf406dc356e284797e8c` |
| `Krea2EditModelPatch` / `Krea2EditGroundedEncode` | [comfyui-krea2edit](https://github.com/lbouaraba/comfyui-krea2edit) | `86f886dac23013d88996e3a2e99093ba44d322fb` |

Each node pack's `requirements.txt` is installed explicitly. The build validates
dependencies only; runtime validation imports ComfyUI, checks node registration,
and verifies the Network Volume assets in report-only mode: warnings never block
worker startup. Strict validation remains available with `KREA2_REPORT_ONLY=0`
for manual/CI checks.

## Network Volume models

Model assets are not baked into the Docker image. Attach Network Volume
`7ppvs7a5jw` and mount it at `/runpod-volume`. It must contain this canonical
layout:

- `/runpod-volume/models/unet/krea2_raw_int8_convrot.safetensors`
- `/runpod-volume/models/clip/qwen3vl_4b_bf16.safetensors`
- `/runpod-volume/models/vae/wan21_vae_fp32.safetensors`
- `/runpod-volume/models/loras/krea2_turbo_lora_rank_64_bf16.safetensors`
- `/runpod-volume/models/loras/krea2_identity_edit_v1_2.safetensors`

The Civitai filter-bypass LoRA is OPTIONAL at startup and is attempted only when
`CIVITAI_API_KEY` is set. Prefer pre-placing it at
`/runpod-volume/models/loras/krea2filterbypass.safetensors`.

Source links:

- UNET: https://huggingface.co/Comfy-Org/Krea-2/resolve/952f49d49653cb42e7d6cf7cbfad74738073ec7d/diffusion_models/krea2_raw_int8_convrot.safetensors
- Text encoder: https://huggingface.co/Comfy-Org/Krea-2/resolve/952f49d49653cb42e7d6cf7cbfad74738073ec7d/text_encoders/qwen3vl_4b_bf16.safetensors
- VAE source (saved as `wan21_vae_fp32.safetensors`): https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/06e001fc51048fb03433a6fb25334de7836704a5/split_files/vae/wan_2.1_vae.safetensors
- Turbo LoRA: https://huggingface.co/Comfy-Org/Krea-2/resolve/952f49d49653cb42e7d6cf7cbfad74738073ec7d/loras/krea2_turbo_lora_rank_64_bf16.safetensors
- Identity Edit LoRA: https://huggingface.co/conradlocke/krea2-identity-edit/resolve/89e9e7a09ee2e5c9331e952063d79b1b8a703280/krea2_identity_edit_v1_2.safetensors
- Filter-bypass LoRA: https://civitai.com/api/download/models/3066812
  Alternative: https://huggingface.co/Kutches/Kr3a/resolve/main/krea2filterbypass.safetensors
  Expected SHA-256: `AC6114D7112AE2397EB26B9E6E9623AAD059D346FC285EA050FFB042C7C6748E`

The standard-Python bootstrap applies a download timeout and checksum
verification. It skips the Civitai download only when the existing file matches
the published checksum, and otherwise verifies the downloaded file before
atomically replacing it.

## Populate the Network Volume

Run from any worker with the volume attached at `/runpod-volume` (or a local
clone of the assets). `aria2` is used because Hugging Face Xet CDNs reject
some parallel range requests; retries are expected near the end of large
files and the checksum below is the final gate.

```bash
apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y aria2
ROOT=/runpod-volume/models
download() { # url rel size sha256
  local final="$ROOT/$2" part="$ROOT/$2.part"
  mkdir -p "$(dirname "$final")"
  if [[ -f "$final" ]] && [[ "$(stat -c %s "$final")" == "$3" ]] \
     && echo "$4  $final" | sha256sum -c - >/dev/null 2>&1; then
    echo "VALID $2"; return
  fi
  rm -f "$part"
  aria2c --continue=true --auto-file-renaming=false --file-allocation=none \
    --max-connection-per-server=16 --split=16 --min-split-size=1M \
    --max-tries=10 --retry-wait=5 --dir="$(dirname "$part")" \
    --out="$(basename "$part")" "$1"
  test "$(stat -c %s "$part")" = "$3"
  echo "$4  $part" | sha256sum -c -
  mv -f "$part" "$final"; echo "READY $2"
}
download https://huggingface.co/Comfy-Org/Krea-2/resolve/952f49d49653cb42e7d6cf7cbfad74738073ec7d/diffusion_models/krea2_raw_int8_convrot.safetensors unet/krea2_raw_int8_convrot.safetensors 13492686496 5585a4a38c4bcfb6fde2d480a4aa6edf7f665721ebde56d30662c35a45f5fa5c
download https://huggingface.co/Comfy-Org/Krea-2/resolve/952f49d49653cb42e7d6cf7cbfad74738073ec7d/text_encoders/qwen3vl_4b_bf16.safetensors clip/qwen3vl_4b_bf16.safetensors 8875719384 36f3ff447ef59201722e8f9ce6020c9819fdcfba6aa2608c4e09b1c0ce114e34
download https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/06e001fc51048fb03433a6fb25334de7836704a5/split_files/vae/wan_2.1_vae.safetensors vae/wan21_vae_fp32.safetensors 253815318 2fc39d31359a4b0a64f55876d8ff7fa8d780956ae2cb13463b0223e15148976b
download https://huggingface.co/Comfy-Org/Krea-2/resolve/952f49d49653cb42e7d6cf7cbfad74738073ec7d/loras/krea2_turbo_lora_rank_64_bf16.safetensors loras/krea2_turbo_lora_rank_64_bf16.safetensors 469423778 db8c5bae0a415d448da9d842111d6e51f7d32e47143a3118eb267e5c4773de87
download https://huggingface.co/conradlocke/krea2-identity-edit/resolve/89e9e7a09ee2e5c9331e952063d79b1b8a703280/krea2_identity_edit_v1_2.safetensors loras/krea2_identity_edit_v1_2.safetensors 1828256432 6adf9a69cc9502d286db7b69964d37da7e9cfe4b05b4d004bc275f087d3fd3cf
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
- `bootstrap.sh` — runtime checksum verification/download and worker startup.
- `validate_nodes.py` — strict runtime node-registration and model-volume check.
- `api-workflow.json` — ComfyUI API workflow.
- `workflow.json` — original canvas workflow.

## Release gates

Verification of hashes for public model assets and the GPU smoke E2E test are
release gates. If they are not automated in the release pipeline yet, run and
record both checks manually before publishing an image.
