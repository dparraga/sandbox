"""Contract checks for independent latest-clear field candidates."""

from collections.abc import Sequence
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone, tzinfo
import io
import struct
import unittest
from zoneinfo import ZoneInfo

from flex_photo.selection import latest_clear_indices


class Captures(Sequence):
    def __init__(self, items):
        self.items = tuple(items)

    def __len__(self):
        return len(self.items)

    def __getitem__(self, index):
        return self.items[index]


class CustomZone(tzinfo):
    def utcoffset(self, value):
        raise AssertionError("unsupported timezone must not be evaluated")


class SelectionTests(unittest.TestCase):
    anchor = datetime(2030, 2, 3, tzinfo=timezone.utc)

    def captures(self, *minutes):
        return [self.anchor + timedelta(minutes=value) for value in minutes]

    def assert_rejected(self, captures, flags, error_type, message):
        with self.assertRaises(error_type) as caught:
            latest_clear_indices(captures, flags)
        self.assertEqual(str(caught.exception), message)

    def test_empty_singleton_and_finite_sequences(self):
        self.assertEqual(latest_clear_indices([], ()), ())
        self.assertEqual(latest_clear_indices((self.anchor,), [True]), (0,))
        self.assertEqual(latest_clear_indices([self.anchor], (False,)), ())
        self.assertEqual(latest_clear_indices(Captures(self.captures(2, 0, 1)),
                                              Captures([True, True, True])), (0,))

    def test_latest_clear_ignores_newer_false_and_supports_unsorted_input(self):
        captures = self.captures(0, 1, 2)
        for flags, expected in [((True, False, False), (0,)),
                                ((False, True, True), (2,)),
                                ((False, False, False), ())]:
            with self.subTest(flags=flags):
                self.assertEqual(latest_clear_indices(captures, flags), expected)
        self.assertEqual(latest_clear_indices(self.captures(2, 0, 3, 1),
                                              (True, True, False, True)), (0,))

    def test_independent_fields_keep_zero_and_original_objects(self):
        captures = self.captures(0, 2, 1)
        distance_flags, range_flags = [True, False, False], [False, True, True]
        values = [0, None, None]
        before = captures.copy(), distance_flags.copy(), range_flags.copy()
        selected = latest_clear_indices(captures, distance_flags)
        self.assertEqual(tuple(values[index] for index in selected), (0,))
        self.assertEqual(latest_clear_indices(captures, range_flags), (1,))
        self.assertEqual((captures, distance_flags, range_flags), before)
        self.assertTrue(all(actual is original for actual, original in zip(captures, before[0])))

    def test_latest_ties_preserve_order_without_resolving_values(self):
        captures = self.captures(2, 0, 2, 0, 3)
        result = latest_clear_indices(captures, [True, True, True, True, False])
        self.assertIsInstance(result, tuple)
        self.assertEqual(result, (0, 2))
        values = ["conflicting first", None, "conflicting second", None, None]
        self.assertEqual(tuple(values[index] for index in result),
                         ("conflicting first", "conflicting second"))
        self.assertEqual(latest_clear_indices(captures, [True] * 5), (4,))

    def test_equal_instants_across_offsets_and_wall_clock_reversal(self):
        captures = [self.anchor.astimezone(timezone(timedelta(hours=3))),
                    self.anchor, self.anchor.astimezone(timezone(timedelta(hours=-4)))]
        self.assertEqual(latest_clear_indices(captures, [True] * 3), (0, 1, 2))
        self.assertEqual([capture.utcoffset() for capture in captures],
                         [timedelta(hours=3), timedelta(0), timedelta(hours=-4)])
        captures = [datetime(2030, 2, 3, 12, tzinfo=timezone(timedelta(hours=-4))),
                    datetime(2030, 2, 3, 13, tzinfo=timezone(timedelta(hours=3)))]
        self.assertEqual(latest_clear_indices(captures, [True, True]), (0,))

    def test_microseconds_and_calendar_boundaries(self):
        for anchor in [datetime(2030, 2, 3, 23, 59, tzinfo=timezone.utc),
                       datetime(2030, 2, 28, 23, 59, tzinfo=timezone.utc),
                       datetime(2030, 12, 31, 23, 59, tzinfo=timezone.utc)]:
            with self.subTest(anchor=anchor):
                captures = [anchor + timedelta(minutes=1), anchor,
                            anchor + timedelta(minutes=1, microseconds=1)]
                self.assertEqual(latest_clear_indices(captures, [True] * 3), (2,))

    def test_converter_extremes_and_equivalent_offset_ties(self):
        positive = timezone(timedelta(hours=23, minutes=59))
        negative = timezone(-timedelta(hours=23, minutes=59))
        earliest = datetime.min.replace(tzinfo=positive)
        latest = datetime.max.replace(tzinfo=negative)
        for captures, expected in [([latest, earliest], (0,)),
                                   ([earliest, earliest + timedelta(microseconds=1)], (1,)),
                                   ([latest - timedelta(microseconds=1), latest], (1,)),
                                   ([earliest, datetime(1, 1, 1, 0, 1,
                                                       tzinfo=timezone(timedelta(hours=23)))], (1,))]:
            with self.subTest(captures=captures):
                self.assertEqual(latest_clear_indices(captures, [True, True]), expected)
        # Equivalent instants whose UTC representation would lie outside datetime's range.
        low_tie = datetime(1, 1, 1, 0, 1, tzinfo=positive)
        low_other = datetime.min.replace(tzinfo=timezone(timedelta(hours=23, minutes=58)))
        high_tie = datetime.max.replace(tzinfo=timezone(-timedelta(hours=23, minutes=58)))
        high_other = latest - timedelta(minutes=1)
        for captures in [[low_tie, low_other], [high_tie, high_other]]:
            self.assertEqual(latest_clear_indices(captures, [True, True]), (0, 1))

    def test_outer_containers_then_lengths_before_elements(self):
        for captures in [None, iter([self.anchor]), {self.anchor}, {0: self.anchor}]:
            self.assert_rejected(captures, None, TypeError, "capture_times must be a sequence")
        for flags in [None, iter([True]), {True}, {0: True}]:
            self.assert_rejected([None], flags, TypeError, "clear_flags must be a sequence")
        self.assert_rejected([None], [], ValueError, "capture_times and clear_flags must have equal lengths")
        self.assert_rejected([], [None], ValueError, "capture_times and clear_flags must have equal lengths")

    def test_timestamp_validation_in_order_before_all_flags(self):
        naive = self.anchor.replace(tzinfo=None)
        custom = self.anchor.replace(tzinfo=CustomZone())
        for captures, kind, message in [([naive, None], ValueError, "capture times must be timezone-aware"),
                                        ([None, naive], TypeError, "capture times must be datetime values"),
                                        ([custom, naive], TypeError, "capture times must use a fixed-offset timezone")]:
            self.assert_rejected(captures, [None, None], kind, message)
        for value in [None, True, 1, "private /photos/secret.heic"]:
            self.assert_rejected([self.anchor, value], [None, False], TypeError,
                                 "capture times must be datetime values")
        self.assert_rejected("x", [True], TypeError, "capture times must be datetime values")
        self.assert_rejected(b"x", [True], TypeError, "capture times must be datetime values")

    def test_zoneinfo_timezone_is_rejected_without_system_zone_database(self):
        # Authored TZif v1 with one UTC rule; even a fixed ZoneInfo is unsupported.
        header = b"TZif\0" + bytes(15) + struct.pack(">6I", 0, 0, 0, 0, 1, 4)
        zone = ZoneInfo.from_file(io.BytesIO(header + struct.pack(">lbb", 0, 0, 0) + b"UTC\0"))
        self.assert_rejected([self.anchor.replace(tzinfo=zone)], [True], TypeError,
                             "capture times must use a fixed-offset timezone")

    def test_flags_require_actual_bools_even_when_ineligible(self):
        for value in [None, 0, 1, "", "private /photos/secret.heic", object(), [], b"x"]:
            self.assert_rejected(self.captures(0, 1), [False, value], TypeError,
                                 "clear flags must be bool values")
        self.assert_rejected([self.anchor], "x", TypeError, "clear flags must be bool values")
        self.assert_rejected([self.anchor], b"x", TypeError, "clear flags must be bool values")

    def test_fixed_diagnostics_no_output_or_mutation_on_invalid_call(self):
        captures, flags = [self.anchor, "private /photos/secret.heic"], [True, False]
        before = captures.copy(), flags.copy()
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            self.assert_rejected(captures, flags, TypeError, "capture times must be datetime values")
            self.assertEqual(latest_clear_indices([self.anchor], [True]), (0,))
        self.assertEqual((output.getvalue(), errors.getvalue()), ("", ""))
        self.assertEqual((captures, flags), before)


if __name__ == "__main__":
    unittest.main()
