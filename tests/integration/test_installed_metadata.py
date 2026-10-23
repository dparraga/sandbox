"""Use the installed reader outside the checkout with public metadata only."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from metadata_fixture import heif_metadata, huge_header_read


class InstalledMetadataTests(unittest.TestCase):
    def test_offline_extraction_errors_and_source_preservation(self):
        with tempfile.TemporaryDirectory(prefix="flex metadata é ") as directory:
            source = Path(directory)
            (source / "capture.heic").write_bytes(heif_metadata(date="invalid date text", subsec="0123456789" * 20))
            (source / "missing.heic").write_bytes(heif_metadata(date=None, offset=None, subsec=None))
            (source / "unsafe.heic").write_bytes(huge_header_read())
            code = """
import hashlib, importlib.metadata, pathlib, socket, sys
from flex_photo.metadata import CaptureMetadata, MetadataError, read_capture_metadata
import flex_photo.metadata as module
assert pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve())
assert importlib.metadata.version('ExifRead') == '3.5.1'
def network_forbidden(*args, **kwargs):
    raise AssertionError('network call')
socket.socket = socket.create_connection = network_forbidden
before = {path.name: hashlib.sha256(path.read_bytes()).digest() for path in pathlib.Path('.').iterdir()}
assert read_capture_metadata(pathlib.Path('capture.heic')) == CaptureMetadata('invalid date text', '+02:30', '0123456789' * 20)
assert read_capture_metadata(pathlib.Path('missing.heic')) == CaptureMetadata(None, None, None)
for name, expected in [('unsafe.heic', 'metadata limit exceeded'), ('absent.heic', 'file unavailable')]:
    try:
        read_capture_metadata(pathlib.Path(name))
    except MetadataError as error:
        assert str(error) == expected
    else:
        raise AssertionError('missing safe error')
after = {path.name: hashlib.sha256(path.read_bytes()).digest() for path in pathlib.Path('.').iterdir()}
assert after == before
"""
            environment = os.environ.copy()
            environment.pop("PYTHONPATH", None)
            environment["PYTHONNOUSERSITE"] = "1"
            result = subprocess.run([sys.executable, "-c", code], cwd=source, env=environment,
                                    capture_output=True, text=True, timeout=30, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((result.stdout, result.stderr), ("", ""))


if __name__ == "__main__":
    unittest.main()
