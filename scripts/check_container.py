"""Verify installed behavior with restricted offline container runtime."""

import argparse
import json
from pathlib import Path
import tempfile
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from metadata_fixture import heif_metadata, huge_header_read


def run(command, expected=0):
    result = subprocess.run(command, text=True, capture_output=True, timeout=60, check=False)
    print(result.stdout, end="")
    print(result.stderr, end="")
    if result.returncode != expected:
        raise RuntimeError(f"Expected exit {expected}, received {result.returncode}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    args = parser.parse_args()
    restricted = ["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
                  "--security-opt", "no-new-privileges"]
    for options, expected in [([], 0), (["--help"], 0), (["--version"], 0), (["--invalid-option"], 2)]:
        result = run(restricted + [args.image] + options, expected)
        if expected == 2:
            assert not result.stdout and "unrecognized arguments" in result.stderr
        else:
            assert not result.stderr
            if not options:
                assert "bootstrap" in result.stdout.lower() and "unavailable" in result.stdout.lower()
            elif options == ["--version"]:
                assert result.stdout.strip() == "flex-photo 0.1.0"
            else:
                assert "--version" in result.stdout
    # Public synthetic data only; permissions allow the image's nonroot UID.
    with tempfile.TemporaryDirectory(prefix="flex-container-") as directory:
        source = Path(directory)
        source.chmod(0o755)
        leaf = source / "day 1"
        leaf.mkdir(mode=0o755)
        for path in [source / "a.HEIC", leaf / "caf\u00e9.heic", source / "ignored.heif"]:
            path.write_bytes(b"synthetic, not a photo")
            path.chmod(0o644)
        mounted = restricted + ["--mount", f"type=bind,source={source},target=/photos,readonly"]
        result = run(mounted + [args.image, "discover", "/photos"])
        assert not result.stderr
        assert result.stdout == json.dumps(["a.HEIC", "day 1/caf\u00e9.heic"], ensure_ascii=True) + "\n"
        failure = run(mounted + [args.image, "discover", "/photos/missing"], 1)
        assert not failure.stdout and "invalid-source:" in failure.stderr
        assert "/photos" not in failure.stderr and "Traceback" not in failure.stderr
        assert sorted(path.relative_to(source).as_posix() for path in source.rglob("*")) == ["a.HEIC", "day 1", "day 1/caf\u00e9.heic", "ignored.heif"]
        capture, unsafe = source / "capture.heic", source / "unsafe.heic"
        capture.write_bytes(heif_metadata())
        unsafe.write_bytes(huge_header_read())
        capture.chmod(0o644)
        unsafe.chmod(0o644)
        before = {path.name: path.read_bytes() for path in (capture, unsafe)}
        metadata_result = run(mounted + ["--entrypoint", "python", args.image, "-c", """
from datetime import datetime, timedelta, timezone
import importlib.metadata, pathlib
from flex_photo.capture_time import CaptureTimeError, parse_capture_time
from flex_photo.grouping import group_capture_times
from flex_photo.metadata import CaptureMetadata, MetadataError, read_capture_metadata
from flex_photo.selection import latest_clear_indices
raw = read_capture_metadata(pathlib.Path('/photos/capture.heic'))
assert raw == CaptureMetadata('2030:02:03 04:05:06', '+02:30', '123456')
parsed = parse_capture_time(raw)
assert parsed == datetime(2030, 2, 3, 4, 5, 6, 123456, tzinfo=timezone(timedelta(minutes=150)))
assert parsed.hour == 4 and parsed.utcoffset() == timedelta(minutes=150)
assert raw.subsec_time_original == '123456'
captures = [parsed + timedelta(minutes=4), parsed,
            parsed + timedelta(minutes=3), parsed + timedelta(minutes=3, microseconds=1),
            parsed.astimezone(timezone.utc)]
assert group_capture_times(captures) == ((1, 4, 2), (3, 0))
assert group_capture_times([parsed, parsed + timedelta(minutes=2), parsed + timedelta(minutes=4)]) == ((0, 1), (2,))
group = group_capture_times(captures)[0]
local_times = [captures[index] for index in group]
def source_candidates(flags):
    return tuple(group[index] for index in latest_clear_indices(local_times, [flags[index] for index in group]))
assert source_candidates([False, True, False, False, False]) == (1,)
assert source_candidates([False, False, True, False, False]) == (2,)
assert source_candidates([False, True, False, False, True]) == (1, 4)
assert source_candidates([False] * len(captures)) == ()
retained_values = [None, 0, None, None, None]
assert tuple(retained_values[index] for index in source_candidates([False, True, False, False, False])) == (0,)
try:
    parse_capture_time(CaptureMetadata(raw.date_time_original, None, None))
except CaptureTimeError as error:
    assert str(error) == 'offset_time_original: missing'
else:
    raise AssertionError('missing capture-time error')
try:
    read_capture_metadata(pathlib.Path('/photos/unsafe.heic'))
except MetadataError as error:
    assert str(error) == 'metadata limit exceeded'
else:
    raise AssertionError('missing limit error')
dependency = importlib.metadata.distribution('ExifRead')
assert dependency.version == '3.5.1'
licenses = [path for path in dependency.files if str(path).endswith('.dist-info/licenses/LICENSE')]
assert len(licenses) == 1
assert 'Redistribution and use in source and binary forms' in dependency.locate_file(licenses[0]).read_text()
print('installed metadata extraction, capture-time conversion, grouping, selection, guard and dependency license passed')
"""])
        assert not metadata_result.stderr
        assert {path.name: path.read_bytes() for path in (capture, unsafe)} == before
    # This also records the actual container interpreter and verifies numeric nonroot execution.
    run(restricted + ["--entrypoint", "python", args.image, "-c",
                      "import os,sys,importlib.util; assert os.getuid()!=0; "
                      "assert importlib.util.find_spec('setuptools') is None; "
                      "print(sys.version); print('uid:',os.getuid())"])


if __name__ == "__main__":
    main()
