"""Installed discovery inventory and source preservation using public synthetic fixtures."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import tempfile
import unittest


class InstalledDiscoveryTests(unittest.TestCase):
    def test_console_and_module_inventory_preserve_sources(self):
        console = Path(sysconfig.get_path("scripts")) / ("flex-photo.exe" if os.name == "nt" else "flex-photo")
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment["PYTHONNOUSERSITE"] = "1"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "photos"
            source.mkdir()
            names = ["z.HEIC", "day 1/caf\u00e9.heic", ".hidden.heic", "not.heif", "not.heic.bak"]
            if os.name != "nt":
                names.append("line\nbreak.heic")
            for name in names:
                path = source / name
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(b"synthetic, not a photo")
            def snapshot():
                return {path.relative_to(source).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in source.rglob("*") if path.is_file()}
            before = snapshot()
            expected = sorted(name for name in names if name.lower().endswith(".heic"))
            for command in [[str(console)], [sys.executable, "-m", "flex_photo"]]:
                with self.subTest(command=command):
                    result = subprocess.run(command + ["discover", str(source)], cwd=root,
                                            env=environment, capture_output=True, text=True, timeout=15, check=False)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stderr, "")
                    self.assertEqual(result.stdout, json.dumps(expected, ensure_ascii=True) + "\n")
                    self.assertEqual(snapshot(), before)
                    self.assertEqual(sorted(path.name for path in root.iterdir()), ["photos"])
                    for args, status in [(["discover", str(source / "missing")], 1), (["discover"], 2)]:
                        failure = subprocess.run(command + args, cwd=root, env=environment,
                                                 capture_output=True, text=True, timeout=15, check=False)
                        self.assertEqual(failure.returncode, status)
                        self.assertEqual(failure.stdout, "")
                        self.assertNotIn(str(source), failure.stderr)
                        self.assertNotIn("Traceback", failure.stderr)
                        self.assertEqual(len(failure.stderr.splitlines()) if status == 1 else 1, 1)
            empty = source / "empty"
            empty.mkdir()
            result = subprocess.run([sys.executable, "-m", "flex_photo", "discover", str(empty)], cwd=root,
                                    env=environment, capture_output=True, text=True, timeout=15, check=False)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "[]\n", ""))


if __name__ == "__main__":
    unittest.main()
