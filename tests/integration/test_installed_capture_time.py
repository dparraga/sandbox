"""Compose the installed metadata reader and strict time converter."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from metadata_fixture import heif_metadata


class InstalledCaptureTimeTests(unittest.TestCase):
    def test_reader_composition_outside_checkout_and_source_preservation(self):
        with tempfile.TemporaryDirectory(prefix="flex capture time é ") as directory:
            source = Path(directory)
            for name, arguments in [("valid.heic", {}), ("whole.heic", {"subsec": None}),
                                    ("missing.heic", {"offset": None}),
                                    ("long.heic", {"subsec": "1234567"})]:
                (source / name).write_bytes(heif_metadata(**arguments))
            code = """
from datetime import datetime, timedelta, timezone
import hashlib, pathlib, sys
import flex_photo.capture_time as module
from flex_photo.capture_time import CaptureTimeError, parse_capture_time
from flex_photo.metadata import CaptureMetadata, read_capture_metadata
assert pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve())
before = {p.name: hashlib.sha256(p.read_bytes()).digest() for p in pathlib.Path('.').iterdir()}
raw = read_capture_metadata(pathlib.Path('valid.heic'))
assert raw == CaptureMetadata('2030:02:03 04:05:06', '+02:30', '123456')
result = parse_capture_time(raw)
assert result == datetime(2030, 2, 3, 4, 5, 6, 123456, tzinfo=timezone(timedelta(minutes=150)))
assert result.hour == 4 and result.utcoffset() == timedelta(minutes=150)
assert raw.subsec_time_original == '123456'
whole = read_capture_metadata(pathlib.Path('whole.heic'))
assert whole.subsec_time_original is None and parse_capture_time(whole).microsecond == 0
for name, field, reason in [('missing.heic', 'offset_time_original', 'missing'),
                            ('long.heic', 'subsec_time_original', 'unsupported precision')]:
    try:
        parse_capture_time(read_capture_metadata(pathlib.Path(name)))
    except CaptureTimeError as error:
        assert (error.field, error.reason) == (field, reason)
        assert str(error) == field + ': ' + reason
    else:
        raise AssertionError('expected component error')
assert {p.name: hashlib.sha256(p.read_bytes()).digest() for p in pathlib.Path('.').iterdir()} == before
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
