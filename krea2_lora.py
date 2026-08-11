"""Ephemeral, allowlisted LoRA downloads for the Krea2 worker."""
import os
import socket
import urllib.parse
import urllib.request
import uuid

ALLOWED_HOSTS = {"huggingface.co", "hf.co", "civitai.com"}
MAX_BYTES = 2 * 1024 * 1024 * 1024


def _checked_url(url):
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname
    allowed = isinstance(host, str) and any(
        host == base or host.endswith("." + base) for base in ALLOWED_HOSTS
    )
    if (
        parsed.scheme != "https"
        or not allowed
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
    ):
        raise ValueError("LoRA URL must be HTTPS on an allowlisted host")
    return parsed


class _AllowlistedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _checked_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_loras(downloads, token=None, directory="/runpod-volume/models/loras", opener=None):
    if not isinstance(downloads, list) or not 1 <= len(downloads) <= 7:
        raise ValueError("lora_downloads must contain 1 to 7 downloads")
    os.makedirs(directory, exist_ok=True)
    opener = opener or urllib.request.build_opener(_AllowlistedRedirect())
    created = []
    try:
        for item in downloads:
            if not isinstance(item, dict):
                raise ValueError("each LoRA download must be an object")
            url = item.get("url")
            strength = item.get("strength")
            _checked_url(url) if isinstance(url, str) else (_ for _ in ()).throw(ValueError("LoRA URL is required"))
            if not isinstance(strength, (int, float)) or isinstance(strength, bool) or not 0 <= strength <= 2:
                raise ValueError("LoRA strength must be between 0 and 2")
            name = "krea2-job-" + uuid.uuid4().hex + ".safetensors"
            final = os.path.join(directory, name)
            part = final + ".part"
            headers = {}
            if urllib.parse.urlparse(url).hostname in {"civitai.com", "www.civitai.com"} and token:
                headers["Authorization"] = "Bearer " + token
            request = urllib.request.Request(url, headers=headers)
            total = 0
            with opener.open(request, timeout=120) as response, open(part, "wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise ValueError("LoRA download exceeds 2 GiB limit")
                    output.write(chunk)
            os.replace(part, final)
            created.append(final)
            yield name, strength
    except Exception:
        for path in created:
            try: os.unlink(path)
            except OSError: pass
        raise
    finally:
        # Remove an interrupted partial file as well.
        for path in locals().get("part", None),:
            if path:
                try: os.unlink(path)
                except OSError: pass


def inject_loras(workflow, loras):
    node = workflow.get("297") if isinstance(workflow, dict) else None
    if not isinstance(node, dict) or node.get("class_type") != "Power Lora Loader (rgthree)":
        raise ValueError("workflow node 297 must be Power Lora Loader (rgthree)")
    inputs = node.setdefault("inputs", {})
    slots = [f"lora_{i}" for i in range(4, 11)]
    free = [slot for slot in slots if not inputs.get(slot)]
    if len(loras) > len(free):
        raise ValueError("node 297 has fewer than 7 free LoRA slots")
    for slot, (name, strength) in zip(free, loras):
        inputs[slot] = {"on": True, "lora": name, "strength": strength, "strengthTwo": None}
    return workflow
