"""Exercise the installed callable; native assets are explicitly provisioned."""

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class InstalledInterpretationTests(unittest.TestCase):
    def test_required_native_provisioning(self):
        if os.environ.get("FLEX_PHOTO_REQUIRE_NATIVE_TESTS") == "1":
            for key in ("FLEX_PHOTO_TESSERACT", "FLEX_PHOTO_TESSDATA",
                        "FLEX_PHOTO_TESSERACT_SHA256"):
                self.assertTrue(os.environ.get(key), f"required native test asset missing: {key}")

    def run_installed(self, code, directory, timeout=45):
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment["PYTHONNOUSERSITE"] = "1"
        result = subprocess.run([sys.executable, "-I", "-c", code], cwd=directory,
                                env=environment, text=True, capture_output=True,
                                timeout=timeout, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((result.stdout, result.stderr), ("", ""))

    def test_missing_assets_stop_before_photo_processing(self):
        with tempfile.TemporaryDirectory(prefix="flex interpretation \u00e9 ") as directory:
            path = Path(directory) / "original.heic"
            path.write_bytes(b"authored invalid photo")
            before = path.read_bytes()
            self.run_installed(r"""
from pathlib import Path
import sys
import flex_photo.interpretation as module
from flex_photo.interpretation import InterpretationAssets, SharedAssetError, interpret_photo
assert Path(module.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
assets = InterpretationAssets(Path('missing-engine'), Path('missing-model'), '0' * 64)
try:
    interpret_photo(Path('original.heic'), assets)
except SharedAssetError:
    pass
else:
    raise AssertionError('missing shared assets must stop rather than classify photo')
assert sorted(p.name for p in Path('.').iterdir()) == ['original.heic']
""", directory)
            self.assertEqual(path.read_bytes(), before)

    @unittest.skipUnless(all(os.environ.get(key) for key in (
        "FLEX_PHOTO_TESSERACT", "FLEX_PHOTO_TESSDATA", "FLEX_PHOTO_TESSERACT_SHA256")),
        "requires explicitly provisioned local OCR executable, model and executable identity")
    def test_real_worker_corrupt_and_white_sources_preserved(self):
        fixture = Path(__file__).resolve().parents[1] / "assets" / "synthetic-white.heic"
        with tempfile.TemporaryDirectory(prefix="flex native \u00e9 ") as directory:
            source = Path(directory)
            (source / "white.heic").write_bytes(fixture.read_bytes())
            (source / "broken.heic").write_bytes(b"authored corrupt HEIC")
            before = {p.name: hashlib.sha256(p.read_bytes()).digest() for p in source.iterdir()}
            self.run_installed(r"""
import os
from pathlib import Path
from flex_photo.interpretation import InterpretationAssets, interpret_photo, validate_interpretation_assets
assets = InterpretationAssets(Path(os.environ['FLEX_PHOTO_TESSERACT']),
    Path(os.environ['FLEX_PHOTO_TESSDATA']), os.environ['FLEX_PHOTO_TESSERACT_SHA256'])
validate_interpretation_assets(assets)
broken = interpret_photo(Path('broken.heic'), assets)
assert broken.layout == 'unresolved' and broken.issues
assert not broken.observations
# A blank generated fixture establishes mechanics, not a real nonmatch rule.
white = interpret_photo(Path('white.heic'), assets)
assert white.layout == 'nonmatch'
assert not white.observations
assert sorted(p.name for p in Path('.').iterdir()) == ['broken.heic', 'white.heic']
""", directory, timeout=160)
            self.assertEqual({p.name: hashlib.sha256(p.read_bytes()).digest()
                              for p in source.iterdir()}, before)

    def test_real_parent_timeout_reaps_worker(self):
        with tempfile.TemporaryDirectory(prefix="flex worker deadline ") as directory:
            self.run_installed(r"""
import subprocess, sys
from pathlib import Path
from unittest.mock import patch
import flex_photo._interpretation_worker as worker
from flex_photo.interpretation import InterpretationAssets
real_popen = subprocess.Popen
children = []
def fixture_process(command, **kwargs):
    command = [sys.executable, '-c', 'import sys,time;sys.stdin.readline();time.sleep(60)']
    child = real_popen(command, **kwargs)
    children.append(child)
    return child
with patch.object(worker.subprocess, 'Popen', side_effect=fixture_process), \
     patch.object(worker, '_DECODE_SECONDS', 0.2):
    try:
        worker.run_bounded(Path('unused.heic'), InterpretationAssets(Path('exe'),Path('models'),'0'*64))
    except RuntimeError as error:
        assert 'deadline' in str(error)
    else:
        raise AssertionError('sleeping worker must time out')
assert len(children) == 1 and children[0].poll() is not None
""", directory)

    def test_timeout_and_crash_remove_private_worker_derivatives(self):
        with tempfile.TemporaryDirectory(prefix="flex derivative cleanup \u00e9 ") as directory:
            self.run_installed(r"""
import json, os, subprocess, sys, tempfile
from pathlib import Path
from unittest.mock import patch
import flex_photo._interpretation_worker as worker
from flex_photo.interpretation import InterpretationAssets
scratch = Path.cwd() / 'scratch'
scratch.mkdir()
for key in ('TMP', 'TEMP', 'TMPDIR'):
    os.environ[key] = str(scratch)
tempfile.tempdir = None
real_popen = subprocess.Popen
children = []
child_code = r'''
import json, os, subprocess, sys, time
from pathlib import Path
request = json.loads(sys.stdin.readline())
folder = Path(request['workspace'])
assert folder.is_dir()
(folder/'models').mkdir(exist_ok=True)
(folder/'reading.ppm').write_bytes(bytes([80,54,10,49,32,49,10,50,53,53,10,0,0,0]))
(folder/'models'/'eng.traineddata').write_bytes(b'authored model surrogate')
held = Path.cwd() / ('held-' + sys.argv[1] + '.txt')
descendant_code = "import os,sys,time;from pathlib import Path;first=open(sys.argv[1],'rb');second=open(sys.argv[2],'rb');Path(sys.argv[3]).write_text(str(os.getpid()));time.sleep(60)"
subprocess.Popen([sys.executable, '-c', descendant_code, str(folder/'reading.ppm'),
                  str(folder/'models'/'eng.traineddata'), str(held)],
                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
deadline = time.monotonic() + 5
while not held.exists():
    if time.monotonic() >= deadline:
        raise RuntimeError('controlled descendant did not open derivatives')
    time.sleep(0.01)
marker = Path.cwd() / ('created-' + sys.argv[1] + '.json')
marker.write_text(json.dumps({'crop': (folder/'reading.ppm').is_file(),
                             'model': (folder/'models'/'eng.traineddata').is_file()}))
print(json.dumps({'stage':'decoded'}), flush=True)
if sys.argv[1] == 'crash':
    os._exit(7)
time.sleep(60)
'''
def controlled_worker(command, **kwargs):
    child = real_popen([sys.executable, '-c', child_code, stage], **kwargs)
    children.append(child)
    return child
for stage in ('timeout', 'crash'):
    with patch.object(worker.subprocess, 'Popen', side_effect=controlled_worker), \
         patch.object(worker, '_DECODE_SECONDS', 5), \
         patch.object(worker, '_PHOTO_SECONDS', 1.5):
        try:
            result = worker.run_bounded(Path('unused.heic'),
                InterpretationAssets(Path('engine'), Path('models'), '0'*64))
        except RuntimeError as error:
            assert stage == 'timeout' and 'deadline' in str(error)
        else:
            assert stage == 'crash' and result.get('error'), result
    marker = json.loads((Path.cwd()/('created-' + stage + '.json')).read_text())
    assert marker == {'crop':True, 'model':True}, marker
    assert (Path.cwd()/('held-' + stage + '.txt')).is_file(), 'descendant never held derivatives'
    assert not list(scratch.iterdir()), 'private worker workspace survived termination'
assert len(children) == 2 and all(child.poll() is not None for child in children)
""", directory)

    @unittest.skipUnless(os.name == "nt", "Windows Job Object enforcement")
    def test_real_windows_job_blocks_large_allocation_and_kills_child(self):
        with tempfile.TemporaryDirectory(prefix="flex job guard ") as directory:
            self.run_installed(r"""
import subprocess, sys
from flex_photo._interpretation_worker import _WindowsJob
# Child waits until assignment, then attempts an allocation beyond the job budget.
code = '''import sys
sys.stdin.readline()
try:
    block = bytearray(2 * 1024**3)
except MemoryError:
    print('bounded', flush=True)
else:
    raise AssertionError('memory guard did not reject allocation')
'''
child = subprocess.Popen([sys.executable,'-c',code], stdin=subprocess.PIPE,
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
job = _WindowsJob(child)
try:
    output, errors = child.communicate('\n',timeout=15)
    assert child.returncode == 0 and output.strip() == 'bounded', (child.returncode, errors)
finally:
    job.close()
    if child.poll() is None:
        child.kill()
    child.wait()
# Assign before release, then verify the worker's descendant inherits containment.
code = '''import subprocess,sys,time
sys.stdin.readline()
descendant = subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
print(descendant.pid, flush=True)
time.sleep(60)
'''
child = subprocess.Popen([sys.executable,'-c',code], stdin=subprocess.PIPE,
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
job = _WindowsJob(child)
import ctypes
from ctypes import wintypes
api = ctypes.WinDLL('kernel32',use_last_error=True)
api.OpenProcess.argtypes = [wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
api.OpenProcess.restype = wintypes.HANDLE
api.WaitForSingleObject.argtypes = [wintypes.HANDLE,wintypes.DWORD]
api.CloseHandle.argtypes = [wintypes.HANDLE]
handle = None
try:
    child.stdin.write('\n')
    child.stdin.flush()
    descendant_pid = int(child.stdout.readline())
    handle = api.OpenProcess(0x100000,False,descendant_pid)
    assert handle, 'descendant must be observable before job close'
    job.close()
    assert child.wait(timeout=10) is not None
    assert api.WaitForSingleObject(handle,10000) == 0, 'descendant survived job close'
finally:
    job.close()
    if handle:
        api.CloseHandle(handle)
    if child.poll() is None:
        child.kill()
    child.wait()
    child.stdin.close()
    child.stdout.close()
    child.stderr.close()
""", directory)

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux address-space enforcement")
    def test_real_linux_worker_installs_limit_before_decode(self):
        with tempfile.TemporaryDirectory(prefix="flex address space guard ") as directory:
            self.run_installed(r"""
import io, json, resource, sys
from types import SimpleNamespace
import flex_photo._interpretation_worker as worker
def allocate(path):
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    assert soft == hard == 1024**3
    try:
        block = bytearray(2 * 1024**3)
    except MemoryError:
        raise ValueError('guard enforced')
    raise AssertionError('allocation unexpectedly succeeded')
worker._validate_assets = lambda assets: None
worker.subprocess.run = lambda *args, **kwargs: SimpleNamespace(
    returncode=0, stdout='tesseract 5.3.0\n')
worker._decode = allocate
sys.stdin = io.StringIO(json.dumps({'path':'unused','exe':'unused','models':'unused','sha':'0'*64})+'\n')
output = io.StringIO()
from contextlib import redirect_stdout
with redirect_stdout(output):
    worker.main()
result = json.loads(output.getvalue())
assert result.get('error', '').endswith('ValueError'), result
""", directory)


if __name__ == "__main__":
    unittest.main()
