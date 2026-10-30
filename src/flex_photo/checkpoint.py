"""Private, append-only extraction checkpoints under the batch output lock."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat


_DIRECTORY = ".flex-photo-checkpoint"
_FINISHED_DIRECTORY = ".flex-photo-checkpoint-finished"
_FILES = {"manifest.json", "results.jsonl", "manifest.tmp"}


def _bytes(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _ordinary(path, *, directory=False):
    info = path.lstat()
    if (stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400
            or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
        raise ValueError("checkpoint contains unsupported filesystem items")
    return info.st_dev, info.st_ino


def _sync_directory(path):
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _relative(value):
    if (not isinstance(value, str) or "\\" in value or not value
            or PurePosixPath(value).is_absolute() or PureWindowsPath(value).drive
            or any(part in ("", ".", "..") for part in value.split("/"))
            or PurePosixPath(value).suffix.lower() != ".heic"):
        raise ValueError("checkpoint candidate path is invalid")
    return value


def _compact_result(value):
    if isinstance(value, dict):
        if any(key in ("raw_text", "evidence") for key in value):
            raise ValueError("checkpoint must not contain raw OCR evidence")
        for child in value.values():
            _compact_result(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _compact_result(child)


class Checkpoint:
    """One frozen candidate set and verified results, with no per-photo rewrites.

    The caller owns the exclusive batch output lock. Config must include folder
    identities, window, asset hashes and recipe version, and match exactly on
    resume. Result dictionaries contain scalar observations, metadata and issues.
    """

    def __init__(self, output, config, *, resume=False, candidates=None):
        self.output = Path(os.path.abspath(output))
        for ancestor in reversed((self.output, *self.output.parents)):
            _ordinary(ancestor, directory=True)
        self._cleanup_finished()
        self.path = self.output / _DIRECTORY
        self._manifest_path = self.path / "manifest.json"
        self._journal_path = self.path / "results.jsonl"
        self.results = {}
        self.history = []
        self._seq = 0
        self._timing = {}
        if self.path.exists() or self.path.is_symlink():
            if not resume:
                raise ValueError("saved extraction checkpoint exists; use --resume")
            _ordinary(self.path, directory=True)
            self._check_files()
            _ordinary(self._manifest_path)
            self._manifest_bytes = self._manifest_path.read_bytes()
            self.manifest = json.loads(self._manifest_bytes)
            if (not isinstance(self.manifest, dict)
                    or set(self.manifest) != {"checkpoint_version", "config", "candidates", "timing", "seq"}
                    or type(self.manifest["checkpoint_version"]) is not int
                    or self.manifest["checkpoint_version"] != 1
                    or self.manifest["config"] != config):
                raise ValueError("checkpoint configuration changed or is incompatible")
            self._validate_candidates(self.manifest["candidates"])
            if (not isinstance(self.manifest["timing"], dict)
                    or type(self.manifest["seq"]) is not int or self.manifest["seq"] < 0):
                raise ValueError("checkpoint timing is invalid")
            self._timing = self.manifest["timing"]
            self._load_journal()
            if self.manifest["seq"] > self._seq:
                raise ValueError("checkpoint journal is missing saved results")
        else:
            if resume:
                raise ValueError("no extraction checkpoint is available to resume")
            candidates = [] if candidates is None else list(candidates)
            self._validate_candidates(candidates)
            # Verify serializability before creating any recovery files.
            self.manifest = {"checkpoint_version": 1, "config": config,
                             "candidates": candidates, "timing": {}, "seq": 0}
            _bytes(self.manifest)
            self.path.mkdir(mode=0o700)
            with self._journal_path.open("xb") as stream:
                stream.flush()
                os.fsync(stream.fileno())
            self._manifest_bytes = None
            self._write_manifest()
            _sync_directory(self.output)
        self._directory_identity = _ordinary(self.path, directory=True)
        self._journal_identity = _ordinary(self._journal_path)
        self._candidates = set(self.manifest["candidates"])

    @staticmethod
    def _validate_candidates(candidates):
        if not isinstance(candidates, list):
            raise ValueError("checkpoint candidate set is invalid")
        names = [_relative(value) for value in candidates]
        if len({os.path.normcase(value) for value in names}) != len(names):
            raise ValueError("checkpoint candidate paths are duplicated")

    def _check_files(self):
        for path in self.path.iterdir():
            if path.name not in _FILES:
                raise ValueError("checkpoint contains unexpected files; preserve for reconciliation")
            _ordinary(path)

    def _guard(self):
        for ancestor in (self.path, self.output, *self.output.parents):
            _ordinary(ancestor, directory=True)
        if _ordinary(self.path, directory=True) != self._directory_identity:
            raise ValueError("checkpoint directory identity changed")
        self._check_files()
        if _ordinary(self._journal_path) != self._journal_identity:
            raise ValueError("checkpoint journal identity changed")
        _ordinary(self._manifest_path)
        if self._manifest_path.read_bytes() != self._manifest_bytes:
            raise ValueError("checkpoint manifest changed unexpectedly")

    def _load_journal(self):
        _ordinary(self._journal_path)
        candidates = set(self.manifest["candidates"])
        with self._journal_path.open("r+b") as stream:
            while True:
                boundary = stream.tell()
                line = stream.readline()
                if not line:
                    break
                if not line.endswith(b"\n"):
                    # Only an unterminated final append can be discarded. No
                    # completed, checksummed record is silently skipped.
                    stream.truncate(boundary)
                    stream.flush()
                    os.fsync(stream.fileno())
                    break
                try:
                    envelope = json.loads(line)
                    record = envelope["data"]
                    if (set(envelope) != {"data", "sha256"}
                            or hashlib.sha256(_bytes(record)).hexdigest() != envelope["sha256"]
                            or set(record) != {"seq", "relative", "hash", "result", "timing"}
                            or type(record["seq"]) is not int or record["seq"] != self._seq + 1
                            or _relative(record["relative"]) not in candidates
                            or not isinstance(record["hash"], str)
                            or re.fullmatch(r"[a-f0-9]{64}", record["hash"]) is None
                            or not isinstance(record["result"], dict)
                            or not isinstance(record["timing"], dict)):
                        raise ValueError
                    _compact_result(record["result"])
                except (ValueError, KeyError, TypeError):
                    raise ValueError("checkpoint contains a corrupt completed result") from None
                self._seq = record["seq"]
                self.history.append(record)
                self.results[record["relative"]] = {key: record[key]
                    for key in ("hash", "result", "timing")}
                if self._seq > self.manifest["seq"]:
                    self._timing = record["timing"]

    @property
    def timing(self):
        return dict(self._timing)

    def _write_manifest(self):
        data = _bytes(self.manifest)
        temporary = self.path / "manifest.tmp"
        if temporary.exists() or temporary.is_symlink():
            _ordinary(temporary)
            temporary.unlink()  # Known leftover from an interrupted manifest save.
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if self._manifest_bytes is not None:
            _ordinary(self._manifest_path)
            if self._manifest_path.read_bytes() != self._manifest_bytes:
                raise ValueError("checkpoint manifest changed unexpectedly")
        elif self._manifest_path.exists() or self._manifest_path.is_symlink():
            raise ValueError("checkpoint manifest appeared unexpectedly")
        os.replace(temporary, self._manifest_path)
        _sync_directory(self.path)
        self._manifest_bytes = data

    def append(self, relative, digest, result, timing):
        self._guard()
        if _relative(relative) not in self._candidates:
            raise ValueError("photo is outside saved candidate set")
        if not isinstance(digest, str) or re.fullmatch(r"[a-f0-9]{64}", digest) is None:
            raise ValueError("checkpoint input hash is invalid")
        if not isinstance(result, dict) or not isinstance(timing, dict):
            raise ValueError("checkpoint result or timing is invalid")
        _compact_result(result)
        record = json.loads(_bytes({"seq": self._seq + 1, "relative": relative, "hash": digest,
                                   "result": result, "timing": timing}))
        encoded = _bytes(record)
        line = _bytes({"data": record, "sha256": hashlib.sha256(encoded).hexdigest()}) + b"\n"
        with self._journal_path.open("ab") as stream:
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())
        self._seq += 1
        self.history.append(record)
        self.results[relative] = {key: record[key] for key in ("hash", "result", "timing")}
        self._timing = record["timing"]

    def save(self, timing):
        self._guard()
        if not isinstance(timing, dict):
            raise ValueError("checkpoint timing is invalid")
        self.manifest["timing"] = timing
        self.manifest["seq"] = self._seq
        self._write_manifest()
        self._timing = timing

    def finish(self):
        """Remove only this checkpoint's known files after verified completion."""
        self._guard()
        # The directory name is the durable completion marker. Once renamed,
        # interruption of cleanup cannot make missing results look resumable.
        self._cleanup_finished()
        os.rename(self.path, self.output / _FINISHED_DIRECTORY)
        _sync_directory(self.output)
        self._cleanup_finished()

    def _cleanup_finished(self):
        path = self.output / _FINISHED_DIRECTORY
        if not path.exists() and not path.is_symlink():
            return
        _ordinary(path, directory=True)
        for file in path.iterdir():
            if file.name not in _FILES:
                raise ValueError("finished checkpoint contains unexpected files; preserve for reconciliation")
            _ordinary(file)
        for name in ("manifest.tmp", "results.jsonl", "manifest.json"):
            file = path / name
            try:
                _ordinary(file)
            except FileNotFoundError:
                continue
            file.unlink()
        path.rmdir()
        _sync_directory(self.output)
