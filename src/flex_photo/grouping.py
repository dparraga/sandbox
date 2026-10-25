"""Group qualified photo capture times within a bounded trip window."""

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone


def group_capture_times(
    capture_times: Sequence[datetime],
    window: timedelta = timedelta(minutes=3),
) -> tuple[tuple[int, ...], ...]:
    """Return original indices grouped from each earliest unassigned instant.

    Equal instants retain input order. Each group's first-to-last elapsed time
    is at most ``window``; consecutive gaps cannot extend that bound.
    """
    if not isinstance(window, timedelta):
        raise TypeError("window must be a timedelta")
    if window < timedelta(0):
        raise ValueError("window must be nonnegative")
    if not isinstance(capture_times, Sequence):
        raise TypeError("capture_times must be a sequence")
    for capture in capture_times:
        if not isinstance(capture, datetime):
            raise TypeError("capture times must be datetime values")
        if capture.tzinfo is None:
            raise ValueError("capture times must be timezone-aware")
        if not isinstance(capture.tzinfo, timezone):
            raise TypeError("capture times must use a fixed-offset timezone")

    indices = sorted(range(len(capture_times)), key=capture_times.__getitem__)
    groups: list[tuple[int, ...]] = []
    current: list[int] = []
    for index in indices:
        if current and capture_times[index] - capture_times[current[0]] > window:
            groups.append(tuple(current))
            current = []
        current.append(index)
    if current:
        groups.append(tuple(current))
    return tuple(groups)
