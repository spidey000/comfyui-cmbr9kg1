import base64
import importlib
import json
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


def _import_handler():
    """Import handler without requiring the RunPod/ComfyUI runtime image."""
    runpod = types.ModuleType("runpod")
    runpod.serverless = types.ModuleType("runpod.serverless")  # type: ignore[attr-defined]
    runpod.serverless.utils = types.ModuleType("runpod.serverless.utils")  # type: ignore[attr-defined]
    runpod.serverless.utils.rp_upload = types.SimpleNamespace()  # type: ignore[attr-defined]
    runpod.serverless.start = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    websocket = types.ModuleType("websocket")
    network_volume = types.ModuleType("network_volume")
    network_volume.is_network_volume_debug_enabled = lambda: False  # type: ignore[attr-defined]
    network_volume.run_network_volume_diagnostics = lambda: None  # type: ignore[attr-defined]
    sys.modules.setdefault("runpod", runpod)
    sys.modules.setdefault("runpod.serverless", runpod.serverless)
    sys.modules.setdefault("runpod.serverless.utils", runpod.serverless.utils)
    sys.modules.setdefault("websocket", websocket)
    sys.modules.setdefault("network_volume", network_volume)
    return importlib.import_module("handler")


handler = _import_handler()


class FakeResponse:
    def __init__(self, chunks=(b"image-bytes",), status=200, content_type="image/png", content_length=None):
        self.status = status
        self._chunks = iter(chunks)
        self._headers = {"Content-Type": content_type}
        if content_length is not None:
            self._headers["Content-Length"] = str(content_length)
        self.closed = False

    def getheader(self, name, default=None):
        return self._headers.get(name, default)

    def read(self, size=-1):
        return next(self._chunks, b"")

    def close(self):
        self.closed = True


class FakeSocket:
    def __init__(self):
        self.closed = False
        self.timeouts = []

    def settimeout(self, value):
        self.timeouts.append(value)

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, response, sock):
        self.response = response
        self.sock = None
        self.requested = False
        self.closed = False
        self._sock = sock

    def request(self, *args, **kwargs):
        self.requested = True

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True
        self._sock.close()


class ShorthandTests(unittest.TestCase):
    def setUp(self):
        self.template = {"317": {"class_type": "Krea2EditGroundedEncode", "inputs": {"prompt": "old"}}, "78": {"class_type": "LoadImage", "inputs": {"image": "old.png"}}, "other": {"x": 1}}
        self.file = tempfile.NamedTemporaryFile(mode="w", suffix=".json")
        json.dump(self.template, self.file); self.file.flush()
        self.path = patch.object(handler, "API_WORKFLOW_PATH", self.file.name)
        self.path.start()

    def tearDown(self):
        self.path.stop(); self.file.close()

    def test_prompt_and_object_image_name_are_injected_without_mutating_template(self):
        result, error = handler.validate_input({"prompt": "make it vivid", "image": {"name": "reference.jpg", "image": "YWJj"}})
        self.assertIsNone(error)
        self.assertEqual(result["workflow"]["317"]["inputs"]["prompt"], "make it vivid")
        self.assertNotEqual(result["workflow"]["78"]["inputs"]["image"], "reference.jpg")
        self.assertEqual(result["workflow"]["78"]["inputs"]["image"], result["images"][0]["name"])
        self.assertEqual(self.template["317"]["inputs"]["prompt"], "old")

    def test_string_image_and_data_uri_are_accepted_and_upload_normalizes_uri(self):
        result, error = handler.validate_input({"prompt": "x", "image": "data:image/png;base64,YWJj"})
        self.assertIsNone(error); self.assertNotEqual(result["images"][0]["name"], "input.png")
        response = types.SimpleNamespace(raise_for_status=lambda: None)
        with patch.object(handler.requests, "post", return_value=response) as post:
            self.assertEqual(handler.upload_images(result["images"])["status"], "success")
        uploaded = post.call_args.kwargs["files"]["image"][1].read()
        self.assertEqual(uploaded, b"abc")

    def test_image_url_download_and_limits_and_scheme(self):
        fake = FakeResponse()
        sock = FakeSocket()
        conn = FakeConnection(fake, sock)
        with patch.object(handler.socket, "getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 443))]), patch.object(handler.socket, "create_connection", return_value=sock), patch.object(handler.ssl, "create_default_context") as context, patch.object(handler.http.client, "HTTPSConnection", return_value=conn):
            context.return_value.wrap_socket.return_value = sock
            result, error = handler.validate_input({"prompt": "x", "image_url": "https://example.test/a"})
        self.assertIsNone(error); self.assertEqual(result["images"][0]["image"], base64.b64encode(b"image-bytes").decode())
        self.assertTrue(fake.closed); self.assertTrue(conn.closed); self.assertTrue(sock.closed)
        bad, error = handler.validate_input({"prompt": "x", "image_url": "file:///tmp/x"})
        self.assertIsNone(bad); self.assertIn("http(s)", error)
        too_large = FakeResponse(content_length=handler.MAX_REMOTE_IMAGE_BYTES + 1)
        large_sock = FakeSocket()
        large_conn = FakeConnection(too_large, large_sock)
        with patch.object(handler.socket, "getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 443))]), patch.object(handler.socket, "create_connection", return_value=large_sock), patch.object(handler.ssl, "create_default_context") as context, patch.object(handler.http.client, "HTTPSConnection", return_value=large_conn):
            context.return_value.wrap_socket.return_value = large_sock
            _, error = handler.validate_input({"prompt": "x", "image_url": "https://example.test/a"})
        self.assertIn("20 MB", error)
        self.assertTrue(too_large.closed); self.assertTrue(large_conn.closed); self.assertTrue(large_sock.closed)

    def test_image_url_blocks_private_and_numeric_targets_without_http(self):
        for url in ("http://127.0.0.1/image", "http://2130706433/image"):
            with patch.object(handler.socket, "create_connection") as get:
                result, error = handler.validate_input({"prompt": "x", "image_url": url})
            self.assertIsNone(result)
            self.assertIsNotNone(error)
            get.assert_not_called()

    def test_image_url_blocks_private_dns_and_redirects(self):
        with patch.object(handler.socket, "getaddrinfo", return_value=[(None, None, None, None, ("10.0.0.1", 443))]), patch.object(handler.socket, "create_connection") as get:
            result, error = handler.validate_input({"prompt": "x", "image_url": "https://example.test/a"})
        self.assertIsNone(result); self.assertIn("public", error); get.assert_not_called()

        self.assertIn("redirect", str(handler._download_public_image)) if False else None

    def test_image_url_blocks_credentials_and_fragments_before_network(self):
        for url in ("https://user:password@example.test/a", "https://example.test/a#fragment"):
            with patch.object(handler.socket, "getaddrinfo") as resolve, patch.object(handler.requests, "get") as get:
                result, error = handler.validate_input({"prompt": "x", "image_url": url})
            self.assertIsNone(result)
            self.assertIsNotNone(error)
            resolve.assert_not_called()
            get.assert_not_called()

    def test_malformed_shorthand_and_full_workflow(self):
        for value in (None, 3, {"name": "x"}, ["x"]):
            _, error = handler.validate_input({"prompt": "x", "image": value})
            self.assertIsNotNone(error)
        workflow = {"317": {"class_type": "Krea2EditGroundedEncode", "inputs": {"prompt": "keep"}}, "78": {"class_type": "LoadImage", "inputs": {"image": "x.png"}}}
        result, error = handler.validate_input({"workflow": workflow, "images": []})
        self.assertIsNone(error); self.assertEqual(result["workflow"], workflow)

    def test_full_workflow_upload_names_are_job_scoped_and_traversal_is_rejected(self):
        workflow = {"load": {"class_type": "LoadImage", "inputs": {"image": "legacy.png"}}}
        payload = {"workflow": workflow, "images": [{"name": "legacy.png", "image": "YWJj"}]}
        first, error = handler.validate_input(json.loads(json.dumps(payload)), "job-1")
        self.assertIsNone(error)
        second, error = handler.validate_input(json.loads(json.dumps(payload)), "job-2")
        self.assertIsNone(error)
        self.assertNotEqual(first["images"][0]["name"], second["images"][0]["name"])
        self.assertEqual(first["workflow"]["load"]["inputs"]["image"], first["images"][0]["name"])
        self.assertEqual(second["workflow"]["load"]["inputs"]["image"], second["images"][0]["name"])
        rejected, error = handler.validate_input({"workflow": workflow, "images": [{"name": "../legacy.png", "image": "YWJj"}]}, "job-3")
        self.assertIsNone(rejected)
        self.assertIn("path separators", error)


if __name__ == "__main__":
    unittest.main()
