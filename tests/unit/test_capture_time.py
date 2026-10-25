"""Behavioral checks for strict original-capture time conversion."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import io
import unittest
from unittest.mock import patch

from flex_photo.capture_time import CaptureTimeError, parse_capture_time
from flex_photo.metadata import CaptureMetadata


class CaptureTimeTests(unittest.TestCase):
    baseline = CaptureMetadata("2030:02:03 04:05:06", "+02:30", "123456")

    def assert_rejected(self, metadata, field, reason):
        with self.assertRaises(CaptureTimeError) as caught:
            parse_capture_time(metadata)
        error = caught.exception
        self.assertEqual((error.field, error.reason), (field, reason))
        self.assertEqual(str(error), f"{field}: {reason}")
        return error

    def test_exact_date_offset_and_fraction_without_normalization(self):
        result = parse_capture_time(self.baseline)
        self.assertEqual(result, datetime(2030, 2, 3, 4, 5, 6, 123456,
                                         tzinfo=timezone(timedelta(hours=2, minutes=30))))
        self.assertEqual(result.hour, 4)
        self.assertEqual(result.utcoffset(), timedelta(hours=2, minutes=30))
        self.assertIsInstance(result.tzinfo, timezone)

    def test_gregorian_and_supported_year_boundaries(self):
        for text, expected in [("0001:01:01 00:00:00", (1, 1, 1)),
                               ("9999:12:31 23:59:59", (9999, 12, 31)),
                               ("2000:02:29 12:00:00", (2000, 2, 29))]:
            with self.subTest(text=text):
                result = parse_capture_time(replace(self.baseline, date_time_original=text))
                self.assertEqual((result.year, result.month, result.day), expected)

    def test_strict_date_rejections(self):
        bad = ["0000:01:01 00:00:00", "1900:02:29 00:00:00", "2030:02:29 00:00:00",
               "2030:04:31 00:00:00", "2030:00:03 04:05:06", "2030:13:03 04:05:06",
               "2030:02:00 04:05:06", "2030:02:03 24:05:06", "2030:02:03 04:60:06",
               "2030:02:03 04:05:60", "2030-02-03 04:05:06", "2030:02:03T04:05:06",
               "2030:2:03 04:05:06", "2030:02:03 04:05:06 ", "2030:02:03 04:05:06\n",
               "２０３０:02:03 04:05:06", "2030:02:03 04:05:٠٦", "", "9" * 10000,
               2030, b"2030:02:03 04:05:06", True]
        for text in bad:
            with self.subTest(value=text if isinstance(text, str) and len(text) < 50 else type(text).__name__):
                self.assert_rejected(replace(self.baseline, date_time_original=text),
                                     "date_time_original", "invalid")
        self.assert_rejected(replace(self.baseline, date_time_original=None),
                             "date_time_original", "missing")

    def test_signed_offsets_zero_and_nonwhole_hours(self):
        for text, minutes in [("+00:00", 0), ("-00:00", 0), ("+23:59", 1439),
                              ("-23:59", -1439), ("+05:45", 345), ("-03:30", -210)]:
            with self.subTest(offset=text):
                metadata = replace(self.baseline, offset_time_original=text)
                result = parse_capture_time(metadata)
                self.assertEqual(result.utcoffset(), timedelta(minutes=minutes))
                self.assertEqual((result.year, result.month, result.day, result.hour), (2030, 2, 3, 4))
                self.assertEqual(metadata.offset_time_original, text)

    def test_offset_rejections_and_required_value(self):
        for text in ["Z", "00:00", "+24:00", "-24:00", "+00:60", "+2:30", "+02:3",
                     "+02:30 ", " +02:30", "+٠٢:30", "−02:30", "", "9" * 10000,
                     150, b"+02:30", False]:
            with self.subTest(value=text if isinstance(text, str) and len(text) < 30 else type(text).__name__):
                self.assert_rejected(replace(self.baseline, offset_time_original=text),
                                     "offset_time_original", "invalid")
        self.assert_rejected(replace(self.baseline, offset_time_original=None),
                             "offset_time_original", "missing")

    def test_absent_and_exact_fractional_values_preserve_raw_text(self):
        for text, expected in [(None, 0), ("0", 0), ("1", 100000), ("01", 10000),
                               ("123", 123000), ("0123", 12300), ("12345", 123450),
                               ("000001", 1), ("123400", 123400), ("999999", 999999)]:
            with self.subTest(fraction=text):
                metadata = replace(self.baseline, subsec_time_original=text)
                self.assertEqual(parse_capture_time(metadata).microsecond, expected)
                self.assertEqual(metadata.subsec_time_original, text)

    def test_fraction_rejections_without_rounding_or_truncation(self):
        for text in ["", " 1", "1 ", ".1", "1.0", "-1", "١", "１", "1\n", 1, b"1", True]:
            with self.subTest(value=text):
                self.assert_rejected(replace(self.baseline, subsec_time_original=text),
                                     "subsec_time_original", "invalid")
        for text in ["1234567", "0000000", "9" * 10000]:
            with self.subTest(length=len(text)):
                self.assert_rejected(replace(self.baseline, subsec_time_original=text),
                                     "subsec_time_original", "unsupported precision")

    def test_error_precedence_sanitization_and_no_output(self):
        private = "private /photos/secret.heic\n2030:02:03 04:05:06"
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            self.assert_rejected(CaptureMetadata(None, None, "1234567"), "date_time_original", "missing")
            self.assert_rejected(replace(self.baseline, offset_time_original=None, subsec_time_original="bad"),
                                 "offset_time_original", "missing")
            error = self.assert_rejected(replace(self.baseline, date_time_original=private),
                                         "date_time_original", "invalid")
        self.assertNotIn(private, str(error))
        self.assertIsNone(error.__cause__)
        self.assertEqual((output.getvalue(), errors.getvalue()), ("", ""))

    def test_pure_conversion_ignores_io_and_environment(self):
        original = self.baseline
        with patch("builtins.open", side_effect=AssertionError("file I/O")), \
             patch("os.getenv", side_effect=AssertionError("environment read")), \
             patch("os.environ", {}), \
             patch("socket.socket", side_effect=AssertionError("network I/O")):
            first = parse_capture_time(original)
        with patch.dict("os.environ", {"TZ": "Pacific/Honolulu"}):
            self.assertEqual(parse_capture_time(original), first)
        self.assertEqual(original, CaptureMetadata("2030:02:03 04:05:06", "+02:30", "123456"))


if __name__ == "__main__":
    unittest.main()
