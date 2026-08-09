#!/usr/bin/env python3
"""Build-time validation for the Krea2 serverless image."""

from __future__ import annotations

import os
import sys


sys.path.insert(0, "/comfyui")

REQUIRED_NODES = {
    "LoadImage",
    "SaveImage",
    "VAEDecode",
    "VAEEncode",
    "UNETLoader",
    "CLIPLoader",
    "VAELoader",
    "LayerUtility: ImageScaleByAspectRatio",
    "ClownsharKSampler_Beta",
    "Power Lora Loader (rgthree)",
    "Krea2EditModelPatch",
    "Krea2EditGroundedEncode",
    "easy int",
    "easy float",
    "PrimitiveBoolean",
}

BUILD_REQUIRED_FILES = {
    "/comfyui/models/diffusion_models/krea2_raw_int8_convrot.safetensors": 13492686496,
    "/comfyui/models/text_encoders/qwen3vl_4b_bf16.safetensors": 8875719384,
    "/comfyui/models/vae/wan21_vae_fp32.safetensors": 253815318,
    "/comfyui/models/loras/krea2_turbo_lora_rank_64_bf16.safetensors": 469423778,
    "/comfyui/models/loras/krea2_identity_edit_v1_2.safetensors": 1828256432,
}
RUNTIME_REQUIRED_FILES = {
    "/comfyui/models/loras/krea2filterbypass.safetensors": None,
}


def main() -> None:
    skip_node_check = os.environ.get("KREA2_SKIP_NODE_CHECK") == "1"
    if skip_node_check:
        print(
            "WARNING: skipping ComfyUI node registration during build; "
            "node validation is deferred to runtime"
        )
    else:
        import nodes  # type: ignore[import-not-found]

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

    required_files: dict[str, int | None] = dict(BUILD_REQUIRED_FILES)
    if os.environ.get("KREA2_VALIDATE_RUNTIME_ASSETS") == "1":
        required_files.update(RUNTIME_REQUIRED_FILES)
    missing_files = sorted(
        path
        for path, expected_size in required_files.items()
        if not os.path.isfile(path)
        or os.path.getsize(path) == 0
        or (expected_size is not None and os.path.getsize(path) != expected_size)
    )
    if missing_files:
        raise SystemExit("Missing required model files:\n" + "\n".join(missing_files))

    print("Krea2 validation OK")
    if not skip_node_check:
        print("Nodes:")
        for node_name in sorted(REQUIRED_NODES):
            print(f"  - {node_name}")
    print("Models and LoRAs: OK")


if __name__ == "__main__":
    main()
