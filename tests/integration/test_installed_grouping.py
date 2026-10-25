"""Compose installed metadata conversion and grouping using synthetic captures."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from metadata_fixture import heif_metadata


class InstalledGroupingTests(unittest.TestCase):
    def test_reader_converter_grouping_outside_checkout_preserves_sources(self):
        with tempfile.TemporaryDirectory(prefix="flex grouping ") as directory:
            source = Path(directory)
            observations = [
                ("later.heic", "2030:01:01 00:03:00", "+00:00", "000001"),
                ("anchor.heic", "2029:12:31 23:00:00", "-01:00", None),
                ("boundary.heic", "2030:01:01 01:03:00", "+01:00", "0"),
                ("equal.heic", "2030:01:01 02:00:00", "+02:00", None),
            ]
            for name, date, offset, subsec in observations:
                (source / name).write_bytes(heif_metadata(date=date, offset=offset, subsec=subsec))
            code = """
from datetime import timedelta
import hashlib, pathlib, sys
import flex_photo.grouping as module
from flex_photo.capture_time import parse_capture_time
from flex_photo.grouping import group_capture_times
from flex_photo.metadata import read_capture_metadata
assert pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve())
before = {p.name: hashlib.sha256(p.read_bytes()).digest() for p in pathlib.Path('.').iterdir()}
names = ['later.heic', 'anchor.heic', 'boundary.heic', 'equal.heic']
metadata = [read_capture_metadata(pathlib.Path(name)) for name in names]
captures = [parse_capture_time(raw) for raw in metadata]
original = captures.copy()
assert group_capture_times(captures) == ((1, 3, 2), (0,))
assert group_capture_times(captures, timedelta(0)) == ((1, 3), (2,), (0,))
assert captures == original
assert [raw.offset_time_original for raw in metadata] == ['+00:00', '-01:00', '+01:00', '+02:00']
assert [raw.subsec_time_original for raw in metadata] == ['000001', None, '0', None]
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
