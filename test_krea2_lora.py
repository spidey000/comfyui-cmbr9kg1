import io
import json
import tempfile
import unittest
from unittest.mock import patch

from krea2_lora import _checked_url, download_loras, inject_loras


class Response(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *args): pass


class Opener:
    def open(self, request, timeout):
        self.request = request
        return Response(b"abc")


class LoraTests(unittest.TestCase):
    def test_url_allowlist(self):
        _checked_url("https://hf.co/a")
        _checked_url("https://cdn.huggingface.co/a")
        _checked_url("https://models.storage.civitai.com/a")
        with self.assertRaises(ValueError): _checked_url("http://hf.co/a")
        with self.assertRaises(ValueError): _checked_url("https://example.com/a")
        with self.assertRaises(ValueError): _checked_url("https://evilhuggingface.co/a")
        with self.assertRaises(ValueError): _checked_url("https://hf.co.evil.com/a")
        with self.assertRaises(ValueError): _checked_url("https://user@hf.co/a")
        with self.assertRaises(ValueError): _checked_url("https://hf.co:443/a")

    def test_download_is_unique_atomic_and_auth_is_not_persisted(self):
        opener = Opener()
        with tempfile.TemporaryDirectory() as directory:
            result = list(download_loras([{"url": "https://civitai.com/api/download/1", "strength": 1}], "secret", directory, opener))
            name, strength = result[0]
            self.assertEqual(strength, 1)
            self.assertTrue((__import__("pathlib").Path(directory) / name).read_bytes() == b"abc")
            self.assertEqual(opener.request.get_header("Authorization"), "Bearer secret")
            self.assertNotIn("secret", json.dumps(result))

    def test_injects_only_free_dynamic_slots(self):
        workflow = {"297": {"class_type": "Power Lora Loader (rgthree)", "inputs": {"lora_4": {"on": True}}}}
        inject_loras(workflow, [("x.safetensors", 0.5)])
        self.assertEqual(workflow["297"]["inputs"]["lora_5"]["strengthTwo"], None)
        with self.assertRaises(ValueError): inject_loras({"297": {}}, [])


if __name__ == "__main__": unittest.main()
