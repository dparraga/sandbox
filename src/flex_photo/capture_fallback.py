"""Resolve authorized capture-time fallbacks without changing strict EXIF parsing."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib.resources import files
import math
from pathlib import Path
import re
import stat
from zoneinfo import ZoneInfo

from .capture_time import _parse_fraction, _parse_offset, parse_capture_time
from .discovery import _is_link_or_reparse

TZDATA_VERSION = "2026.6"
CAPTURE_POLICY = "v1/America/Los_Angeles/tzdata-" + TZDATA_VERSION
_FILENAME = re.compile(r"^([0-9]{4})([0-9]{2})([0-9]{2})_([0-9]{2})([0-9]{2})([0-9]{2})([0-9]{3})(?:_|$)")


class CaptureFallbackError(Exception):
    def __init__(self, reason, *, silent=False):
        self.silent = silent
        super().__init__(reason)


@dataclass(frozen=True)
class CaptureResolution:
    capture: datetime
    spelling: str
    source: str
    inputs: dict | None = None


@lru_cache(maxsize=1)
def _la_zone():
    # Use the pinned package even when the host has a different IANA database.
    try:
        import tzdata
        if tzdata.__version__ != TZDATA_VERSION:
            raise CaptureFallbackError("pinned fallback timezone data version unavailable")
        with files("tzdata.zoneinfo").joinpath("America", "Los_Angeles").open("rb") as stream:
            return ZoneInfo.from_file(stream, key="America/Los_Angeles")
    except (ImportError, OSError, ValueError) as error:
        raise CaptureFallbackError("pinned fallback timezone data unavailable") from error


def capture_inputs(path: Path) -> dict:
    """Read true birth time, never modification time or Unix metadata-change time."""
    info = path.lstat()
    if _is_link_or_reparse(info) or not stat.S_ISREG(info.st_mode):
        raise CaptureFallbackError("capture source is not an ordinary file")
    birth = getattr(info, "st_birthtime_ns", None)
    if type(birth) is not int:
        seconds = getattr(info, "st_birthtime", None)
        birth = (round(seconds * 1_000_000_000)
                 if not isinstance(seconds, bool) and isinstance(seconds, (int, float))
                 and math.isfinite(seconds) else None)
    return {"creation_time_ns": birth, "filename": path.name, "policy": CAPTURE_POLICY}


def validate_capture_inputs(path: Path, value: dict) -> None:
    if (not isinstance(value, dict) or set(value) != {"creation_time_ns", "filename", "policy"}
            or value["filename"] != path.name or value["policy"] != CAPTURE_POLICY
            or value["creation_time_ns"] is not None and type(value["creation_time_ns"]) is not int):
        raise CaptureFallbackError("saved capture fallback inputs are incompatible")


def capture_inputs_match(path: Path, expected: dict) -> bool:
    try:
        validate_capture_inputs(path, expected)
        return capture_inputs(path) == expected
    except (OSError, CaptureFallbackError):
        return False


def _fixed_offset(value: datetime) -> datetime:
    offset = value.utcoffset()
    if offset is None or offset % timedelta(minutes=1):
        raise CaptureFallbackError("fallback timezone offset is outside the supported minute precision")
    result = value.replace(tzinfo=timezone(offset), fold=0)
    result.astimezone(timezone.utc)
    return result


def _filename_capture(path: Path) -> datetime:
    stem = path.stem
    if re.fullmatch(r"[0-9]{8}", stem):
        raise CaptureFallbackError("date-only filename has no grouping time", silent=True)
    match = _FILENAME.match(stem)
    if match is None:
        raise CaptureFallbackError("filename has no YYYYMMDD_HHMMSSfff timestamp")
    try:
        year, month, day, hour, minute, second, millisecond = map(int, match.groups())
        local = datetime(year, month, day, hour, minute, second, millisecond * 1000)
        zone = _la_zone()
        candidates = {}
        for fold in (0, 1):
            value = local.replace(tzinfo=zone, fold=fold)
            if value.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == local:
                candidates[value.utcoffset()] = value
    except (ValueError, OverflowError) as error:
        raise CaptureFallbackError("filename timestamp is invalid or outside the supported range") from error
    if not candidates:
        raise CaptureFallbackError("filename local time does not exist in America/Los_Angeles")
    if len(candidates) != 1:
        raise CaptureFallbackError("filename local time is ambiguous in America/Los_Angeles")
    return _fixed_offset(next(iter(candidates.values())))


def resolve_capture(path: Path, metadata, *, inputs=None) -> CaptureResolution:
    """Prefer present EXIF dates; missing dates use birth time, then filename.

    Present but invalid EXIF values keep the existing strict error contract.
    Fallback creation instants are represented at the grouping API's microsecond
    precision; filename milliseconds retain their three supplied digits.
    """
    if metadata is not None and metadata.date_time_original is not None:
        capture = parse_capture_time(metadata)
        capture.astimezone(timezone.utc)
        text = metadata.date_time_original
        spelling = text[:4] + "-" + text[5:7] + "-" + text[8:10] + "T" + text[11:]
        if metadata.subsec_time_original is not None:
            spelling += "." + metadata.subsec_time_original
        return CaptureResolution(capture, spelling + metadata.offset_time_original, "metadata")
    # Missing date authorizes fallback; malformed surviving EXIF fields do not.
    if metadata is not None:
        if metadata.offset_time_original is not None:
            _parse_offset(metadata.offset_time_original)
        if metadata.subsec_time_original is not None:
            _parse_fraction(metadata.subsec_time_original)
    context = capture_inputs(path) if inputs is None else inputs
    validate_capture_inputs(path, context)
    birth = context["creation_time_ns"]
    if birth is not None:
        try:
            utc = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=birth // 1000)
            capture = _fixed_offset(utc.astimezone(_la_zone()))
        except (ValueError, OverflowError, CaptureFallbackError):
            pass  # An unrepresentable creation timestamp cannot outrank a valid filename.
        else:
            precision = "microseconds" if capture.microsecond else "seconds"
            return CaptureResolution(capture, capture.isoformat(timespec=precision), "file_creation", dict(context))
    capture = _filename_capture(path)
    return CaptureResolution(capture, capture.isoformat(timespec="milliseconds"), "filename", dict(context))
