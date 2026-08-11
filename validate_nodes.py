#!/usr/bin/env python3
"""Build-time validation for the Krea2 serverless image."""

from __future__ import annotations

import os
import sys
import asyncio
import inspect
from pathlib import Path
from collections.abc import Mapping


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

MODEL_MANIFEST = {
    "unet/krea2_raw_int8_convrot.safetensors": 13492686496,
    "clip/qwen3vl_4b_bf16.safetensors": 8875719384,
    "vae/wan21_vae_fp32.safetensors": 253815318,
    "loras/krea2_turbo_lora_rank_64_bf16.safetensors": 469423778,
    "loras/krea2_identity_edit_v1_2.safetensors": 1828256432,
}
RUNTIME_MANIFEST = {"loras/krea2filterbypass.safetensors": None}
WARNINGS: list[str] = []
REPORT_ONLY = os.environ.get("KREA2_REPORT_ONLY") == "1"


def validate_models(root: Path, manifest: Mapping[str, int | None]) -> None:
    required_failures = []
    optional_failures = []
    for relative, expected_size in manifest.items():
        path = root / relative
        resolved_root = root.resolve()
        resolved_path = path.resolve()
        try:
            resolved_path.relative_to(resolved_root)
        except ValueError:
            label = "OPTIONAL" if relative in RUNTIME_MANIFEST else "REQUIRED"
            (optional_failures if label == "OPTIONAL" else required_failures).append(
                f"{label}: {path} resolves outside model root"
            )
            continue
        if not path.is_file() or (expected_size is not None and path.stat().st_size != expected_size):
            label = "OPTIONAL" if relative in RUNTIME_MANIFEST else "REQUIRED"
            (optional_failures if label == "OPTIONAL" else required_failures).append(
                label + ": " + str(path)
            )
            continue
    if optional_failures:
        WARNINGS.append("Missing or invalid optional model files:\n" + "\n".join(optional_failures))
    if required_failures:
        raise SystemExit("Missing or invalid required model files:\n" + "\n".join(required_failures))


def validate_discovery(root: Path, manifest: Mapping[str, int | None]) -> None:
    import folder_paths  # type: ignore[import-not-found]
    from utils.extra_config import load_extra_path_config  # type: ignore[import-not-found]

    extra_model_paths = Path("/comfyui/extra_model_paths.yaml")
    if extra_model_paths.exists():
        load_extra_path_config(str(extra_model_paths))

    categories = {"unet": "diffusion_models", "clip": "text_encoders", "vae": "vae", "loras": "loras"}
    for relative in manifest:
        category, filename = relative.split("/", 1)
        discovered = folder_paths.get_full_path(categories[category], filename)
        expected = (root / relative).resolve()
        if discovered is None or Path(discovered).resolve() != expected:
            label = "OPTIONAL" if relative in RUNTIME_MANIFEST else "REQUIRED"
            message = f"{label}: ComfyUI model discovery mismatch for {relative}: {discovered}"
            if label == "OPTIONAL":
                WARNINGS.append(message)
            else:
                raise SystemExit(message)


def main() -> None:
    skip_node_check = os.environ.get("KREA2_SKIP_NODE_CHECK") == "1"
    if skip_node_check:
        print(
            "WARNING: skipping ComfyUI node registration during build; "
            "node validation is deferred to runtime"
        )
    else:
        try:
            # Match ComfyUI's main startup: custom nodes expect a live
            # PromptServer.instance (in particular its route registry) while
            # they are imported.
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            from server import PromptServer  # type: ignore[import-not-found]

            PromptServer(loop)
            import nodes  # type: ignore[import-not-found]

            try:
                initialization = nodes.init_extra_nodes(init_custom_nodes=True)
            except TypeError:
                # Compatibility with older ComfyUI base images.
                initialization = nodes.init_extra_nodes()
            if inspect.isawaitable(initialization):
                async def complete_initialization() -> None:
                    await initialization

                loop.run_until_complete(complete_initialization())

            registered = set(nodes.NODE_CLASS_MAPPINGS)
            missing_nodes = sorted(REQUIRED_NODES - registered)
            if missing_nodes:
                raise RuntimeError(
                    "Missing required ComfyUI nodes after startup: "
                    + ", ".join(missing_nodes)
                )
            loop.close()
            asyncio.set_event_loop(None)
        except Exception as exc:
            raise RuntimeError(f"ComfyUI node validation failed: {exc}") from exc

    if os.environ.get("KREA2_VALIDATE_MODEL_ASSETS", "1") != "0":
        manifest: dict[str, int | None] = dict(MODEL_MANIFEST)
        if os.environ.get("KREA2_VALIDATE_RUNTIME_ASSETS") == "1":
            manifest.update(RUNTIME_MANIFEST)
        try:
            validate_models(Path(os.environ.get("KREA2_MODEL_ROOT", "/comfyui/models")), manifest)
            if not skip_node_check:
                validate_discovery(Path(os.environ.get("KREA2_MODEL_ROOT", "/comfyui/models")), manifest)
        except Exception:
            # Required assets and discovery are startup prerequisites.  Do not
            # let report-only mode turn a broken required model into success.
            raise

    if WARNINGS:
        for warning in WARNINGS: print(f"WARNING: {warning}")
        print("Krea2 validation completed with warnings (continuing)")
    else: print("Krea2 validation OK")
    if not skip_node_check:
        print("Nodes:")
        for node_name in sorted(REQUIRED_NODES):
            print(f"  - {node_name}")
    print("Models and LoRAs: OK")


if __name__ == "__main__":
    main()
