#!/usr/bin/env python3
"""Build-time validation for the Krea2 serverless image."""

from __future__ import annotations

import os
import sys


sys.path.insert(0, "/comfyui")

import nodes  # type: ignore[import-not-found]  # noqa: E402


REQUIRED_NODES = {
    "LayerUtility: ImageScaleByAspectRatio",
    "ClownsharKSampler_Beta",
    "Power Lora Loader (rgthree)",
    "Krea2EditModelPatch",
    "Krea2EditGroundedEncode",
}

REQUIRED_FILES = {
    "/comfyui/models/diffusion_models/krea2_raw_int8_convrot.safetensors",
    "/comfyui/models/text_encoders/qwen3vl_4b_bf16.safetensors",
    "/comfyui/models/vae/wan21_vae_fp32.safetensors",
    "/comfyui/models/loras/krea2_turbo_lora_rank_64_bf16.safetensors",
    "/comfyui/models/loras/krea2filterbypass.safetensors",
    "/comfyui/models/loras/krea2_identity_edit_v1_2.safetensors",
}


def main() -> None:
    try:
        nodes.init_extra_nodes(init_custom_nodes=True)
    except TypeError:
        # Compatibility with older ComfyUI base images.
        nodes.init_extra_nodes()

    registered = set(nodes.NODE_CLASS_MAPPINGS)
    missing_nodes = sorted(REQUIRED_NODES - registered)
    if missing_nodes:
        raise SystemExit(
            "Missing required ComfyUI nodes after startup: "
            + ", ".join(missing_nodes)
        )

    missing_files = sorted(path for path in REQUIRED_FILES if not os.path.isfile(path))
    if missing_files:
        raise SystemExit("Missing required model files:\n" + "\n".join(missing_files))

    print("Krea2 validation OK")
    print("Nodes:")
    for node_name in sorted(REQUIRED_NODES):
        print(f"  - {node_name}")
    print("Models and LoRAs: OK")


if __name__ == "__main__":
    main()
