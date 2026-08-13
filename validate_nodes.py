#!/usr/bin/env python3
"""Build-time validation for the Krea2 serverless image."""

from __future__ import annotations

import os
import sys
import asyncio
import inspect
import hashlib
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
    "unet/lustifyNSFWCheckpoint_v10Krea2.safetensors": 13148974712,
    "clip/qwen3vl_4b_fp8_scaled.safetensors": 5242467968,
    "vae/wan21_vae_fp32.safetensors": 253815318,
    "loras/krea2_turbo_lora_rank_64_bf16.safetensors": 469423778,
    "loras/krea2_identity_edit_v1_2.safetensors": 1828256432,
}
RUNTIME_MANIFEST = {
    # Immutable Hugging Face LFS metadata for the documented equivalent asset.
    "loras/krea2filterbypass.safetensors": (160, "ac6114d7112ae2397eb26b9e6e9623aad059d346fc285ea050ffb042c7c6748e"),
}
WARNINGS: list[str] = []
REPORT_ONLY = os.environ.get("KREA2_REPORT_ONLY") == "1"


def validate_models(root: Path, manifest: Mapping[str, int | tuple[int, str] | None]) -> None:
    required_failures = []
    for relative, expected in manifest.items():
        expected_size = expected[0] if isinstance(expected, tuple) else expected
        path = root / relative
        resolved_root = root.resolve()
        resolved_path = path.resolve()
        try:
            resolved_path.relative_to(resolved_root)
        except ValueError:
            required_failures.append(f"REQUIRED: {path} resolves outside model root")
            continue
        if not path.is_file() or (expected_size is not None and path.stat().st_size != expected_size):
            required_failures.append("REQUIRED: " + str(path))
            continue
        if isinstance(expected, tuple):
            digest = hashlib.sha256()
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != expected[1]:
                required_failures.append("REQUIRED: " + str(path) + " (SHA-256 mismatch)")
    if required_failures:
        raise SystemExit("Missing or invalid required model files:\n" + "\n".join(required_failures))


def validate_discovery(root: Path, manifest: Mapping[str, int | tuple[int, str] | None]) -> None:
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
            raise SystemExit(f"REQUIRED: ComfyUI model discovery mismatch for {relative}: {discovered}")


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
        manifest: dict[str, int | tuple[int, str] | None] = dict(MODEL_MANIFEST)
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
