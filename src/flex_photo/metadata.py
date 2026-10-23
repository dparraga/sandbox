"""Read original-capture text without selecting or normalizing a timestamp."""

from dataclasses import dataclass
import os
from pathlib import Path
import stat
from typing import BinaryIO

import exifread


_MAX_READ_BYTES = 1024 * 1024
_MAX_TOTAL_BYTES = 64 * 1024 * 1024
_MAX_OPERATIONS = 100_000


@dataclass(frozen=True)
class CaptureMetadata:
    date_time_original: str | None
    offset_time_original: str | None
    subsec_time_original: str | None


class MetadataError(Exception):
    """Safe public diagnostic with private context retained separately."""

    def __init__(self, path: Path, cause: Exception | None, reason: str):
        self.path = path
        self.cause = cause
        self.reason = reason
        super().__init__(reason)


class _LimitExceeded(Exception):
    pass


class _BoundedStream:
    """Expose only the parser's required, bounded binary stream operations."""

    def __init__(self, stream: BinaryIO, size: int):
        self._stream = stream
        self._size = size
        self._position = 0
        self._total_bytes = 0
        self._operations = 0
        self.failed = False

    def _fail(self) -> None:
        self.failed = True
        raise _LimitExceeded

    def _operation(self) -> None:
        self._operations += 1
        if self.failed or self._operations > _MAX_OPERATIONS:
            self._fail()

    def read(self, size: int = -1) -> bytes:
        self._operation()
        if size < 0 or size > _MAX_READ_BYTES:
            self._fail()
        possible = min(size, self._size - self._position)
        if self._total_bytes + possible > _MAX_TOTAL_BYTES:
            self._fail()
        data = self._stream.read(size)
        self._position += len(data)
        self._total_bytes += len(data)
        if self._total_bytes > _MAX_TOTAL_BYTES:
            self._fail()
        return data

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        self._operation()
        if whence == os.SEEK_SET:
            target = offset
        elif whence == os.SEEK_CUR:
            target = self._position + offset
        elif whence == os.SEEK_END:
            target = self._size + offset
        else:
            self._fail()
        if target < 0 or target > self._size:
            self._fail()
        self._position = self._stream.seek(target)
        return self._position

    def tell(self) -> int:
        self._operation()
        return self._position


def _regular(info: os.stat_result) -> bool:
    return stat.S_ISREG(info.st_mode) and not (
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def read_capture_metadata(path: Path) -> CaptureMetadata:
    """Extract three original-capture values from one stable local candidate."""
    stream = None
    guard = None
    try:
        before = path.lstat()
        checked = path.lstat()
        if not _regular(before) or not _regular(checked) or not os.path.samestat(before, checked):
            raise MetadataError(path, None, "file unavailable")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            stream = os.fdopen(descriptor, "rb")
        except Exception:
            os.close(descriptor)
            raise
        with stream:
            opened = os.fstat(stream.fileno())
            if not _regular(opened) or not os.path.samestat(checked, opened):
                raise MetadataError(path, None, "file unavailable")
            guard = _BoundedStream(stream, opened.st_size)
            logger = exifread.logger
            disabled = logger.disabled
            logger.disabled = True
            try:
                tags = exifread.process_file(
                    guard, details=False, extract_thumbnail=False, debug=False,
                    strict=True, truncate_tags=False,
                )
            finally:
                logger.disabled = disabled
            if guard.failed:
                raise _LimitExceeded
            values = []
            for name in ("DateTimeOriginal", "OffsetTimeOriginal", "SubSecTimeOriginal"):
                tag = tags.get(f"EXIF {name}")
                value = None if tag is None else tag.values
                if tag is not None and not isinstance(value, str):
                    raise MetadataError(path, None, "timestamp tag is not text")
                values.append(value)
            after = path.lstat()
            if not _regular(after) or not os.path.samestat(opened, after):
                raise MetadataError(path, None, "file unavailable")
        return CaptureMetadata(*values)
    except Exception as cause:
        if guard is not None and guard.failed:
            raise MetadataError(path, cause, "metadata limit exceeded") from None
        if isinstance(cause, MetadataError):
            raise
        reason = "file unavailable" if isinstance(cause, (OSError, ValueError)) and stream is None else "metadata parsing failed"
        if isinstance(cause, OSError):
            reason = "file unavailable"
        raise MetadataError(path, cause, reason) from None
