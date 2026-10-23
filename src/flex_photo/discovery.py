"""Read-only discovery of HEIC filename candidates in stable local trees."""

import os
from pathlib import Path
import stat


class DiscoveryError(Exception):
    """A failed discovery operation, retaining its original filesystem cause."""

    def __init__(
        self,
        category: str,
        path: Path,
        cause: OSError | ValueError | None = None,
        *,
        reason: str,
    ) -> None:
        self.category = category
        self.path = path
        self.cause = cause
        self.reason = reason
        super().__init__(f"{category}: {reason}")


def _is_link_or_reparse(metadata: os.stat_result) -> bool:
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0)
        & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def _check_directory(path: Path, *, initial: bool) -> None:
    category = "invalid-source" if initial else "scan-failed"
    try:
        metadata = path.lstat()
    except (OSError, ValueError) as cause:
        raise DiscoveryError(
            category, path, cause, reason="directory metadata unavailable"
        ) from cause
    if _is_link_or_reparse(metadata):
        raise DiscoveryError(category, path, reason="directory is a link or reparse point")
    if not stat.S_ISDIR(metadata.st_mode):
        raise DiscoveryError(category, path, reason="not an ordinary directory")


def discover_heic(source: Path) -> tuple[Path, ...]:
    """Return sorted relative regular-file paths with a final .heic suffix.

    The selected root cannot be a link/reparse point. Such entries encountered
    below it are skipped. No file contents are opened; this is neither image
    validation nor an atomic snapshot or hostile-tree containment boundary.
    """
    # abspath normalizes the lexical path without resolving a linked root.
    try:
        root = Path(os.path.abspath(source))
    except (OSError, ValueError) as cause:
        raise DiscoveryError(
            "invalid-source", source, cause, reason="source path unavailable"
        ) from cause
    _check_directory(root, initial=True)
    pending = [root]
    candidates: list[Path] = []
    while pending:
        directory = pending.pop()
        # An ordinary directory queued earlier may since have been replaced.
        _check_directory(directory, initial=False)
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    path = directory / entry.name
                    try:
                        metadata = entry.stat(follow_symlinks=False)
                    except OSError as cause:
                        raise DiscoveryError(
                            "scan-failed", path, cause, reason="entry metadata unavailable"
                        ) from cause
                    if _is_link_or_reparse(metadata):
                        continue
                    if stat.S_ISDIR(metadata.st_mode):
                        pending.append(path)
                    elif stat.S_ISREG(metadata.st_mode) and path.suffix.lower() == ".heic":
                        candidates.append(path.relative_to(root))
        except OSError as cause:
            # Includes scandir construction, iteration and handle-close failures.
            raise DiscoveryError(
                "scan-failed", directory, cause, reason="directory enumeration failed"
            ) from cause
    return tuple(sorted(candidates, key=lambda path: path.as_posix()))
