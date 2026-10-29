"""Compact terminal progress and monotonic, resume-aware processing timing."""

import os
import sys
import threading
import time


def _duration(seconds):
    if seconds is None:
        return "Calculating..."
    seconds = max(0, round(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:d}:{minutes:02d}:{seconds:02d}"


class Progress:
    """Persist snapshots at safe boundaries; create a new instance on resume.

    Only ``record_photo`` adds measured work to throughput. Merely restoring or
    reusing results changes evaluated counts without inflating processing speed.
    The optional heartbeat keeps long native calls visible without per-photo logs.
    """

    def __init__(self, total=0, *, evaluated=0, active_seconds=0.,
                 processed_seconds=0., processed_count=0, stream=None,
                 clock=time.monotonic, enabled=True):
        self.enabled = enabled
        self.total = total
        self.evaluated = evaluated
        self.stage = "discovery"
        self.status = "running"
        self.processed_seconds = processed_seconds
        self.processed_count = processed_count
        self.finalization_remaining_seconds = None
        self._active_seconds = active_seconds
        self._clock = clock
        self._started = clock()
        self._closed = False
        self._stream = sys.stderr if stream is None else stream
        try:
            self._refresh = bool(self._stream.isatty() and os.environ.get("TERM") != "dumb")
        except (OSError, ValueError):
            self._refresh = False
        self._interval = 1. if self._refresh else 30.
        self._last_render = None
        self._line_width = 0
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None

    def snapshot(self):
        with self._lock:
            active = self._active_seconds
            if not self._closed:
                active += max(0., self._clock() - self._started)
            remaining = max(0, self.total - self.evaluated)
            average = (self.processed_seconds / self.processed_count
                       if self.processed_count else None)
            eta = average * remaining if average is not None and remaining else None
            if self.finalization_remaining_seconds is not None:
                eta = ((eta or 0.) + self.finalization_remaining_seconds
                       if not remaining or eta is not None else None)
            if self.status == "completed":
                eta = 0.
            return {"total": self.total, "evaluated": self.evaluated,
                    "remaining": remaining,
                    "percent": (min(100., self.evaluated * 100. / self.total)
                                if self.total else 0.),
                    "active_seconds": active,
                    "processed_seconds": self.processed_seconds,
                    "processed_count": self.processed_count,
                    "average_seconds": average, "eta_seconds": eta,
                    "finalization_remaining_seconds": self.finalization_remaining_seconds,
                    "stage": self.stage, "status": self.status}

    def update(self, *, total=None, evaluated=None, stage=None, status=None,
               finalization_remaining_seconds=None):
        with self._lock:
            for name, value in (("total", total), ("evaluated", evaluated),
                                ("stage", stage), ("status", status),
                                ("finalization_remaining_seconds", finalization_remaining_seconds)):
                if value is not None:
                    setattr(self, name, value)
            self.render()

    def record_photo(self, seconds, *, evaluated=None):
        with self._lock:
            self.processed_seconds += max(0., seconds)
            self.processed_count += 1
            self.evaluated = self.evaluated + 1 if evaluated is None else evaluated
            self.render()

    def render(self, *, force=False):
        if not self.enabled:
            return
        with self._lock:
            now = self._clock()
            if not force and self._last_render is not None and now - self._last_render < self._interval:
                return
            value = self.snapshot()
            eta = _duration(value["eta_seconds"])
            if (value["eta_seconds"] is not None and value["remaining"]
                    and value["finalization_remaining_seconds"] is None):
                eta += " + finalization"
            line = (f"{value['status']} | {value['stage']} | "
                    f"{value['evaluated']}/{value['total']} evaluated, "
                    f"{value['remaining']} remaining ({value['percent']:.1f}%) | "
                    f"avg {_duration(value['average_seconds'])}/photo | "
                    f"active {_duration(value['active_seconds'])} | ETA {eta}")
            try:
                if self._refresh:
                    self._stream.write("\r" + line.ljust(self._line_width))
                    self._line_width = len(line)
                else:
                    self._stream.write(line + "\n")
                self._stream.flush()
            except (OSError, UnicodeError, ValueError):
                # A closed display must not interrupt safe persistence or moves.
                self._stop.set()
            self._last_render = now

    def start(self):
        with self._lock:
            if self._thread is not None or self._closed:
                return self
            self.render(force=True)

            def heartbeat():
                while not self._stop.wait(self._interval):
                    self.render()

            self._thread = threading.Thread(target=heartbeat, daemon=True,
                                            name="flex-photo-progress")
            self._thread.start()
            return self

    def close(self, status=None):
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=2.)
        with self._lock:
            if self._closed:
                return
            self._active_seconds += max(0., self._clock() - self._started)
            self._closed = True
            if status is not None:
                self.status = status
            self.render(force=True)
            if self._refresh:
                try:
                    self._stream.write("\n")
                    self._stream.flush()
                except (OSError, UnicodeError, ValueError):
                    pass

    def __enter__(self):
        return self.start()

    def __exit__(self, *_):
        self.close()
