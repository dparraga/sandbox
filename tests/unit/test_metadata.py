"""Three-field extraction and bounded parsing, without private photographs."""

from dataclasses import FrozenInstanceError
import io
import logging
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import exifread
from flex_photo import metadata
from flex_photo.metadata import CaptureMetadata, MetadataError, read_capture_metadata

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from metadata_fixture import heif_metadata, huge_header_read, nonprogressing_box


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "capture.heic"
        self.path.write_bytes(heif_metadata())

    def assert_safe_error(self, reason, action):
        with self.assertRaises(MetadataError) as caught:
            action()
        self.assertEqual(str(caught.exception), reason)
        self.assertEqual(caught.exception.path, self.path)
        self.assertNotIn(str(self.path), str(caught.exception))
        return caught.exception

    def test_real_heif_exact_text_immutable_and_source_preserved(self):
        # Long subsecond text must not use the backend's abbreviated display.
        expected = CaptureMetadata(" invalid date ", "+02:30", "1234567890" * 20)
        original = heif_metadata(date=expected.date_time_original,
                                 offset=expected.offset_time_original,
                                 subsec=expected.subsec_time_original)
        self.path.write_bytes(original)
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            result = read_capture_metadata(self.path)
        self.assertEqual(result, expected)
        with self.assertRaises(FrozenInstanceError):
            result.date_time_original = "changed"
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])
        self.assertEqual((stdout.getvalue(), stderr.getvalue()), ("", ""))

    def test_missing_targets_and_backend_empty_result_are_none(self):
        for content in [heif_metadata(date=None, offset=None, subsec=None), b"not HEIF", b""]:
            with self.subTest(length=len(content)):
                self.path.write_bytes(content)
                self.assertEqual(read_capture_metadata(self.path), CaptureMetadata(None, None, None))

    def test_real_nontext_target_rejected(self):
        self.path.write_bytes(heif_metadata(nontext=True))
        self.assert_safe_error("timestamp tag is not text", lambda: read_capture_metadata(self.path))

    def test_real_malformed_inputs_are_bounded_and_safe(self):
        for content in [huge_header_read(), nonprogressing_box()]:
            with self.subTest(kind=content[:8]):
                self.path.write_bytes(content)
                self.assert_safe_error("metadata limit exceeded", lambda: read_capture_metadata(self.path))
        # The backend detects this cyclic IFD and returns once, rather than
        # repeatedly following it. Malformation alone is not a required error.
        self.path.write_bytes(heif_metadata(cycle=True))
        self.assertEqual(read_capture_metadata(self.path), CaptureMetadata("2030:02:03 04:05:06", "+02:30", "123456"))
        self.path.write_bytes(heif_metadata()[:40])
        try:
            result = read_capture_metadata(self.path)
        except MetadataError as error:
            self.assertIn(str(error), ("metadata parsing failed", "metadata limit exceeded"))
        else:
            self.assertEqual(result, CaptureMetadata(None, None, None))

    def test_sticky_failure_not_hidden_by_backend(self):
        def swallowed(stream, **kwargs):
            try:
                stream.read(-1)
            except Exception:
                pass
            return {}
        with patch.object(exifread, "process_file", swallowed):
            self.assert_safe_error("metadata limit exceeded", lambda: read_capture_metadata(self.path))

    def test_nontext_backend_values_including_none_rejected(self):
        for value in [None, 7, ["text"]]:
            with self.subTest(value=value), patch.object(exifread, "process_file", return_value={"EXIF DateTimeOriginal": SimpleNamespace(values=value)}):
                self.assert_safe_error("timestamp tag is not text", lambda: read_capture_metadata(self.path))

    def test_backend_errors_and_logger_restoration_without_output(self):
        dedicated, root, unrelated = exifread.logger, logging.getLogger(), logging.getLogger("unrelated")
        prior = (dedicated.disabled, root.disabled, unrelated.disabled)
        self.addCleanup(setattr, dedicated, "disabled", prior[0])
        for disabled in (False, True):
            dedicated.disabled = disabled
            def backend(stream, **kwargs):
                self.assertTrue(dedicated.disabled)
                self.assertEqual((root.disabled, unrelated.disabled), prior[1:])
                self.assertEqual(kwargs, dict(details=False, extract_thumbnail=False,
                                             debug=False, strict=True, truncate_tags=False))
                dedicated.error("private metadata")
                raise RuntimeError("private backend text")
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch.object(exifread, "process_file", backend), patch("sys.stdout", stdout), patch("sys.stderr", stderr):
                self.assert_safe_error("metadata parsing failed", lambda: read_capture_metadata(self.path))
            self.assertEqual(dedicated.disabled, disabled)
            self.assertEqual((stdout.getvalue(), stderr.getvalue()), ("", ""))

    def test_invalid_file_and_detected_replacement_rejected(self):
        original = self.path.lstat()
        with patch.object(Path, "lstat", side_effect=FileNotFoundError("private OS text")):
            self.assert_safe_error("file unavailable", lambda: read_capture_metadata(self.path))
        for replacement in [SimpleNamespace(st_mode=stat.S_IFDIR),
                            SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)]:
            with patch.object(Path, "lstat", side_effect=[original, replacement]):
                self.assert_safe_error("file unavailable", lambda: read_capture_metadata(self.path))
        other = self.path.with_name("replacement.heic")
        other.write_bytes(heif_metadata())
        different = other.lstat()
        for sequence in [[original, different], [original, original, different]]:
            with patch.object(Path, "lstat", side_effect=sequence):
                self.assert_safe_error("file unavailable", lambda: read_capture_metadata(self.path))
        with patch.object(metadata.os, "fstat", return_value=different):
            self.assert_safe_error("file unavailable", lambda: read_capture_metadata(self.path))

    def test_real_symlink_rejected(self):
        target = self.path.with_name("target.heic")
        self.path.rename(target)
        try:
            self.path.symlink_to(target)
        except OSError as error:
            self.skipTest(f"Symlinks unavailable: {type(error).__name__}")
        self.assert_safe_error("file unavailable", lambda: read_capture_metadata(self.path))

    def test_stream_closes_on_backend_failure_and_io_close_errors_are_safe(self):
        real_fdopen = os.fdopen
        opened = []
        def tracked(descriptor, mode):
            stream = real_fdopen(descriptor, mode)
            opened.append(stream)
            return stream
        with patch.object(metadata.os, "fdopen", tracked), patch.object(exifread, "process_file", side_effect=RuntimeError("private")):
            self.assert_safe_error("metadata parsing failed", lambda: read_capture_metadata(self.path))
        self.assertTrue(opened[0].closed)
        class BrokenClose:
            def __init__(self, stream):
                self.stream = stream
            def __getattr__(self, name):
                return getattr(self.stream, name)
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.stream.close()
                raise OSError("private close text")
        with patch.object(metadata.os, "fdopen", lambda fd, mode: BrokenClose(real_fdopen(fd, mode))):
            self.assert_safe_error("file unavailable", lambda: read_capture_metadata(self.path))
        with patch.object(metadata.os, "open", side_effect=PermissionError("private open text")):
            self.assert_safe_error("file unavailable", lambda: read_capture_metadata(self.path))
        with patch.object(exifread, "process_file", side_effect=OSError("private read text")):
            self.assert_safe_error("file unavailable", lambda: read_capture_metadata(self.path))

    def test_descriptor_closed_when_stream_construction_fails(self):
        real_close = os.close
        with patch.object(metadata.os, "fdopen", side_effect=OSError("private fdopen text")), patch.object(metadata.os, "close", wraps=real_close) as close:
            self.assert_safe_error("file unavailable", lambda: read_capture_metadata(self.path))
        self.assertEqual(close.call_count, 1)
        with self.assertRaises(OSError):
            os.fstat(close.call_args.args[0])


class ParserGuardTests(unittest.TestCase):
    def test_unbounded_large_reads_and_outside_seeks_rejected_before_io(self):
        for action in [lambda s: s.read(), lambda s: s.read(-2),
                       lambda s: s.read(1024 * 1024 + 1),
                       lambda s: s.seek(-1), lambda s: s.seek(5),
                       lambda s: s.seek(1, os.SEEK_END)]:
            stream = io.BytesIO(b"1234")
            guard = metadata._BoundedStream(stream, 4)
            with self.assertRaises(metadata._LimitExceeded):
                action(guard)
            self.assertTrue(guard.failed)
            self.assertEqual(stream.tell(), 0)
            with self.assertRaises(metadata._LimitExceeded):
                guard.read(0)

    def test_actual_cumulative_and_combined_operation_limits(self):
        block = b"x" * (1024 * 1024)
        guard = metadata._BoundedStream(io.BytesIO(block), len(block))
        for _ in range(64):
            self.assertEqual(len(guard.read(len(block))), len(block))
            guard.seek(0)
        with self.assertRaises(metadata._LimitExceeded):
            guard.read(1)
        self.assertTrue(guard.failed)
        guard = metadata._BoundedStream(io.BytesIO(b""), 0)
        for index in range(100_000):
            [lambda: guard.read(0), lambda: guard.seek(0), guard.tell][index % 3]()
        with self.assertRaises(metadata._LimitExceeded):
            guard.tell()
        self.assertTrue(guard.failed)

    def test_seek_modes_and_eof_reads(self):
        guard = metadata._BoundedStream(io.BytesIO(b"1234"), 4)
        self.assertEqual(guard.seek(-1, os.SEEK_END), 3)
        self.assertEqual(guard.read(10), b"4")
        self.assertEqual(guard.tell(), 4)
        self.assertEqual(guard.read(10), b"")
        self.assertEqual(guard.seek(-2, os.SEEK_CUR), 2)
        self.assertEqual(guard.read(1), b"3")


if __name__ == "__main__":
    unittest.main()
