"""Krea2 runtime logging adjustment."""

import logging
import os


def _level() -> int:
    value = os.environ.get("KREA2_COMFY_KITCHEN_LOG_LEVEL", "INFO").upper()
    if value not in logging._nameToLevel:
        return logging.INFO
    return logging._nameToLevel[value]


logging.getLogger("comfy_kitchen.dispatch").setLevel(_level())


if os.environ.get("KREA2_FORCE_MATH_SDPA", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}:
    try:
        import torch
    except ImportError:
        pass
    else:
        torch.backends.cuda.enable_flash_sdp(False)
        torch.backends.cuda.enable_mem_efficient_sdp(False)
        torch.backends.cuda.enable_cudnn_sdp(False)
        torch.backends.cuda.enable_math_sdp(True)
