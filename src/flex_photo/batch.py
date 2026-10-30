"""Offline batch composition and hash-verified, recoverable local effects."""

from contextlib import contextmanager, ExitStack
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
import signal
import threading
import uuid

from .capture_time import CaptureTimeError, parse_capture_time
from .capture_fallback import (CaptureFallbackError, capture_inputs, capture_inputs_match,
                               resolve_capture, validate_capture_inputs)
from .discovery import DiscoveryError, discover_heic, _is_link_or_reparse
from .grouping import group_capture_times
from .interpretation import (InterpretationAssets, SharedAssetError, interpret_photo,
                             validate_interpretation_assets as _validate_assets)
from .selection import latest_clear_indices
from .metadata import CaptureMetadata
from .interpretation import PhotoInterpretation, FieldObservation, InterpretationIssue
from .checkpoint import Checkpoint, _sync_directory
from .progress import Progress
from .diagnostics import Diagnostics

_FIELDS = ("trip_distance", "trip_duration", "trip_average_mpg", "odometer")
_STATE = ".flex-photo-state.json"
_REWRITE = ".flex-photo-rewrite.json"


class BatchError(Exception):
    """A sanitized failure whose affected operation must remain untouched."""


class ClearConflict(BatchError):
    pass


class PublishedCleanupError(BatchError):
    """Publication succeeded; an owned sibling remains for cleanup."""

    def __init__(self, temporary):
        self.temporary = temporary
        super().__init__("verified output saved; temporary cleanup failed")


@dataclass(frozen=True)
class BatchResult:
    status: str
    report_path: Path | None
    counts: dict[str, int]

    @property
    def complete(self) -> bool:
        return self.status == "complete"

    def summary(self) -> dict:
        return {"status": self.status, "report_path": str(self.report_path) if self.report_path else None,
                "counts": self.counts}


def _json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sparse_entry(entry: dict) -> dict:
    """Canonical public schema 2; private recovery serialization is unchanged."""
    return {**entry, "fields": {field: {key: value for key, value in reading.items() if value is not None}
                               for field, reading in entry["fields"].items() if reading is not None}}


def _entry_version(entry: dict) -> int:
    return 1 if any(reading is None or isinstance(reading, dict) and reading.get("unit", "") is None
                    for reading in entry["fields"].values()) else 2


def _ordinary(path: Path, *, directory: bool = False) -> os.stat_result:
    info = path.lstat()
    if _is_link_or_reparse(info) or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise BatchError("unsupported link or filesystem item")
    return info


def _safe_path(path: Path, root: Path, *, missing: bool = False) -> None:
    if path != Path(os.path.abspath(path)) or root != Path(os.path.abspath(root)):
        raise BatchError("path is not normalized within selected folder")
    try:
        relative = path.relative_to(root)
    except ValueError:
        raise BatchError("path escapes selected folder") from None
    _ordinary(root, directory=True)
    current = root
    for part in relative.parts[:-1]:
        current /= part
        _ordinary(current, directory=True)
    if path != root and (path.exists() or path.is_symlink() or not missing):
        _ordinary(path)


def _hash_file(path: Path) -> str:
    _ordinary(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _actual_hash(path: Path) -> str | None:
    try:
        return _hash_file(path)
    except FileNotFoundError:
        return None


def _identity(path: Path) -> list[int]:
    info = _ordinary(path, directory=True)
    return [info.st_dev, info.st_ino]


def _roots(source, destination, output) -> tuple[Path, Path, Path]:
    paths = tuple(Path(os.path.abspath(value)) for value in (source, destination, output))
    for path in paths:
        # Resolve no links, including ancestors of a nonexistent requested folder.
        for ancestor in reversed((path, *path.parents)):
            if ancestor.exists() or ancestor.is_symlink():
                _ordinary(ancestor, directory=True)
    for index, path in enumerate(paths):
        for other in paths[index + 1:]:
            if path == other or path.is_relative_to(other) or other.is_relative_to(path):
                raise BatchError("source, destination and output must be separate nonnested folders")
    _ordinary(paths[0], directory=True)
    for path in paths[1:]:
        path.mkdir(parents=True, exist_ok=True)
        _ordinary(path, directory=True)
    return paths


def _check_roots(roots: dict) -> None:
    for value in roots.values():
        path = Path(value["path"])
        for ancestor in (path, *path.parents):
            _ordinary(ancestor, directory=True)
        if _identity(path) != value["identity"]:
            raise BatchError("selected folder identity changed")


def _atomic_write(path: Path, data: bytes, expected: str | None) -> None:
    """Flush a private sibling and replace only the expected ordinary target."""
    if _actual_hash(path) != expected:
        raise BatchError("output changed unexpectedly")
    temporary = path.with_name(".flex-write-" + uuid.uuid4().hex)
    published = False
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if _actual_hash(path) != expected:
            raise BatchError("output changed unexpectedly")
        if expected is None:
            # A hard link publishes without replacing a racing new file.
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
        published = True
        _sync_directory(path.parent)
    finally:
        deadline = time.monotonic() + 1
        while True:
            try:
                temporary.unlink()
                break
            except FileNotFoundError:
                break
            except OSError as error:
                if os.name == "nt" and getattr(error, "winerror", None) in (5, 32, 33) and time.monotonic() < deadline:
                    time.sleep(.02)
                    continue
                if published and _actual_hash(path) == _hash_bytes(data):
                    raise PublishedCleanupError(temporary.name) from error
                raise


@contextmanager
def _output_lock(output: Path):
    path = output / ".flex-photo.lock"
    _safe_path(path, output, missing=True)
    with path.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise BatchError("output is owned by another process") from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class _Report:
    def __init__(self, output: Path):
        run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex
        self.path = output / ("report-" + run + ".json")
        self.value = {"report_version": 1, "run_id": run, "status": "incomplete",
                      "counts": {"candidates": 0, "nonmatches": 0, "duplicates": 0,
                                 "repeats": 0, "skipped": 0, "moved": 0, "trips": 0}, "issues": []}
        self.expected = None
        self.saved = False
        self.finalized = False
        self.last_write = 0.0
        self.last_error = None
        self._issues = set()
        self.write()

    def write(self):
        try:
            aggregates = {}
            for issue in self.value["issues"]:
                key = (issue.get("stage", "processing"), issue["issue"])
                aggregates[key] = aggregates.get(key, 0) + 1
            self.value["issue_summary"] = [{"stage": stage, "issue": reason, "count": count}
                for (stage, reason), count in sorted(aggregates.items())]
            snapshot = dict(self.value)
            if snapshot["status"] == "complete" and not self.finalized:
                snapshot["status"] = "incomplete"
            data = _json_bytes(snapshot)
            try:
                _atomic_write(self.path, data, self.expected)
            except PublishedCleanupError as error:
                # Never leave a stale expected identity after verified publication.
                self.expected = _hash_bytes(data)
                self.saved = True
                self.issue(error.temporary, str(error), "preserve owned temporary; inspect filesystem", stage="report")
                raise
            if _actual_hash(self.path) != _hash_bytes(data):
                raise BatchError("run report verification failed")
            self.expected = _hash_bytes(data)
            self.saved = True
            self.last_write = time.monotonic()
        except (OSError, ValueError, TypeError, BatchError) as error:
            try:
                self.saved = bool('data' in locals() and _actual_hash(self.path) == _hash_bytes(data))
            except (OSError, BatchError):
                self.saved = False
            if self.saved:
                self.expected = _hash_bytes(data)
            if isinstance(error, OSError):
                reason = f"{type(error).__name__} (errno={error.errno}, winerror={getattr(error, 'winerror', None)})"
            elif isinstance(error, BatchError):
                reason = str(error)
            else:
                reason = type(error).__name__ + " during JSON serialization"
            if reason != self.last_error:
                print("report-failed: " + reason, file=sys.stderr)
                self.last_error = reason
            raise BatchError("run report unavailable") from None

    def issue(self, item, reason, action, *, incomplete=True, stage="processing"):
        key = (str(item), reason, action, stage)
        if key not in self._issues:
            self._issues.add(key)
            self.value["issues"].append({"item": str(item), "issue": reason, "action": action, "stage": stage})
        if incomplete:
            self.value["status"] = "incomplete"

    def flush_due(self):
        if time.monotonic() - self.last_write >= 30:
            self.write()


def _reading(observation, field):
    if observation is None or observation.status != "clear" or not isinstance(observation.value, str):
        return None
    value, unit = observation.value, observation.unit
    if field == "trip_duration":
        match = re.fullmatch(r"([0-9]+):([0-5][0-9])", value)
        if match is None or unit is not None:
            return None
        normalized = (match[1].lstrip("0") or "0").zfill(2) + ":" + match[2]
        return normalized, None, normalized
    if re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", value) is None:
        return None
    if unit != ("MPG" if field == "trip_average_mpg" else "mi"):
        return None
    return value, unit, Decimal(value)


def _resolve_trip(records: list[dict], report: _Report) -> tuple[str, dict]:
    captures = [item["capture"] for item in records]
    first, last = min(captures), max(captures)
    latest = [item for item in records if item["capture"] == last]
    months = {item["spelling"][:7] for item in latest}
    dates = {item["spelling"][:10] for item in latest}
    assignment = "latest_capture_local"
    if len(months) > 1:
        date = last.astimezone(timezone.utc).date().isoformat()
        assignment = "latest_instant_utc"
        report.issue(records[0]["path"], "latest captures have different local months", "use shared UTC date/month", incomplete=False)
    else:
        date = max(dates)
        if len(dates) > 1:
            report.issue(records[0]["path"], "latest captures have different local dates", "use greatest local date", incomplete=False)
    fields = {}
    for field in _FIELDS:
        parsed = []
        for item in records:
            observation = next((value for value in item["observations"] if value.field_id == field), None)
            value = _reading(observation, field)
            if observation is not None and observation.status == "clear" and value is None:
                report.issue(item["path"], "malformed " + field, "exclude observation; retain earlier valid candidate", incomplete=False)
            parsed.append(value)
        selected = latest_clear_indices(captures, [value is not None for value in parsed])
        if not selected:
            fields[field] = None
            report.issue(records[0]["path"], "no clear " + field + " in trip", "emit null", incomplete=False)
            continue
        tied = [parsed[index] for index in selected]
        if any((value[2], value[1]) != (tied[0][2], tied[0][1]) for value in tied[1:]):
            raise ClearConflict("conflicting equally latest clear " + field)
        chosen = min(tied, key=lambda value: value[0])
        fields[field] = {"value": chosen[0], "unit": chosen[1]}
    return date[:7], _sparse_entry({"trip_date": date, "first_capture_times": sorted({item["spelling"] for item in records if item["capture"] == first}),
                      "last_capture_times": sorted({item["spelling"] for item in records if item["capture"] == last}),
                      "month_assignment": assignment, "fields": fields})


def _eligible_trips(candidates: list[list[dict]], committed: list[dict], window: timedelta) -> set[int]:
    """Remove whole overlapping candidates until rejected captures shield none."""
    history = [(datetime.fromisoformat(capture), None) for trip in committed for capture in trip["captures"]]
    eligible = set(range(len(candidates)))
    while eligible:
        combined = history + [(item["capture"], index) for index in sorted(eligible) for item in candidates[index]]
        rejected = set()
        for group in group_capture_times([value[0] for value in combined], window):
            owners = {combined[index][1] for index in group}
            if None in owners:
                rejected.update(owners - {None})
        if not rejected:
            break
        eligible -= rejected
    return eligible


def _capture_text(text: str) -> datetime:
    match = re.fullmatch(r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}:[0-9]{2}:[0-9]{2})(?:\.([0-9]{1,6}))?([+-][0-9]{2}:[0-9]{2})", text)
    if match is None:
        raise ValueError("invalid capture representation")
    parsed = parse_capture_time(CaptureMetadata(":".join(match.group(1, 2, 3)) + " " + match[4], match[6], match[5]))
    parsed.astimezone(timezone.utc)
    return parsed


def _validate_entry(entry: dict, month: str, captures: list[str], *, schema_version=None) -> None:
    """Check only the approved public trip contract and its saved membership."""
    if not isinstance(entry, dict) or set(entry) != {"trip_date", "first_capture_times", "last_capture_times", "month_assignment", "fields"}:
        raise ValueError("unknown trip fields")
    if not isinstance(entry["fields"], dict) or not set(entry["fields"]) <= set(_FIELDS):
        raise ValueError("unknown dashboard fields")
    version = _entry_version(entry) if schema_version is None else schema_version
    if version == 1 and set(entry["fields"]) != set(_FIELDS):
        raise ValueError("legacy dashboard fields are incomplete")
    for field, value in entry["fields"].items():
        if value is None:
            if version == 2:
                raise ValueError("schema 2 omits unavailable readings")
            continue
        keys = {"value"} if version == 2 and field == "trip_duration" else {"value", "unit"}
        if not isinstance(value, dict) or set(value) != keys or not isinstance(value["value"], str):
            raise ValueError("invalid reading")
        if field == "trip_duration":
            if value.get("unit") is not None or re.fullmatch(r"[0-9]{2,}:[0-5][0-9]", value["value"]) is None:
                raise ValueError("invalid duration")
        elif value["unit"] != ("MPG" if field == "trip_average_mpg" else "mi") or re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", value["value"]) is None:
            raise ValueError("invalid decimal or literal unit")
    parsed = [_capture_text(text) for text in captures]
    if not parsed or parsed != sorted(parsed):
        raise ValueError("invalid capture ordering")
    bounds = []
    for name, instant in (("first_capture_times", parsed[0]), ("last_capture_times", parsed[-1])):
        texts = entry[name]
        if not isinstance(texts, list) or not texts or texts != sorted(set(texts)):
            raise ValueError("invalid capture bound array")
        values = [_capture_text(text) for text in texts]
        if any(value != instant for value in values):
            raise ValueError("capture bounds disagree with membership")
        # Offset/local spelling has meaning even when instants are equal.
        signature = lambda value: (value.replace(tzinfo=None), value.utcoffset())
        if {signature(value) for value in values} != {signature(value) for value in parsed if value == instant}:
            raise ValueError("capture bound offsets disagree with membership")
        if len(texts) > sum(value == instant for value in parsed):
            raise ValueError("capture bound count exceeds membership")
        bounds.append(values)
    local_months = {value.date().isoformat()[:7] for value in bounds[1]}
    if len(local_months) > 1:
        date = parsed[-1].astimezone(timezone.utc).date().isoformat()
        assignment = "latest_instant_utc"
    else:
        date = max(value.date().isoformat() for value in bounds[1])
        assignment = "latest_capture_local"
    if entry["trip_date"] != date or date[:7] != month or entry["month_assignment"] != assignment:
        raise ValueError("trip date/month disagrees with capture bounds")


def _validate_month(value: dict, month: str) -> None:
    if (not isinstance(value, dict) or set(value) != {"schema_version", "month", "trips"}
            or type(value["schema_version"]) is not int or value["schema_version"] not in (1, 2)
            or value["month"] != month or not isinstance(value["trips"], list)):
        raise ValueError("invalid monthly envelope")


def _validate_membership(trip: dict, window_microseconds: int, seen: set[str]) -> None:
    if type(window_microseconds) is not int or window_microseconds < 0:
        raise ValueError("invalid stored grouping window")
    window = timedelta(microseconds=window_microseconds)
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}", trip["month"]) is None:
        raise ValueError("invalid assigned month")
    _capture_text(trip["month"] + "-01T00:00:00+00:00")
    if (not isinstance(trip["hashes"], list) or not trip["hashes"]
            or not isinstance(trip["captures"], list) or len(trip["hashes"]) != len(trip["captures"])):
        raise ValueError("invalid trip membership")
    parsed = [_capture_text(capture) for capture in trip["captures"]]
    if parsed != sorted(parsed) or parsed[-1] - parsed[0] > window:
        raise ValueError("stored trip violates its grouping window")
    for digest in trip["hashes"]:
        if re.fullmatch(r"[a-f0-9]{64}", digest) is None or digest in seen:
            raise ValueError("duplicate or invalid photo membership")
        seen.add(digest)


def _validate_indexed_month(value: dict, state: dict, month: str) -> None:
    _validate_month(value, month)
    indexed = [trip for trip in state["committed"] if trip["month"] == month]
    if {trip["entry_index"] for trip in indexed} != set(range(len(value["trips"]))):
        raise ValueError("monthly membership index disagrees")
    for trip in indexed:
        entry = value["trips"][trip["entry_index"]]
        _validate_entry(entry, month, trip["captures"], schema_version=value["schema_version"])
        if _hash_bytes(_json_bytes(entry)) != trip["entry_digest"]:
            raise ValueError("indexed entry changed")


def _validate_publication(trip: dict, state: dict) -> None:
    publication = trip["publication"]
    if set(publication) != {"before", "before_bytes", "after", "bytes"}:
        raise ValueError("invalid pending publication")
    if publication["before"] != state["months"].get(trip["month"]):
        raise ValueError("publication base disagrees with committed state")
    if publication["before"] is None:
        if publication["before_bytes"] is not None:
            raise ValueError("unexpected publication base")
        before = {"schema_version": _entry_version(trip["entry"]), "month": trip["month"], "trips": []}
    else:
        data = publication["before_bytes"].encode("utf-8")
        if _hash_bytes(data) != publication["before"]:
            raise ValueError("publication base identity mismatch")
        before = json.loads(data)
    _validate_indexed_month(before, state, trip["month"])
    data = publication["bytes"].encode("utf-8")
    if _hash_bytes(data) != publication["after"]:
        raise ValueError("publication identity mismatch")
    after = json.loads(data)
    _validate_month(after, trip["month"])
    _validate_entry(trip["entry"], trip["month"], trip["captures"], schema_version=after["schema_version"])
    if (after["schema_version"] != before["schema_version"]
            or type(trip["entry_index"]) is not int or trip["entry_index"] != len(before["trips"])
            or after["trips"] != before["trips"] + [trip["entry"]]):
        raise ValueError("publication must append exactly its resolved trip")


def _guard_month(output: Path, state: dict, trip: dict) -> None:
    """Verify the affected monthly dependency before any pending photo effect."""
    month = trip["month"]
    actual = _actual_hash(output / (month + ".json"))
    expected = state["months"].get(month)
    publication = trip.get("publication")
    if publication is not None:
        _validate_publication(trip, state)
        if actual in (publication["before"], publication["after"]):
            return
    elif actual == expected:
        if expected is not None:
            monthly = json.loads((output / (month + ".json")).read_bytes())
            _validate_indexed_month(monthly, state, month)
            _validate_entry(trip["entry"], month, trip["captures"], schema_version=monthly["schema_version"])
        return
    raise BatchError("affected monthly output changed; preserve pending sources for reconciliation")


def _rewrite_state(value: dict) -> None:
    """Validate rewrite snapshots without trusting the live two-file boundary."""
    if (not isinstance(value, dict) or set(value) != {"state_version", "committed", "months", "pending"}
            or type(value["state_version"]) is not int or value["state_version"] != 1
            or value["pending"] is not None or not isinstance(value["committed"], list)
            or not isinstance(value["months"], dict)):
        raise ValueError("rewrite requires valid committed state without pending effects")
    seen, positions = set(), set()
    for month, digest in value["months"].items():
        if not isinstance(month, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}", month) is None:
            raise ValueError("invalid indexed month")
        _capture_text(month + "-01T00:00:00+00:00")
        if not isinstance(digest, str) or re.fullmatch(r"[a-f0-9]{64}", digest) is None:
            raise ValueError("invalid indexed month identity")
    for trip in value["committed"]:
        if not isinstance(trip, dict) or set(trip) != {"hashes", "captures", "window_microseconds", "month", "entry_index", "entry_digest"}:
            raise ValueError("invalid committed trip")
        _validate_membership(trip, trip["window_microseconds"], seen)
        if (trip["month"] not in value["months"] or type(trip["entry_index"]) is not int
                or trip["entry_index"] < 0 or not isinstance(trip["entry_digest"], str)
                or re.fullmatch(r"[a-f0-9]{64}", trip["entry_digest"]) is None):
            raise ValueError("invalid committed trip index")
        position = trip["month"], trip["entry_index"]
        if position in positions:
            raise ValueError("duplicate committed trip index")
        positions.add(position)


def _derived_rewrite(month: str, before_month: bytes, before_state: bytes) -> tuple[bytes, bytes]:
    state, monthly = json.loads(before_state), json.loads(before_month)
    _rewrite_state(state)
    if state["months"].get(month) != _hash_bytes(before_month):
        raise ValueError("rewrite month does not match its saved index")
    _validate_indexed_month(monthly, state, month)
    if monthly["schema_version"] != 1:
        raise ValueError("rewrite input must use legacy schema 1")
    after_month = _json_bytes({**monthly, "schema_version": 2,
                               "trips": [_sparse_entry(entry) for entry in monthly["trips"]]})
    sparse = json.loads(after_month)
    state["months"][month] = _hash_bytes(after_month)
    for trip in state["committed"]:
        if trip["month"] == month:
            trip["entry_digest"] = _hash_bytes(_json_bytes(sparse["trips"][trip["entry_index"]]))
    _validate_indexed_month(sparse, state, month)
    return after_month, _json_bytes(state)


def _recover_rewrite(output: Path) -> None:
    """Finish only a validated month-then-state transition under the output lock."""
    path = output / _REWRITE
    journal_hash = _actual_hash(path)
    if journal_hash is None:
        return
    try:
        journal = json.loads(path.read_bytes())
        if (not isinstance(journal, dict) or set(journal) != {"rewrite_version", "output_identity", "month", "before_month", "after_month", "before_state", "after_state"}
                or type(journal["rewrite_version"]) is not int or journal["rewrite_version"] != 1
                or journal["output_identity"] != _identity(output)
                or not isinstance(journal["month"], str)
                or re.fullmatch(r"[0-9]{4}-[0-9]{2}", journal["month"]) is None):
            raise ValueError("invalid rewrite ownership or envelope")
        snapshots = {}
        for name in ("before_month", "after_month", "before_state", "after_state"):
            value = journal[name]
            if not isinstance(value, dict) or set(value) != {"bytes", "hash"} or not isinstance(value["bytes"], str):
                raise ValueError("invalid rewrite snapshot")
            data = value["bytes"].encode("utf-8")
            if _hash_bytes(data) != value["hash"]:
                raise ValueError("rewrite snapshot hash mismatch")
            snapshots[name] = data
        month = journal["month"]
        derived = _derived_rewrite(month, snapshots["before_month"], snapshots["before_state"])
        if derived != (snapshots["after_month"], snapshots["after_state"]):
            raise ValueError("rewrite changes data beyond sparse serialization")
        month_path = output / (month + ".json")
        actual = _actual_hash(month_path), _actual_hash(output / _STATE)
        before = journal["before_month"]["hash"], journal["before_state"]["hash"]
        after = journal["after_month"]["hash"], journal["after_state"]["hash"]
        if actual not in (before, (after[0], before[1]), after):
            raise ValueError("rewrite files have unexpected or unreachable identities")
        if actual == before:
            _atomic_write(month_path, snapshots["after_month"], before[0])
            _rewrite_sync(output)
        if actual != after:
            _atomic_write(output / _STATE, snapshots["after_state"], before[1])
            _rewrite_sync(output)
        if (_actual_hash(month_path), _actual_hash(output / _STATE)) != after:
            raise ValueError("rewrite publication could not be verified")
        if _actual_hash(path) != journal_hash:
            raise ValueError("rewrite journal changed during recovery")
        path.unlink()
        _rewrite_sync(output)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, CaptureTimeError) as error:
        raise BatchError("monthly rewrite requires reconciliation: " + str(error)) from None


def _rewrite_sync(output: Path) -> None:
    if os.name != "nt":
        descriptor = os.open(output, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _rewrite_month(output: Path, state: dict, expected: list[str | None], month: str) -> bool:
    if state["pending"] is not None:
        raise BatchError("recover pending photo effects before rewriting monthly JSON")
    before_month = (output / (month + ".json")).read_bytes()
    monthly = json.loads(before_month)
    _validate_indexed_month(monthly, state, month)
    if _actual_hash(output / _STATE) != expected[0] or _hash_bytes(before_month) != state["months"][month]:
        raise BatchError("monthly output or private state changed before rewrite")
    if monthly["schema_version"] == 2:
        return False
    before_state = (output / _STATE).read_bytes()
    if _hash_bytes(before_state) != expected[0]:
        raise BatchError("private state changed while reading the monthly rewrite snapshot")
    after_month, after_state = _derived_rewrite(month, before_month, before_state)
    journal = {"rewrite_version": 1, "output_identity": _identity(output), "month": month}
    for name, data in (("before_month", before_month), ("after_month", after_month),
                       ("before_state", before_state), ("after_state", after_state)):
        journal[name] = {"bytes": data.decode("utf-8"), "hash": _hash_bytes(data)}
    _atomic_write(output / _REWRITE, _json_bytes(journal), None)
    _rewrite_sync(output)
    _recover_rewrite(output)
    state.clear()
    state.update(json.loads(after_state))
    expected[0] = _hash_bytes(after_state)
    return True


def rewrite_months(output: Path) -> dict[str, int]:
    """Convert indexed legacy monthly files without interpreting or moving photos."""
    output = Path(os.path.abspath(output))
    for ancestor in (output, *output.parents):
        _ordinary(ancestor, directory=True)
    with _output_lock(output):
        state, digest, invalid = _load_state(output)
        if invalid:
            raise BatchError("indexed monthly output requires reconciliation before rewriting")
        if state["pending"] is not None:
            raise BatchError("recover pending photo effects before rewriting monthly JSON")
        expected = [digest]
        count = sum(_rewrite_month(output, state, expected, month) for month in sorted(state["months"]))
        return {"rewritten_months": count, "indexed_trips": len(state["committed"])}


def _load_state(output: Path) -> tuple[dict, str | None, set[str]]:
    _recover_rewrite(output)
    path = output / _STATE
    expected = _actual_hash(path)
    if expected is None:
        return {"state_version": 1, "committed": [], "months": {}, "pending": None}, None, set()
    try:
        state = json.loads(path.read_bytes())
        if not isinstance(state, dict) or set(state) != {"state_version", "committed", "months", "pending"} or type(state["state_version"]) is not int or state["state_version"] != 1:
            raise ValueError
        if not isinstance(state["committed"], list) or not isinstance(state["months"], dict):
            raise ValueError
        seen = set()
        indexed_positions = set()
        for trip in state["committed"]:
            if set(trip) != {"hashes", "captures", "window_microseconds", "month", "entry_index", "entry_digest"}:
                raise ValueError
            _validate_membership(trip, trip["window_microseconds"], seen)
            if trip["month"] not in state["months"] or type(trip["entry_index"]) is not int or trip["entry_index"] < 0 or re.fullmatch(r"[a-f0-9]{64}", trip["entry_digest"]) is None:
                raise ValueError
            position = (trip["month"], trip["entry_index"])
            if position in indexed_positions:
                raise ValueError
            indexed_positions.add(position)
        pending = state["pending"]
        publications = {}
        if pending is not None:
            if not isinstance(pending, dict) or set(pending) != {"roots", "window_microseconds", "trips"}:
                raise ValueError
            if type(pending["window_microseconds"]) is not int or pending["window_microseconds"] < 0 or not isinstance(pending["trips"], list):
                raise ValueError
            if set(pending["roots"]) != {"source", "destination", "output"}:
                raise ValueError
            for root in pending["roots"].values():
                if set(root) != {"path", "identity"} or not Path(root["path"]).is_absolute() or not isinstance(root["identity"], list) or len(root["identity"]) != 2 or any(type(value) is not int for value in root["identity"]):
                    raise ValueError
            paths = set()
            destinations = set()
            temporaries = set()
            for trip in pending["trips"]:
                required = {"month", "entry", "hashes", "captures", "files"}
                optional = {"publication", "entry_index"} if "publication" in trip else set()
                if set(trip) != required | optional:
                    raise ValueError
                _validate_membership(trip, pending["window_microseconds"], seen)
                _validate_entry(trip["entry"], trip["month"], trip["captures"])
                if not isinstance(trip["files"], list) or len(trip["files"]) != len(trip["hashes"]):
                    raise ValueError
                for file, digest, capture in zip(trip["files"], trip["hashes"], trip["captures"]):
                    required_file = {"source", "hash", "destination", "temporary", "stage"}
                    if set(file) not in (required_file, required_file | {"capture_inputs"}):
                        raise ValueError
                    relative = Path(file["source"])
                    if relative.is_absolute() or not relative.parts or relative.suffix.lower() != ".heic" or any(part in ("..", ".") for part in relative.parts):
                        raise ValueError
                    if "capture_inputs" in file:
                        validate_capture_inputs(relative, file["capture_inputs"])
                        resolved = resolve_capture(relative, None, inputs=file["capture_inputs"]).capture
                        saved = _capture_text(capture)
                        if resolved != saved or resolved.utcoffset() != saved.utcoffset():
                            raise ValueError("pending capture context disagrees with its resolved trip")
                    for key in ("destination", "temporary"):
                        if not isinstance(file[key], str) or Path(file[key]).name != file[key] or file[key] in ("", ".", ".."):
                            raise ValueError
                    if re.fullmatch(r"\.flex-copy-[a-f0-9]{32}", file["temporary"]) is None or file["hash"] != digest:
                        raise ValueError
                    if file["stage"] not in ("reserved", "published", "deleted"):
                        raise ValueError
                    for name, collection in ((file["source"], paths), (file["destination"], destinations), (file["temporary"], temporaries)):
                        normalized = os.path.normcase(name)
                        if normalized in collection:
                            raise ValueError
                        collection.add(normalized)
                publication = trip.get("publication")
                if publication is not None:
                    if trip["month"] in publications or any(file["stage"] != "deleted" for file in trip["files"]):
                        raise ValueError
                    _validate_publication(trip, state)
                    publications[trip["month"]] = trip
        invalid = set()
        for month, digest in state["months"].items():
            if re.fullmatch(r"[0-9]{4}-[0-9]{2}", month) is None or re.fullmatch(r"[a-f0-9]{64}", digest) is None:
                raise ValueError
            month_path = output / (month + ".json")
            if month in publications:
                try:
                    _guard_month(output, state, publications[month])
                except (OSError, BatchError, ValueError):
                    invalid.add(month)
                continue
            if _actual_hash(month_path) != digest:
                invalid.add(month)
                continue
            try:
                value = json.loads(month_path.read_bytes())
            except (ValueError, UnicodeError):
                invalid.add(month)
                continue
            try:
                _validate_indexed_month(value, state, month)
            except (ValueError, TypeError, KeyError, CaptureTimeError):
                invalid.add(month)
        return state, expected, invalid
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, AttributeError, CaptureTimeError, CaptureFallbackError):
        raise BatchError("private output state is invalid; reconciliation required") from None


def _save_state(output: Path, state: dict, expected: list[str | None]) -> None:
    if state["pending"]:
        _check_roots(state["pending"]["roots"])
    data = _json_bytes(state)
    try:
        _atomic_write(output / _STATE, data, expected[0])
    except PublishedCleanupError:
        expected[0] = _hash_bytes(data)
        raise
    expected[0] = _hash_bytes(data)


def _copy_file(source: Path, temporary: Path) -> None:
    with source.open("rb") as reader, temporary.open("xb") as writer:
        for block in iter(lambda: reader.read(1024 * 1024), b""):
            writer.write(block)
        writer.flush()
        os.fsync(writer.fileno())


def _reserve(destination: Path, name: str, reserved: set[str]) -> str:
    original = Path(name)
    candidate = name
    number = 0
    while candidate in reserved or (destination / candidate).exists() or (destination / candidate).is_symlink():
        number += 1
        candidate = original.stem + f"-{number:02d}" + original.suffix
    reserved.add(candidate)
    return candidate


def _execute_plan(output: Path, state: dict, expected: list[str | None], report: _Report, *, recovery: bool, boundary=lambda: None) -> None:
    plan = state["pending"]
    _check_roots(plan["roots"])
    source = Path(plan["roots"]["source"]["path"])
    destination = Path(plan["roots"]["destination"]["path"])
    reserved = {file["destination"] for trip in plan["trips"] for file in trip["files"]}
    for trip in list(plan["trips"]):
        boundary()
        try:
            if any(other is not trip and other["month"] == trip["month"] and "publication" in other
                   for other in plan["trips"]):
                raise BatchError("another publication for this month is pending; preserve dependent sources until recovery")
            _guard_month(output, state, trip)
            for file in trip["files"]:
                boundary()
                _check_roots(plan["roots"])
                _guard_month(output, state, trip)
                origin = source / file["source"]
                target = destination / file["destination"]
                _safe_path(origin, source, missing=True)
                _safe_path(target, destination, missing=True)
                if origin.exists() and "capture_inputs" in file and not capture_inputs_match(origin, file["capture_inputs"]):
                    raise BatchError("file creation timestamp or capture context changed before movement")
                actual = _actual_hash(target)
                if actual is not None:
                    if actual != file["hash"]:
                        raise BatchError("reserved destination changed; reconciliation required")
                    if file["stage"] != "deleted":
                        file["stage"] = "published"
                elif file["stage"] in ("published", "deleted"):
                    raise BatchError("verified destination is missing")
                else:
                    if _hash_file(origin) != file["hash"]:
                        raise BatchError("source changed before copy")
                    temporary = destination / file["temporary"]
                    _safe_path(temporary, destination, missing=True)
                    if temporary.exists():
                        if _hash_file(temporary) != file["hash"]:
                            preserved = file["temporary"]
                            file["temporary"] = ".flex-copy-" + uuid.uuid4().hex
                            _save_state(output, state, expected)
                            report.issue(preserved, "saved temporary copy is incomplete or unexpected", "preserve bytes; recopy verified original using a fresh private reservation", incomplete=False)
                            temporary = destination / file["temporary"]
                    if not temporary.exists():
                        _copy_file(origin, temporary)
                    if _hash_file(temporary) != file["hash"] or _hash_file(origin) != file["hash"]:
                        raise BatchError("copy or source verification failed")
                    while True:
                        try:
                            os.link(temporary, target)
                            break
                        except FileExistsError:
                            if recovery:
                                raise BatchError("reserved destination changed during recovery") from None
                            file["destination"] = _reserve(destination, Path(file["source"]).name, reserved)
                            target = destination / file["destination"]
                            _save_state(output, state, expected)
                    temporary.unlink()
                    file["stage"] = "published"
                _save_state(output, state, expected)
                _check_roots(plan["roots"])
                if _hash_file(target) != file["hash"]:
                    raise BatchError("destination changed before source deletion")
                _guard_month(output, state, trip)
                if origin.exists() or origin.is_symlink():
                    _safe_path(origin, source)
                    if "capture_inputs" in file and not capture_inputs_match(origin, file["capture_inputs"]):
                        raise BatchError("file creation timestamp or capture context changed before source deletion")
                    if _hash_file(origin) != file["hash"]:
                        raise BatchError("source changed before deletion")
                    origin.unlink()
                    report.value["counts"]["moved"] += 1
                file["stage"] = "deleted"
                _save_state(output, state, expected)
            publication = trip.get("publication")
            month = trip["month"]
            month_path = output / (month + ".json")
            if publication is None:
                before = state["months"].get(month)
                if _actual_hash(month_path) != before:
                    raise BatchError("monthly output changed before publication")
                before_data = month_path.read_bytes() if before else None
                monthly = json.loads(before_data) if before else {"schema_version": _entry_version(trip["entry"]), "month": month, "trips": []}
                trip["entry_index"] = len(monthly["trips"])
                monthly["trips"].append(trip["entry"])
                after = _json_bytes(monthly)
                publication = trip["publication"] = {"before": before, "before_bytes": before_data.decode("utf-8") if before_data is not None else None,
                                                      "after": _hash_bytes(after), "bytes": after.decode("utf-8")}
                _save_state(output, state, expected)
            actual = _actual_hash(month_path)
            if actual == publication["before"]:
                _atomic_write(month_path, publication["bytes"].encode("utf-8"), publication["before"])
            elif actual != publication["after"]:
                raise BatchError("pending monthly output requires reconciliation")
            state["months"][month] = publication["after"]
            state["committed"].append({"hashes": trip["hashes"], "captures": trip["captures"],
                                       "window_microseconds": plan["window_microseconds"], "month": month,
                                       "entry_index": trip["entry_index"], "entry_digest": _hash_bytes(_json_bytes(trip["entry"]))})
            plan["trips"].remove(trip)
            _save_state(output, state, expected)
            report.value["counts"]["trips"] += 1
            report.flush_due()
        except Exception as error:
            reason = str(error) if isinstance(error, BatchError) else "trip movement or publication failed"
            report.issue(trip["files"][0]["source"], reason, "preserve originals, verified copies and pending state; rerun for recovery")
            # State changes/publication failures affect all following work unless the
            # last persisted sidecar still exactly matches in-memory state.
            if _actual_hash(output / _STATE) != expected[0] or _hash_bytes(_json_bytes(state)) != expected[0]:
                raise BatchError("shared progress state requires recovery") from error
    if not plan["trips"]:
        state["pending"] = None
        _save_state(output, state, expected)


class _Paused(BaseException):
    pass


class _CheckpointFailure(BatchError):
    pass


def _checkpoint_photo(checkpoint, relative, digest, interpreted, timing, capture_context=None):
    try:
        value = _compact_interpretation(interpreted)
        if capture_context is not None:
            value["capture_inputs"] = capture_context
        checkpoint.append(relative, digest, value, timing)
    except (OSError, ValueError) as error:
        raise _CheckpointFailure("unable to save extraction checkpoint (" + type(error).__name__ + "); resume required") from error


def _compact_interpretation(value):
    return {"layout": value.layout,
            "observations": [{"field_id": item.field_id, "status": item.status,
                              "value": item.value, "unit": item.unit} for item in value.observations],
            "metadata": asdict(value.metadata) if value.metadata is not None else None,
            "issues": [{"reason": item.reason, "action": item.action} for item in value.issues]}


def _restore_interpretation(path, value):
    """Validate cached extraction data before it can reach output planning."""
    required = {"layout", "observations", "metadata", "issues"}
    if not isinstance(value, dict) or set(value) not in (required, required | {"capture_inputs"}):
        raise BatchError("invalid cached interpretation")
    if "capture_inputs" in value:
        try:
            validate_capture_inputs(path, value["capture_inputs"])
        except CaptureFallbackError as error:
            raise BatchError("invalid cached capture context") from error
    if value["layout"] not in ("trip_summary", "drive_info", "nonmatch", "unresolved"):
        raise BatchError("invalid cached layout")
    observations = []
    seen = set()
    for item in value["observations"]:
        if (not isinstance(item, dict) or set(item) != {"field_id", "status", "value", "unit"}
                or item["field_id"] not in _FIELDS or item["field_id"] in seen
                or item["status"] not in ("clear", "unclear", "absent")
                or item["value"] is not None and not isinstance(item["value"], str)
                or item["unit"] is not None and not isinstance(item["unit"], str)):
            raise BatchError("invalid cached field")
        seen.add(item["field_id"])
        observation = FieldObservation(**item)
        if observation.status == "clear" and _reading(observation, observation.field_id) is None:
            raise BatchError("invalid cached clear reading")
        if observation.status != "clear" and (observation.value is not None or observation.unit is not None):
            raise BatchError("invalid unavailable cached reading")
        observations.append(observation)
    metadata = value["metadata"]
    if metadata is not None:
        if (not isinstance(metadata, dict) or set(metadata) != {"date_time_original", "offset_time_original", "subsec_time_original"}
                or any(item is not None and not isinstance(item, str) for item in metadata.values())):
            raise BatchError("invalid cached original metadata")
        metadata = CaptureMetadata(**metadata)
    issues = []
    for item in value["issues"]:
        if not isinstance(item, dict) or set(item) != {"reason", "action"} or any(not isinstance(v, str) for v in item.values()):
            raise BatchError("invalid cached issue")
        issues.append(InterpretationIssue(path, item["reason"], item["action"]))
    return PhotoInterpretation(path, value["layout"], tuple(observations), metadata, issues=tuple(issues))


@contextmanager
def _pause_handler(event, progress):
    previous = None
    installed = threading.current_thread() is threading.main_thread()
    if installed:
        previous = signal.getsignal(signal.SIGINT)
        def pause(signum, frame):
            event.set()
            progress.status = "pausing"
        signal.signal(signal.SIGINT, pause)
    try:
        yield
    finally:
        if installed:
            signal.signal(signal.SIGINT, previous)


def _timing(value):
    result = {}
    for key in ("active_seconds", "processed_seconds", "processed_count"):
        item = value.get(key, 0)
        if (isinstance(item, bool) or not isinstance(item, (float, int)) or not math.isfinite(item)
                or item < 0 or key == "processed_count" and type(item) is not int):
            raise BatchError("invalid checkpoint timing")
        result[key] = item
    return result


def _report_capture_source(relative, resolution, report):
    if resolution is not None and resolution.source != "metadata":
        report.issue(relative, "capture time from " + resolution.source,
                     "use America/Los_Angeles fallback; original capture date unavailable",
                     incomplete=False, stage="capture")


def _replay_checkpoint_issues(checkpoint, report, *, relatives=None):
    for relative, item in checkpoint.results.items():
        if relatives is not None and relative not in relatives:
            continue
        result = item["result"]
        resolution = failure = None
        if result["layout"] in ("trip_summary", "drive_info"):
            try:
                metadata = CaptureMetadata(**result["metadata"]) if result["metadata"] is not None else None
                if (metadata is None or metadata.date_time_original is None) and result.get("capture_inputs") is None:
                    raise CaptureFallbackError("legacy cache has no verified capture context; revalidate original on a new run")
                resolution = resolve_capture(Path(relative), metadata, inputs=result.get("capture_inputs"))
            except CaptureFallbackError as error:
                if error.silent:
                    report.value["counts"]["skipped"] += 1
                    report.value["status"] = "incomplete"
                    continue
                failure = error
            except (CaptureTimeError, ValueError, OverflowError, OSError) as error:
                failure = error
        _report_capture_source(relative, resolution, report)
        for issue in result["issues"]:
            if resolution and resolution.source != "metadata" and issue["action"] == "preserve/report/exclude from grouping":
                continue
            report.issue(relative, issue["reason"], issue["action"], incomplete=result["layout"] == "unresolved", stage="interpretation")
        if failure:
            report.issue(relative, "capture timestamp invalid or unavailable", "leave untouched; exclude from grouping; revalidate original on a subsequent new run", stage="metadata")


def _process_batch(source: Path, destination: Path, output: Path, *, ownership, assets: InterpretationAssets,
                  window: timedelta = timedelta(minutes=3), resume=False, display_progress=False,
                  pause_event=None, diagnostics=False) -> BatchResult:
    """Interpret/checkpoint each safe unit before verified recoverable effects."""
    report = checkpoint = progress = None
    counts = {}
    event = pause_event if pause_event is not None else threading.Event()
    paused = False
    started_run = time.monotonic()
    try:
        if not isinstance(window, timedelta) or window < timedelta(0):
            raise BatchError("window must be a nonnegative timedelta")
        source, destination, output = _roots(source, destination, output)
        diagnostic_log = Diagnostics(output, enabled=diagnostics)
        report = _Report(output)
        report.value["status"] = "complete"
        counts = report.value["counts"]
        ownership.enter_context(_output_lock(output))
        _validate_assets(assets)
        state, digest, invalid = _load_state(output)
        expected = [digest]
        for month in sorted(invalid):
            report.issue(month, "indexed monthly output changed or is invalid", "preserve affected month; reconcile external edits")
        roots = {key: {"path": str(path), "identity": _identity(path)} for key, path in
                 (("source", source), ("destination", destination), ("output", output))}
        config = {"roots": roots, "window_microseconds": window // timedelta(microseconds=1),
                  "executable": str(assets.tesseract_executable.absolute()),
                  "tessdata": str(assets.tessdata_directory.absolute()),
                  "executable_sha256": assets.executable_sha256, "recipe_version": 3}
        saved = (output / ".flex-photo-checkpoint").exists()
        if saved or not state["pending"]:
            recovering = bool(state["pending"])
            if recovering and not resume:
                config["window_microseconds"] = state["pending"]["window_microseconds"]
            candidates = None if resume or recovering else [p.as_posix() for p in discover_heic(source)]
            checkpoint = Checkpoint(output, config, resume=resume or recovering, candidates=candidates)
            candidates = [Path(p) for p in checkpoint.manifest["candidates"]]
            # Validate every saved scalar result even when effects recovery takes precedence.
            for relative, item in checkpoint.results.items():
                _restore_interpretation(source / relative, item["result"])
            for item in checkpoint.history:
                latest = checkpoint.results[item["relative"]]
                if latest["hash"] != item["hash"]:
                    for issue in item["result"]["issues"]:
                        report.issue(item["relative"], "previous input version: " + issue["reason"], "superseded by changed bytes; preserve prior failure record", incomplete=False, stage="resume")
            timing = _timing(checkpoint.timing)
            counts["candidates"] = len(candidates)
        else:
            timing = {}
            candidates = []
            if state["pending"]["roots"] != roots:
                raise BatchError("pending operation belongs to different folder identities")
        timing["active_seconds"] = timing.get("active_seconds", 0.) + time.monotonic() - started_run
        progress = Progress(len(candidates), enabled=display_progress, **timing)
        if display_progress:
            progress.start()
        def boundary():
            if event.is_set():
                raise _Paused()
            report.flush_due()
            if checkpoint and progress.stage in ("recovery", "movement/publication"):
                try:
                    checkpoint.save(progress.snapshot())
                except (OSError, ValueError) as error:
                    raise _CheckpointFailure("unable to checkpoint finalization timing: " + type(error).__name__) from error
        with _pause_handler(event, progress):
            if state["pending"]:
                if state["pending"]["roots"] != roots or state["pending"]["window_microseconds"] != config["window_microseconds"]:
                    raise BatchError("pending operation configuration changed")
                # Moved sources need not exist; the saved effect plan verifies copies.
                if checkpoint:
                    _replay_checkpoint_issues(checkpoint, report)
                progress.update(evaluated=len(candidates), stage="recovery", status="completing")
                recovered_months = {trip["month"] for trip in state["pending"]["trips"]}
                _execute_plan(output, state, expected, report, recovery=True, boundary=boundary)
                if state["pending"]:
                    report.value["status"] = "incomplete"
                else:
                    for month in sorted(recovered_months):
                        _rewrite_month(output, state, expected, month)
            else:
                progress.update(stage="hashing")
                unique = {}
                committed_hashes = {digest for trip in state["committed"] for digest in trip["hashes"]}
                for relative in candidates:
                    boundary()
                    try:
                        path = source / relative
                        _safe_path(path, source)
                        digest = _hash_file(path)
                        if digest in unique:
                            counts["duplicates"] += 1
                            report.issue(relative, "byte-identical input copy", "leave extra copy untouched", incomplete=False, stage="discovery")
                        else:
                            unique[digest] = relative
                    except FileNotFoundError:
                        cached = checkpoint.results.get(relative.as_posix())
                        if cached and cached["hash"] in committed_hashes:
                            counts["repeats"] += 1
                            _replay_checkpoint_issues(checkpoint, report, relatives={relative.as_posix()})
                        else:
                            counts["skipped"] += 1
                            report.issue(relative, "source unavailable during preflight", "leave untouched; continue", stage="discovery")
                    except (OSError, BatchError):
                        counts["skipped"] += 1
                        report.issue(relative, "source unavailable during preflight", "leave untouched; continue", stage="discovery")
                known = set()
                for previous in state["committed"]:
                    supplied = set(previous["hashes"]) & unique.keys()
                    known.update(supplied)
                    if supplied == set(previous["hashes"]):
                        counts["repeats"] += len(supplied)
                    elif supplied:
                        counts["skipped"] += len(supplied)
                        for digest in sorted(supplied):
                            report.issue(unique[digest], "partial indexed trip overlap", "leave untouched for reconciliation")
                records = []
                evaluated = counts["duplicates"] + counts["skipped"] + counts["repeats"]
                progress.update(evaluated=evaluated, stage="decoding/OCR")
                for digest, relative in unique.items():
                    boundary()
                    if digest in known:
                        continue
                    path = source / relative
                    before_evaluated = evaluated
                    try:
                        _safe_path(path, source)
                        cached = checkpoint.results.get(relative.as_posix())
                        if cached is not None and cached["hash"] == digest:
                            interpreted = _restore_interpretation(path, cached["result"])
                            evaluated += 1
                            progress.update(evaluated=evaluated)
                        else:
                            if cached is not None:
                                report.issue(relative, "input changed since checkpoint", "invalidate cached readings; reprocess changed bytes", incomplete=False, stage="resume")
                                for issue in cached["result"]["issues"]:
                                    report.issue(relative, "previous input version: " + issue["reason"], "superseded by changed bytes; preserve prior failure record", incomplete=False, stage="resume")
                            started = time.monotonic()
                            interpreted = interpret_photo(path, assets, diagnostics=True) if diagnostics else interpret_photo(path, assets)
                            diagnostic_log.record("interpretation", interpreted.diagnostic_trace)
                            if _hash_file(path) != digest:
                                raise BatchError("source changed during interpretation")
                            evaluated += 1
                            progress.record_photo(time.monotonic() - started, evaluated=evaluated)
                        context = None
                        if (interpreted.layout in ("trip_summary", "drive_info")
                                and (interpreted.metadata is None or interpreted.metadata.date_time_original is None)):
                            context = capture_inputs(path)
                        if cached is None or cached["hash"] != digest:
                            _checkpoint_photo(checkpoint, relative.as_posix(), digest, interpreted, progress.snapshot(), context)
                        elif cached["result"].get("capture_inputs") != context:
                            if cached["result"].get("capture_inputs") is not None:
                                report.issue(relative, "file creation timestamp changed since checkpoint", "revalidate capture fallback without repeating OCR", incomplete=False, stage="resume")
                            _checkpoint_photo(checkpoint, relative.as_posix(), digest, interpreted, progress.snapshot(), context)
                        resolution = capture_failure = None
                        if interpreted.layout in ("trip_summary", "drive_info"):
                            try:
                                resolution = resolve_capture(path, interpreted.metadata, inputs=context)
                            except CaptureFallbackError as error:
                                if error.silent:
                                    counts["skipped"] += 1
                                    report.value["status"] = "incomplete"
                                    continue
                                capture_failure = error
                            except (CaptureTimeError, OverflowError, ValueError) as error:
                                capture_failure = error
                        _report_capture_source(relative, resolution, report)
                        for issue in interpreted.issues:
                            if resolution and resolution.source != "metadata" and issue.action == "preserve/report/exclude from grouping":
                                continue
                            report.issue(relative, issue.reason, issue.action, incomplete=interpreted.layout == "unresolved", stage="interpretation")
                        if interpreted.layout == "nonmatch":
                            counts["nonmatches"] += 1
                            continue
                        if interpreted.layout not in ("trip_summary", "drive_info"):
                            counts["skipped"] += 1
                            if not interpreted.issues:
                                report.issue(relative, "individual interpretation unresolved", "leave untouched; continue", stage="interpretation")
                            continue
                        if capture_failure:
                            counts["skipped"] += 1
                            report.issue(relative, "capture timestamp invalid or unavailable: " + str(capture_failure), "leave untouched; exclude from grouping", stage="metadata")
                            continue
                        records.append({"path": relative.as_posix(), "hash": digest, "capture": resolution.capture,
                                        "spelling": resolution.spelling, "capture_inputs": resolution.inputs,
                                        "observations": interpreted.observations})
                    except SharedAssetError:
                        raise
                    except _CheckpointFailure:
                        raise
                    except (OSError, BatchError) as error:
                        counts["skipped"] += 1
                        evaluated = max(evaluated, before_evaluated + 1)
                        progress.update(evaluated=evaluated)
                        report.issue(relative, str(error) if isinstance(error, BatchError) else "source unavailable", "leave untouched; continue", stage="preflight")
                    except Exception as error:
                        counts["skipped"] += 1
                        evaluated = max(evaluated, before_evaluated + 1)
                        progress.update(evaluated=evaluated)
                        report.issue(relative, "unexpected photo processing failure: " + type(error).__name__, "leave untouched; continue", stage="preflight")
                    report.flush_due()
                progress.update(stage="grouping", status="completing")
                boundary()
                groups = [[records[index] for index in group] for group in group_capture_times([item["capture"] for item in records], window)]
                eligible = _eligible_trips(groups, state["committed"], window)
                trips = []
                reserved = set()
                rewrite_months_needed = set()
                for index, group in enumerate(groups):
                    if index not in eligible:
                        counts["skipped"] += len(group)
                        for item in group:
                            report.issue(item["path"], "trip overlaps indexed capture history", "leave untouched for reconciliation")
                        continue
                    month, entry = _resolve_trip(group, report)
                    if month in invalid or (month not in state["months"] and (output / (month + ".json")).exists()):
                        counts["skipped"] += len(group)
                        report.issue(group[0]["path"], "monthly output/index requires reconciliation", "leave trip untouched")
                        continue
                    if month in state["months"]:
                        rewrite_months_needed.add(month)
                    trips.append({"month": month, "entry": entry, "hashes": [item["hash"] for item in group],
                                  "captures": [item["capture"].isoformat() for item in group],
                                  "files": [{"source": item["path"], "hash": item["hash"],
                                             "destination": _reserve(destination, Path(item["path"]).name, reserved),
                                             "temporary": ".flex-copy-" + uuid.uuid4().hex, "stage": "reserved",
                                             **({"capture_inputs": item["capture_inputs"]} if item["capture_inputs"] is not None else {})}
                                            for item in group]})
                _validate_assets(assets)
                _check_roots(roots)
                boundary()
                for month in sorted(rewrite_months_needed):
                    _rewrite_month(output, state, expected, month)
                if trips:
                    progress.update(stage="movement/publication")
                    state["pending"] = {"roots": roots, "window_microseconds": window // timedelta(microseconds=1), "trips": trips}
                    _save_state(output, state, expected)
                    _execute_plan(output, state, expected, report, recovery=False, boundary=boundary)
                if state["pending"]:
                    report.value["status"] = "incomplete"
            progress.update(stage="report", status="completing")
            # Remove extraction checkpoint only after all effects are durably reconciled.
            if checkpoint and not state["pending"]:
                report.finalized = True
                report.write()
                checkpoint.finish()
    except _Paused:
        paused = True
        if progress:
            progress.close(status="paused")
        if checkpoint:
            try:
                checkpoint.save(progress.snapshot())
            except (OSError, ValueError) as error:
                paused = False
                report.issue("checkpoint", "pause checkpoint save failed: " + type(error).__name__, "preserve journal; resume from last verified boundary", stage="checkpoint")
        if report:
            report.value["status"] = "paused" if paused else "incomplete"
    except (Exception, KeyboardInterrupt) as error:
        if report:
            report.value["status"] = "incomplete"
            reason = str(error) if isinstance(error, (SharedAssetError, BatchError, DiscoveryError, ValueError)) else "processing stopped before further safe effects (" + type(error).__name__ + ")"
            report.issue("run", reason, "preserve originals and pending evidence; inspect report and resume with unchanged configuration", stage="run")
        else:
            print("process-failed: folders or run report unavailable", file=sys.stderr)
    if progress:
        progress.close(status="paused" if paused else "completed" if report.value["status"] == "complete" else "incomplete")
        report.value["progress"] = progress.snapshot()
    if report:
        try:
            report.finalized = True
            report.write()
        except BatchError:
            report.value["status"] = "incomplete"
        return BatchResult(report.value["status"], report.path if report.saved else None, dict(counts))
    return BatchResult("incomplete", None, counts)


def process_batch(source: Path, destination: Path, output: Path, *, assets: InterpretationAssets,
                  window: timedelta = timedelta(minutes=3), resume=False, display_progress=False,
                  pause_event=None, diagnostics=False) -> BatchResult:
    with ExitStack() as ownership:
        return _process_batch(source, destination, output, ownership=ownership, assets=assets,
                              window=window, resume=resume, display_progress=display_progress,
                              pause_event=pause_event, diagnostics=diagnostics)
