"""Installed process restart and SIGINT mechanics with authored extraction data."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


_HARNESS = r"""
import json, os, signal, sys
from pathlib import Path
import flex_photo.batch as batch
from flex_photo.interpretation import InterpretationAssets, FieldObservation, PhotoInterpretation
from flex_photo.metadata import CaptureMetadata
assert Path(batch.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
root = Path.cwd()
mode = sys.argv[1]
batch._validate_assets = lambda assets: None
def interpret(path, assets):
    with (root / 'ocr-calls.txt').open('a', encoding='ascii') as calls:
        calls.write(path.name + '\n')
        calls.flush()
        os.fsync(calls.fileno())
    if mode == 'crash' and path.name == 'b.heic':
        os._exit(71)
    if mode == 'pause' and path.name == 'a.heic':
        signal.raise_signal(signal.SIGINT)
    return PhotoInterpretation(path, 'trip_summary', (
        FieldObservation('trip_distance', 'clear', value='0.0', unit='mi'),
        FieldObservation('trip_duration', 'clear', value='00:12'),
        FieldObservation('trip_average_mpg', 'absent'),
        FieldObservation('odometer', 'absent')),
        CaptureMetadata('2031:06:12 12:00:00', '+00:00', None))
batch.interpret_photo = interpret
result = batch.process_batch(root / 'source', root / 'destination', root / 'output',
    assets=InterpretationAssets(Path('authored-engine'), Path('authored-model'), 'a' * 64),
    resume=mode == 'resume')
print(json.dumps(result.summary()))
"""


class InstalledResumeTests(unittest.TestCase):
    def run_child(self, directory, mode):
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment["PYTHONNOUSERSITE"] = "1"
        return subprocess.run([sys.executable, "-I", "-c", _HARNESS, mode],
                              cwd=directory, env=environment, text=True,
                              capture_output=True, timeout=30, check=False)

    def make_inputs(self, root):
        (root / "source").mkdir()
        originals = {name: ("authored bytes " + name).encode() for name in ("a.heic", "b.heic")}
        for name, data in originals.items():
            (root / "source" / name).write_bytes(data)
        return originals

    def assert_output(self, root, originals):
        self.assertEqual(list((root / "source").iterdir()), [])
        for name, original in originals.items():
            self.assertEqual((root / "destination" / name).read_bytes(), original)
        monthly = json.loads((root / "output" / "2031-06.json").read_bytes())
        self.assertEqual(len(monthly["trips"]), 1)
        self.assertEqual(monthly["trips"][0]["fields"]["trip_distance"], {"value": "0.0", "unit": "mi"})
        self.assertFalse((root / "output" / ".flex-photo-checkpoint").exists())

    def test_new_process_recovers_after_unexpected_exit_without_repeating_completed_ocr(self):
        with tempfile.TemporaryDirectory(prefix="flex restart \u00e9 ") as directory:
            root = Path(directory)
            originals = self.make_inputs(root)
            crashed = self.run_child(directory, "crash")
            self.assertEqual(crashed.returncode, 71, crashed.stderr)
            self.assertTrue((root / "output" / ".flex-photo-checkpoint" / "results.jsonl").exists())
            resumed = self.run_child(directory, "resume")
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertEqual(json.loads(resumed.stdout)["status"], "complete")
            self.assertEqual((root / "ocr-calls.txt").read_text().splitlines(), ["a.heic", "b.heic", "b.heic"])
            self.assert_output(root, originals)

    def test_sigint_finishes_current_unit_and_new_process_resumes(self):
        with tempfile.TemporaryDirectory(prefix="flex signal \u00e9 ") as directory:
            root = Path(directory)
            originals = self.make_inputs(root)
            paused = self.run_child(directory, "pause")
            self.assertEqual(paused.returncode, 0, paused.stderr)
            summary = json.loads(paused.stdout)
            self.assertEqual(summary["status"], "paused")
            report = json.loads(Path(summary["report_path"]).read_bytes())
            self.assertEqual(report["progress"]["processed_count"], 1)
            self.assertEqual(len(list((root / "source").iterdir())), 2)
            resumed = self.run_child(directory, "resume")
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertEqual(json.loads(resumed.stdout)["status"], "complete")
            self.assertEqual((root / "ocr-calls.txt").read_text().splitlines(), ["a.heic", "b.heic"])
            self.assert_output(root, originals)


if __name__ == "__main__":
    unittest.main()
