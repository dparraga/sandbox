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

    def test_installed_fallback_sparse_output_and_legacy_rewrite_keep_original_bytes(self):
        with tempfile.TemporaryDirectory(prefix="flex installed sparse \u00e9 ") as directory:
            self.run_installed(r"""
import json, hashlib
from pathlib import Path
import flex_photo.batch as batch
from flex_photo.capture_fallback import CAPTURE_POLICY
from flex_photo.interpretation import FieldObservation, InterpretationAssets, PhotoInterpretation
source, destination, output = [Path.cwd()/name for name in ('source','destination','output')]
source.mkdir()
photo = source/'20310612_120000123_iOS.heic'
photo.write_bytes(b'authored input bytes')
batch._validate_assets = lambda assets: None
batch.capture_inputs = lambda path: {'creation_time_ns':None,'filename':path.name,'policy':CAPTURE_POLICY}
batch.capture_inputs_match = lambda path, expected: batch.capture_inputs(path) == expected
batch.interpret_photo = lambda path, assets: PhotoInterpretation(path, 'trip_summary', (
    FieldObservation('trip_distance','clear',value='0.0',unit='mi'),
    FieldObservation('trip_duration','clear',value='00:00')))
assets = InterpretationAssets(Path('engine'),Path('model'),'a'*64)
result = batch.process_batch(source,destination,output,assets=assets)
assert result.complete
monthly_path = output/'2031-06.json'
monthly = json.loads(monthly_path.read_bytes())
assert monthly['schema_version'] == 2
entry = monthly['trips'][0]
assert entry['first_capture_times'] == ['2031-06-12T12:00:00.123-07:00']
assert entry['fields'] == {'trip_distance':{'value':'0.0','unit':'mi'},'trip_duration':{'value':'00:00'}}
assert (destination/photo.name).read_bytes() == b'authored input bytes'
# Reconstruct the approved legacy format to exercise installed reader/migration.
monthly['schema_version'] = 1
entry['fields']['trip_duration']['unit'] = None
entry['fields'].update(trip_average_mpg=None,odometer=None)
monthly_path.write_bytes(batch._json_bytes(monthly))
state_path = output/batch._STATE
state = json.loads(state_path.read_bytes())
state['months']['2031-06'] = batch._hash_file(monthly_path)
state['committed'][0]['entry_digest'] = batch._hash_bytes(batch._json_bytes(entry))
state_path.write_bytes(batch._json_bytes(state))
assert batch.rewrite_months(output) == {'rewritten_months':1,'indexed_trips':1}
assert json.loads(monthly_path.read_bytes())['schema_version'] == 2
assert batch._load_state(output)[2] == set()
assert (destination/photo.name).read_bytes() == b'authored input bytes'
assert not list(source.iterdir())
""", directory)


if __name__ == "__main__":
    unittest.main()
