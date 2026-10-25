"""Convert original-capture text to a fixed-offset aware datetime."""

from datetime import datetime, timedelta, timezone

from flex_photo.metadata import CaptureMetadata


class CaptureTimeError(Exception):
    """Sanitized component error without original metadata or parser details."""

    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        super().__init__(f"{field}: {reason}")


def _ascii_digits(value: str) -> bool:
    return value.isascii() and value.isdecimal()


def parse_capture_time(metadata: CaptureMetadata) -> datetime:
    """Parse only original fields, preserving local time and an explicit offset."""
    field = "date_time_original"
    date = metadata.date_time_original
    if date is None:
        raise CaptureTimeError(field, "missing")
    if (not isinstance(date, str) or len(date) != 19
            or date[4] != ":" or date[7] != ":" or date[10] != " "
            or date[13] != ":" or date[16] != ":"
            or not _ascii_digits(date[:4] + date[5:7] + date[8:10]
                                 + date[11:13] + date[14:16] + date[17:19])):
        raise CaptureTimeError(field, "invalid")
    try:
        result = datetime(int(date[:4]), int(date[5:7]), int(date[8:10]),
                          int(date[11:13]), int(date[14:16]), int(date[17:19]))
    except ValueError:
        raise CaptureTimeError(field, "invalid") from None

    field = "offset_time_original"
    offset = metadata.offset_time_original
    if offset is None:
        raise CaptureTimeError(field, "missing")
    if (not isinstance(offset, str) or len(offset) != 6 or offset[0] not in "+-"
            or offset[3] != ":" or not _ascii_digits(offset[1:3] + offset[4:6])):
        raise CaptureTimeError(field, "invalid")
    hours, minutes = int(offset[1:3]), int(offset[4:6])
    if hours > 23 or minutes > 59:
        raise CaptureTimeError(field, "invalid")
    delta = timedelta(hours=hours, minutes=minutes)
    if offset[0] == "-":
        delta = -delta

    field = "subsec_time_original"
    fraction = metadata.subsec_time_original
    microsecond = 0
    if fraction is not None:
        if not isinstance(fraction, str):
            raise CaptureTimeError(field, "invalid")
        if len(fraction) > 6:
            raise CaptureTimeError(field, "unsupported precision")
        if not _ascii_digits(fraction):
            raise CaptureTimeError(field, "invalid")
        microsecond = int(fraction.ljust(6, "0"))
    return result.replace(microsecond=microsecond, tzinfo=timezone(delta))
