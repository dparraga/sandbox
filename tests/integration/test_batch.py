"""Installed batch CLI and actual OS lock ownership on disposable folders."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class InstalledBatchTests(unittest.TestCase):
    def run_installed(self, code, directory):
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment["PYTHONNOUSERSITE"] = "1"
        result = subprocess.run([sys.executable, "-I", "-c", code], cwd=directory,
                                env=environment, capture_output=True, text=True,
                                timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((result.stdout, result.stderr), ("", ""))

    def test_lock_refuses_other_process_and_releases_after_owner(self):
        with tempfile.TemporaryDirectory(prefix="flex batch lock \u00e9 ") as directory:
            self.run_installed(r"""
from pathlib import Path
import subprocess, sys
import flex_photo.batch as batch
assert Path(batch.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
output = Path.cwd()
probe = '''from pathlib import Path
from flex_photo.batch import BatchError, _output_lock
try:
    with _output_lock(Path.cwd()):
        pass
except BatchError:
    raise SystemExit(3)
'''
with batch._output_lock(output):
    child = subprocess.run([sys.executable,'-I','-c',probe], capture_output=True,
                           text=True, timeout=10, check=False)
    assert child.returncode == 3, (child.returncode,child.stderr)
    assert not child.stdout and not child.stderr
child = subprocess.run([sys.executable,'-I','-c',probe], capture_output=True,
                       text=True, timeout=10, check=False)
assert child.returncode == 0, child.stderr
assert not child.stdout and not child.stderr
assert (output/'.flex-photo.lock').is_file()
""", directory)

    def test_process_missing_assets_is_incomplete_and_preserves_input(self):
        with tempfile.TemporaryDirectory(prefix="flex process \u00e9 ") as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            original = source / "original.heic"
            original.write_bytes(b"authored source must not be processed without assets")
            before = original.read_bytes()
            environment = os.environ.copy()
            environment.pop("PYTHONPATH", None)
            result = subprocess.run([
                sys.executable, "-I", "-m", "flex_photo", "process", str(source),
                "--destination", str(root / "destination"), "--json-output", str(root / "output"),
                "--tesseract", str(root / "missing-engine"), "--tessdata", str(root / "missing-models"),
                "--tesseract-sha256", "0" * 64], cwd=directory, env=environment,
                capture_output=True, text=True, timeout=30, check=False)
            self.assertEqual(result.returncode, 1, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["status"], "incomplete")
            self.assertTrue(Path(summary["report_path"]).is_file())
            self.assertEqual(result.stderr, "")
            self.assertEqual(original.read_bytes(), before)
            self.assertFalse(list((root / "destination").glob("*.heic")))
            self.assertFalse(list((root / "output").glob("????-??.json")))


if __name__ == "__main__":
    unittest.main()
