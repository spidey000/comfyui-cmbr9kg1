"""Krea2 runtime logging adjustment."""

import logging
import os


def _level() -> int:
    value = os.environ.get("KREA2_COMFY_KITCHEN_LOG_LEVEL", "INFO").upper()
    if value not in logging._nameToLevel:
        return logging.INFO
    return logging._nameToLevel[value]


logging.getLogger("comfy_kitchen.dispatch").setLevel(_level())
