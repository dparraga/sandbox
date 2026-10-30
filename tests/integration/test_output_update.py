"""Installed sparse-format crash recovery and pinned filename timezone behavior."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class InstalledOutputUpdateTests(unittest.TestCase):
    def run_installed(self, code, directory, expected=0):
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        result = subprocess.run([sys.executable, "-I", "-c", code], cwd=directory,
                                env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, expected, result.stderr)
        self.assertEqual((result.stdout, result.stderr), ("", ""))

    def test_real_process_exit_between_month_and_index_recovers_once(self):
        with tempfile.TemporaryDirectory(prefix="flex rewrite restart \u00e9 ") as directory:
            self.run_installed(r"""
import os, sys
from pathlib import Path
from unittest.mock import patch
import flex_photo.batch as batch
assert Path(batch.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
stamp = '2031-06-12T12:00:00+00:00'
entry = {'trip_date':'2031-06-12', 'first_capture_times':[stamp], 'last_capture_times':[stamp],
         'month_assignment':'latest_capture_local', 'fields':{
             'trip_distance':{'value':'0.0','unit':'mi'},
             'trip_duration':{'value':'00:00','unit':None},
             'trip_average_mpg':None, 'odometer':None}}
monthly = {'schema_version':1, 'month':'2031-06', 'trips':[entry]}
encoded = batch._json_bytes(monthly)
state = {'state_version':1, 'committed':[{'hashes':['a'*64], 'captures':[stamp],
         'window_microseconds':180000000, 'month':'2031-06', 'entry_index':0,
         'entry_digest':batch._hash_bytes(batch._json_bytes(entry))}],
         'months':{'2031-06':batch._hash_bytes(encoded)}, 'pending':None}
Path('2031-06.json').write_bytes(encoded)
Path(batch._STATE).write_bytes(batch._json_bytes(state))
real_write = batch._atomic_write
def write(path, data, expected):
    real_write(path, data, expected)
    if path.name == '2031-06.json':
        os._exit(77)
with patch.object(batch, '_atomic_write', side_effect=write):
    batch.rewrite_months(Path.cwd())
raise AssertionError('fixture did not terminate at publication boundary')
""", directory, expected=77)
            self.assertTrue((Path(directory) / ".flex-photo-rewrite.json").is_file())
            self.run_installed(r"""
import json
from pathlib import Path
import flex_photo.batch as batch
batch.rewrite_months(Path.cwd())
with batch._output_lock(Path.cwd()):
    state, _, invalid = batch._load_state(Path.cwd())
assert not invalid and state['pending'] is None and len(state['committed']) == 1
monthly = json.loads(Path('2031-06.json').read_bytes())
assert monthly['schema_version'] == 2
assert monthly['trips'][0]['fields'] == {
    'trip_distance':{'value':'0.0','unit':'mi'}, 'trip_duration':{'value':'00:00'}}
assert not Path(batch._REWRITE).exists()
before = Path('2031-06.json').read_bytes(), Path(batch._STATE).read_bytes()
assert batch.rewrite_months(Path.cwd())['rewritten_months'] == 0
assert before == (Path('2031-06.json').read_bytes(), Path(batch._STATE).read_bytes())
""", directory)

    def test_filename_grouping_uses_packaged_rules_not_system_timezone(self):
        with tempfile.TemporaryDirectory(prefix="flex filename timezone \u00e9 ") as directory:
            self.run_installed(r"""
import os
from datetime import timedelta, timezone
from pathlib import Path
os.environ['TZ'] = 'UTC'
os.environ['PYTHONTZPATH'] = str(Path.cwd() / 'unavailable-zone-database')
from flex_photo.capture_fallback import CAPTURE_POLICY, CaptureFallbackError, resolve_capture
from flex_photo.grouping import group_capture_times
captures = []
for stem in ('20310612_183504223_iOS', '20310612_183604224_iOS'):
    path = Path(stem + '.heic')
    context = {'creation_time_ns':None, 'filename':path.name, 'policy':CAPTURE_POLICY}
    result = resolve_capture(path, None, inputs=context)
    assert result.source == 'filename'
    assert type(result.capture.tzinfo) is timezone
    assert result.capture.utcoffset() == timedelta(hours=-7)
    captures.append(result.capture)
assert group_capture_times(captures, timedelta(minutes=3)) == ((0,1),)
bare = Path('20310612.heic')
try:
    resolve_capture(bare, None, inputs={'creation_time_ns':None, 'filename':bare.name, 'policy':CAPTURE_POLICY})
except CaptureFallbackError as error:
    assert error.silent
else:
    raise AssertionError('date-only filename must not invent a clock')
""", directory)


if __name__ == "__main__":
    unittest.main()
