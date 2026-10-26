"""Compose installed candidate selection with synthetic metadata and grouping."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from metadata_fixture import heif_metadata


class InstalledSelectionTests(unittest.TestCase):
    def test_group_local_candidates_map_to_retained_source_values(self):
        with tempfile.TemporaryDirectory(prefix="flex selection ") as directory:
            source = Path(directory)
            observations = [
                ("next.heic", "2030:01:01 00:03:00", "+00:00", "000001"),
                ("anchor.heic", "2029:12:31 23:00:00", "-01:00", None),
                ("boundary.heic", "2030:01:01 01:03:00", "+01:00", "0"),
                ("equal.heic", "2030:01:01 02:00:00", "+02:00", None),
                ("boundary-tie.heic", "2029:12:31 23:03:00", "-01:00", None),
            ]
            for name, date, offset, subsec in observations:
                (source / name).write_bytes(heif_metadata(date=date, offset=offset, subsec=subsec))
            code = """
import hashlib, pathlib, sys
import flex_photo.selection as module
from flex_photo.capture_time import parse_capture_time
from flex_photo.grouping import group_capture_times
from flex_photo.metadata import read_capture_metadata
from flex_photo.selection import latest_clear_indices
assert pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve())
before = {p.name: hashlib.sha256(p.read_bytes()).digest() for p in pathlib.Path('.').iterdir()}
names = ['next.heic', 'anchor.heic', 'boundary.heic', 'equal.heic', 'boundary-tie.heic']
metadata = [read_capture_metadata(pathlib.Path(name)) for name in names]
captures = [parse_capture_time(raw) for raw in metadata]
original = captures.copy()
groups = group_capture_times(captures)
assert groups == ((1, 3, 2, 4), (0,))
group = groups[0]
local_times = [captures[index] for index in group]
# Synthetic caller-owned values and clarity flags; no extraction/schema policy.
zero_values = [None, 0, None, None, None]
zero_flags = [False, True, False, False, False]
range_values = [999, None, 50, None, None]
range_flags = [True, False, True, False, False]
tie_values = [None, None, 'first conflict', None, 'second conflict']
tie_flags = [False, False, True, False, True]
def source_candidates(flags):
    local_candidates = latest_clear_indices(local_times, [flags[index] for index in group])
    return tuple(group[index] for index in local_candidates)
assert source_candidates(zero_flags) == (1,)
assert tuple(zero_values[index] for index in source_candidates(zero_flags)) == (0,)
assert source_candidates(range_flags) == (2,)
assert tuple(range_values[index] for index in source_candidates(range_flags)) == (50,)
assert source_candidates(tie_flags) == (2, 4)
assert tuple(tie_values[index] for index in source_candidates(tie_flags)) == ('first conflict', 'second conflict')
# The absence result remains empty for a future value layer; no JSON/winner is emitted.
assert source_candidates([False] * len(captures)) == ()
assert latest_clear_indices([captures[index] for index in groups[1]], [True]) == (0,)
assert captures == original and all(a is b for a, b in zip(captures, original))
assert [raw.offset_time_original for raw in metadata] == ['+00:00', '-01:00', '+01:00', '+02:00', '-01:00']
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
