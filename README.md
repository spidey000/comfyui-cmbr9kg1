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
`validate_nodes.py` and, by default, imports ComfyUI on CPU to validate the
registration of every node in the workflow. `KREA2_SKIP_NODE_CHECK=1` is only
a diagnostic escape for environments where that check cannot run; it must not
be used as the normal build configuration. Runtime validation remains strict
and fails if a required node or model is missing; no GPU check is added.

The Pastebin workflow uses the literal scheduler value `beta`. The image keeps
that value available through a fail-closed alias for the pinned RES4LYF
revision, so a missing or incompatible scheduler alias causes validation to
fail rather than silently selecting another scheduler.

## Models and LoRAs included

The Dockerfile downloads the exact files expected by the API workflow:

- `models/diffusion_models/krea2_raw_int8_convrot.safetensors`
- `models/text_encoders/qwen3vl_4b_bf16.safetensors`
- `models/vae/wan21_vae_fp32.safetensors`
- `models/loras/krea2_turbo_lora_rank_64_bf16.safetensors`
- `models/loras/krea2filterbypass.safetensors` (downloaded at worker startup)
- `models/loras/krea2_identity_edit_v1_2.safetensors`

Source links:

- UNET: https://huggingface.co/Comfy-Org/Krea-2/resolve/952f49d49653cb42e7d6cf7cbfad74738073ec7d/diffusion_models/krea2_raw_int8_convrot.safetensors
- Text encoder: https://huggingface.co/Comfy-Org/Krea-2/resolve/952f49d49653cb42e7d6cf7cbfad74738073ec7d/text_encoders/qwen3vl_4b_bf16.safetensors
- VAE source (saved as `wan21_vae_fp32.safetensors`): https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/06e001fc51048fb03433a6fb25334de7836704a5/split_files/vae/wan_2.1_vae.safetensors
- Turbo LoRA: https://huggingface.co/Comfy-Org/Krea-2/resolve/952f49d49653cb42e7d6cf7cbfad74738073ec7d/loras/krea2_turbo_lora_rank_64_bf16.safetensors
- Identity Edit LoRA: https://huggingface.co/conradlocke/krea2-identity-edit/resolve/89e9e7a09ee2e5c9331e952063d79b1b8a703280/krea2_identity_edit_v1_2.safetensors
- Filter-bypass LoRA: https://civitai.com/api/download/models/3066812
  Expected SHA-256: `AC6114D7112AE2397EB26B9E6E9623AAD059D346FC285EA050FFB042C7C6748E`

All Hugging Face URLs above are public and are downloaded into the image; no
Hugging Face token or build secret is required. The Civitai filter-bypass LoRA
is downloaded at startup using the runtime `CIVITAI_API_KEY`. The
standard-Python bootstrap applies a download timeout and checksum verification:
it skips downloads only when the existing file matches the published checksum,
and otherwise verifies the downloaded file before atomically replacing it.

## Build locally

```bash
docker build -t krea2-edit .
```

The build validates all public assets and all workflow node registrations on
CPU by default. The resulting image is large; use sufficient RunPod
container/network-volume storage.

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
4. Configure the endpoint runtime environment exactly as:
   `CIVITAI_API_KEY={{ RUNPOD_SECRET_CIVITAI_API_KEY }}`.
   Do not configure a Docker build argument or build secret. Startup downloads
   the Civitai LoRA before starting ComfyUI.
5. Use `api-workflow.json` as the handler's workflow payload. It is the
   complete API-format conversion of the source workflow. Each
   `input.images[].name` must exactly match the corresponding
   `LoadImage.image`; the fixture uses `example.png`, but a client may send a
   different filename when all references are changed consistently.

Do not place RunPod, GitHub, Hugging Face, or Civitai tokens in the repository.
The GitHub repository is public, so cloning it does not require a GitHub token.

## Files

- `Dockerfile` — pinned custom nodes, model/LoRA downloads, strict validation.
- `bootstrap.sh` — runtime checksum verification/download and worker startup.
- `validate_nodes.py` — strict runtime node and model check, with build-only node-check opt-out.
- `api-workflow.json` — ComfyUI API workflow.
- `workflow.json` — original canvas workflow.

## Release gates

Verification of hashes for public model assets and the GPU smoke E2E test are
release gates. If they are not automated in the release pipeline yet, run and
record both checks manually before publishing an image.
