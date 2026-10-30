"""Opt-in, size-bounded representative stack diagnostics; reports own counts."""

import os
from pathlib import Path
import re
import stat
import sys

from .discovery import _is_link_or_reparse

_LIMIT = 64 * 1024


class Diagnostics:
    def __init__(self, output: Path, enabled: bool = False):
        self.output = output
        self.enabled = enabled
        self.seen = set()
        self.warned = False

    def _check(self, path: Path, *, directory=False):
        try:
            info = path.lstat()
        except FileNotFoundError:
            if directory:
                raise
            return
        if _is_link_or_reparse(info) or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
            raise OSError("unsupported diagnostic item")
        if not directory and info.st_size > _LIMIT:
            raise OSError("existing diagnostic exceeds size limit")

    def record(self, category: str, trace: str | None):
        if not self.enabled or not trace:
            return
        category = category if re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", category) else "processing"
        if category in self.seen:
            return
        self.seen.add(category)
        try:
            self._check(self.output, directory=True)
            path = self.output / ".flex-photo-diagnostic.log"
            previous = self.output / ".flex-photo-diagnostic.log.1"
            self._check(path)
            self._check(previous)
            # JSON encoding keeps one record per line and prevents terminal escapes.
            import json
            data = (json.dumps({"category": category, "stack": trace[:8192]}, ensure_ascii=True) + "\n").encode("ascii")
            if path.exists() and path.stat().st_size + len(data) > _LIMIT:
                os.replace(path, previous)
            with path.open("ab") as stream:
                stream.write(data)
        except (OSError, ValueError) as error:
            if not self.warned:
                print("diagnostic-failed: " + type(error).__name__ +
                      " (errno=" + str(getattr(error, "errno", None)) + ")", file=sys.stderr)
                self.warned = True
