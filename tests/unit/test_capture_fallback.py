"""Authorized fallback precedence, real birth time and literal filename clocks."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import stat
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flex_photo.capture_fallback import (
    CAPTURE_POLICY, CaptureFallbackError, _la_zone, capture_inputs,
    capture_inputs_match, resolve_capture,
)
from flex_photo.capture_time import CaptureTimeError
from flex_photo.grouping import group_capture_times
from flex_photo.metadata import CaptureMetadata


class CaptureFallbackTests(unittest.TestCase):
    path = Path("20310612_183604224_iOS.heic")

    def context(self, path=None, birth=None):
        return {"creation_time_ns": birth, "filename": (path or self.path).name, "policy": CAPTURE_POLICY}

    def test_original_metadata_wins_and_keeps_its_precision_and_offset(self):
        metadata = CaptureMetadata("2031:06:12 08:01:02", "+02:30", "120")
        with patch("flex_photo.capture_fallback.capture_inputs", side_effect=AssertionError("must not use fallback")):
            result = resolve_capture(self.path, metadata)
        self.assertEqual(result.source, "metadata")
        self.assertEqual(result.spelling, "2031-06-12T08:01:02.120+02:30")
        self.assertIsNone(result.inputs)

    def test_present_invalid_metadata_is_not_silently_repaired(self):
        for metadata in (CaptureMetadata("2031:06:12 08:01:02", None, None),
                         CaptureMetadata("2031:06:12 08:01:99", "+00:00", None),
                         CaptureMetadata(None, "bad", None),
                         CaptureMetadata(None, None, "x"),
                         CaptureMetadata(None, "+24:00", "1")):
            with self.subTest(metadata=metadata), self.assertRaises(CaptureTimeError):
                resolve_capture(self.path, metadata, inputs=self.context(birth=0))

    def test_birth_instant_precedes_filename_and_uses_los_angeles_day(self):
        utc = datetime(2031, 6, 13, 1, 2, 3, 456789, tzinfo=timezone.utc)
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        birth = ((utc - epoch) // timedelta(microseconds=1)) * 1000 + 123
        result = resolve_capture(self.path, CaptureMetadata(None, None, None), inputs=self.context(birth=birth))
        self.assertEqual(result.source, "file_creation")
        self.assertEqual(result.spelling, "2031-06-12T18:02:03.456789-07:00")
        self.assertIs(type(result.capture.tzinfo), timezone)
        self.assertEqual(result.capture.astimezone(timezone.utc), utc)

    def test_zero_creation_timestamp_is_available_not_missing(self):
        result = resolve_capture(self.path, None, inputs=self.context(birth=0))
        self.assertEqual(result.source, "file_creation")
        self.assertEqual(result.spelling, "1969-12-31T16:00:00-08:00")

    def test_filename_preserves_milliseconds_and_supports_existing_trip_window(self):
        first = Path("20310612_183504223_iOS.heic")
        a = resolve_capture(first, None, inputs=self.context(first))
        b = resolve_capture(self.path, None, inputs=self.context())
        self.assertEqual(b.spelling, "2031-06-12T18:36:04.224-07:00")
        self.assertEqual(b.source, "filename")
        self.assertIs(type(b.capture.tzinfo), timezone)
        self.assertEqual(group_capture_times([a.capture, b.capture], timedelta(minutes=3)), ((0, 1),))

    def test_birth_time_does_not_use_change_or_modification_time(self):
        info = SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0,
                               st_ctime_ns=0, st_mtime_ns=0)
        with patch.object(Path, "lstat", return_value=info):
            context = capture_inputs(self.path)
        self.assertIsNone(context["creation_time_ns"])
        self.assertEqual(resolve_capture(self.path, None, inputs=context).source, "filename")

    def test_birth_time_identity_is_independent_of_photo_bytes(self):
        info = SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0, st_birthtime_ns=123)
        with patch.object(Path, "lstat", return_value=info):
            saved = capture_inputs(self.path)
            self.assertTrue(capture_inputs_match(self.path, saved))
            info.st_birthtime_ns = 124
            self.assertFalse(capture_inputs_match(self.path, saved))

    def test_unrepresentable_birth_time_can_use_filename(self):
        result = resolve_capture(self.path, None, inputs=self.context(birth=10 ** 40))
        self.assertEqual(result.source, "filename")

    def test_bare_date_skips_without_item_report(self):
        path = Path("20310612.heic")
        with self.assertRaises(CaptureFallbackError) as caught:
            resolve_capture(path, None, inputs=self.context(path))
        self.assertTrue(caught.exception.silent)

    def test_filename_does_not_guess_precision_calendar_or_dst_offset(self):
        cases = ("20310612_183604_iOS.heic", "20310612_1836042249999_iOS.heic",
                 "20310230_183604224_iOS.heic", "20310612_246004224_iOS.heic",
                 "20260308_023000000_iOS.heic", "20261101_013000000_iOS.heic")
        for name in cases:
            path = Path(name)
            with self.subTest(name=name), self.assertRaises(CaptureFallbackError) as caught:
                resolve_capture(path, None, inputs=self.context(path))
            self.assertFalse(caught.exception.silent)

    def test_creation_instant_resolves_both_sides_of_fall_dst_fold(self):
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        spellings = []
        for hour in (8, 9):
            utc = datetime(2026, 11, 1, hour, 30, tzinfo=timezone.utc)
            birth = ((utc - epoch) // timedelta(microseconds=1)) * 1000
            spellings.append(resolve_capture(self.path, None, inputs=self.context(birth=birth)).spelling)
        self.assertEqual(spellings, ["2026-11-01T01:30:00-07:00", "2026-11-01T01:30:00-08:00"])

    def test_incompatible_policy_and_timezone_data_fail_explicitly(self):
        with self.assertRaises(CaptureFallbackError):
            resolve_capture(self.path, None, inputs=dict(self.context(), policy="other"))
        with patch("tzdata.__version__", "unapproved"), self.assertRaises(CaptureFallbackError):
            _la_zone.__wrapped__()


if __name__ == "__main__":
    unittest.main()
