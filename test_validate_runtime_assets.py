import hashlib
from pathlib import Path

import unittest

from validate_nodes import RUNTIME_MANIFEST, validate_models


class RuntimeAssetTests(unittest.TestCase):
  def test_runtime_asset_validates_size_and_hash(self):
    from tempfile import TemporaryDirectory
    rel, expected = next(iter(RUNTIME_MANIFEST.items()))
    with TemporaryDirectory() as directory:
      target = Path(directory) / rel
      target.parent.mkdir()
      target.write_bytes(b"x" * expected[0])
      digest = hashlib.sha256(target.read_bytes()).hexdigest()
      with self.assertRaises(SystemExit):
        validate_models(Path(directory), {rel: (expected[0], digest + "0")})


  def test_runtime_asset_rejects_invalid_hash(self):
    from tempfile import TemporaryDirectory
    rel, expected = next(iter(RUNTIME_MANIFEST.items()))
    with TemporaryDirectory() as directory:
      target = Path(directory) / rel
      target.parent.mkdir()
      target.write_bytes(b"x" * expected[0])
      with self.assertRaisesRegex(SystemExit, "SHA-256 mismatch"):
        validate_models(Path(directory), RUNTIME_MANIFEST)
