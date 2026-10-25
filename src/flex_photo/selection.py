"""Select the latest clearly readable candidates for one trip field."""

from collections.abc import Sequence
from datetime import datetime, timezone


def latest_clear_indices(
    capture_times: Sequence[datetime],
    clear_flags: Sequence[bool],
) -> tuple[int, ...]:
    """Return every latest clear candidate's original index, preserving ties.

    The caller establishes clarity independently for each field. Candidate
    order preserves observation identity and does not choose a tie winner.
    """
    if not isinstance(capture_times, Sequence):
        raise TypeError("capture_times must be a sequence")
    if not isinstance(clear_flags, Sequence):
        raise TypeError("clear_flags must be a sequence")
    if len(capture_times) != len(clear_flags):
        raise ValueError("capture_times and clear_flags must have equal lengths")
    for capture in capture_times:
        if not isinstance(capture, datetime):
            raise TypeError("capture times must be datetime values")
        if capture.tzinfo is None:
            raise ValueError("capture times must be timezone-aware")
        if not isinstance(capture.tzinfo, timezone):
            raise TypeError("capture times must use a fixed-offset timezone")
    for clear in clear_flags:
        if type(clear) is not bool:
            raise TypeError("clear flags must be bool values")

    latest: datetime | None = None
    candidates: list[int] = []
    for index, capture in enumerate(capture_times):
        if not clear_flags[index]:
            continue
        if latest is None or capture > latest:
            latest = capture
            candidates = [index]
        elif capture == latest:
            candidates.append(index)
    return tuple(candidates)
