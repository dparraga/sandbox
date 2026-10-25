"""Behavioral checks for bounded first-to-last capture-time grouping."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone, tzinfo
import io
import unittest

from flex_photo.grouping import group_capture_times


class CustomZone(tzinfo):
    def utcoffset(self, value):
        raise AssertionError("unsupported timezone must not be evaluated")


class GroupingTests(unittest.TestCase):
    anchor = datetime(2030, 2, 3, tzinfo=timezone.utc)

    def captures(self, *minutes):
        return [self.anchor + timedelta(minutes=value) for value in minutes]

    def assert_rejected(self, captures, error_type, message, **kwargs):
        with self.assertRaises(error_type) as caught:
            group_capture_times(captures, **kwargs)
        self.assertEqual(str(caught.exception), message)

    def test_empty_singleton_and_sequence_inputs(self):
        self.assertEqual(group_capture_times([]), ())
        self.assertEqual(group_capture_times((self.anchor,)), ((0,),))
        self.assertEqual(group_capture_times(self.captures(0, 3)), ((0, 1),))

    def test_inclusive_boundary_microsecond_exclusion_and_no_chaining(self):
        captures = self.captures(0, 2, 3, 4)
        captures.insert(3, self.anchor + timedelta(minutes=3, microseconds=1))
        self.assertEqual(group_capture_times(captures), ((0, 1, 2), (3, 4)))
        self.assertEqual(group_capture_times(self.captures(0, 2, 4)), ((0, 1), (2,)))

    def test_unsorted_indices_complete_once_and_input_unchanged(self):
        captures = self.captures(9, 2, 4, 0, 9, 6)
        before = captures.copy()
        groups = group_capture_times(captures)
        self.assertEqual(groups, ((3, 1), (2, 5), (0, 4)))
        self.assertEqual(sorted(index for group in groups for index in group), list(range(len(captures))))
        self.assertTrue(all(group for group in groups))
        self.assertEqual(captures, before)
        self.assertTrue(all(actual is original for actual, original in zip(captures, before)))

    def test_equal_instants_keep_original_order_across_offsets(self):
        captures = [self.anchor.astimezone(timezone(timedelta(hours=3))),
                    self.anchor, self.anchor.astimezone(timezone(timedelta(hours=-4)))]
        self.assertEqual(group_capture_times(captures, timedelta(0)), ((0, 1, 2),))

    def test_offset_changes_can_reverse_wall_clock_order(self):
        captures = [datetime(2030, 2, 3, 12, tzinfo=timezone(timedelta(hours=-4))),
                    datetime(2030, 2, 3, 13, tzinfo=timezone(timedelta(hours=3)))]
        self.assertEqual(group_capture_times(captures), ((1,), (0,)))

    def test_cross_midnight_month_and_year_boundaries(self):
        for anchor in [datetime(2030, 2, 3, 23, 59, tzinfo=timezone.utc),
                       datetime(2030, 2, 28, 23, 59, tzinfo=timezone.utc),
                       datetime(2030, 12, 31, 23, 59, tzinfo=timezone.utc)]:
            with self.subTest(anchor=anchor):
                self.assertEqual(group_capture_times([anchor + timedelta(minutes=3), anchor]), ((1, 0),))

    def test_zero_and_maximum_windows(self):
        captures = [self.anchor + timedelta(microseconds=1), self.anchor, self.anchor]
        self.assertEqual(group_capture_times(captures, timedelta(0)), ((1, 2), (0,)))
        extremes = [datetime.max.replace(tzinfo=timezone.utc), datetime.min.replace(tzinfo=timezone.utc)]
        self.assertEqual(group_capture_times(extremes, timedelta.max), ((1, 0),))

    def test_extreme_offset_instants_without_utc_or_window_overflow(self):
        positive = timezone(timedelta(hours=23, minutes=59))
        negative = timezone(-timedelta(hours=23, minutes=59))
        earliest = datetime.min.replace(tzinfo=positive)
        latest = datetime.max.replace(tzinfo=negative)
        nearby = datetime(1, 1, 1, 0, 1, tzinfo=timezone(timedelta(hours=23)))
        for captures, window in [([earliest + timedelta(minutes=3), earliest], timedelta(minutes=3)),
                                 ([latest, latest - timedelta(minutes=3)], timedelta(minutes=3)),
                                 ([latest, earliest], timedelta.max)]:
            with self.subTest(captures=captures):
                self.assertEqual(group_capture_times(captures, window), ((1, 0),))
        # Differing offsets near year 1 compare without constructing a UTC date.
        self.assertEqual(group_capture_times([nearby, earliest], timedelta(hours=1)), ((1, 0),))

    def test_reject_invalid_window_before_container_or_elements(self):
        for window in [None, 3, True, "private /photos/secret.heic"]:
            self.assert_rejected(None, TypeError, "window must be a timedelta", window=window)
        self.assert_rejected([], ValueError, "window must be nonnegative", window=-timedelta(microseconds=1))
        self.assert_rejected(None, ValueError, "window must be nonnegative", window=timedelta.min)

    def test_reject_outer_nonsequences_and_invalid_values(self):
        for captures in [None, iter([self.anchor]), {self.anchor}, {0: self.anchor}]:
            self.assert_rejected(captures, TypeError, "capture_times must be a sequence")
        for captures in [[None], [True], ["private /photos/secret.heic"], "secret", b"secret"]:
            self.assert_rejected(captures, TypeError, "capture times must be datetime values")

    def test_timezone_rejections_and_input_order_precedence(self):
        naive = self.anchor.replace(tzinfo=None)
        custom = self.anchor.replace(tzinfo=CustomZone())
        self.assert_rejected([naive, None], ValueError, "capture times must be timezone-aware")
        self.assert_rejected([None, naive], TypeError, "capture times must be datetime values")
        self.assert_rejected([custom, naive], TypeError, "capture times must use a fixed-offset timezone")

    def test_sanitized_errors_and_no_output(self):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            self.assert_rejected(["private /photos/secret.heic"], TypeError,
                                 "capture times must be datetime values")
            self.assertEqual(group_capture_times(self.captures(0, 2, 4)), ((0, 1), (2,)))
        self.assertEqual((output.getvalue(), errors.getvalue()), ("", ""))


if __name__ == "__main__":
    unittest.main()
