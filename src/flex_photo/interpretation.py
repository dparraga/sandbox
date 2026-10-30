"""Bounded offline interpretation of the four approved dashboard readings."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

from .metadata import CaptureMetadata, MetadataError, read_capture_metadata

_FIELDS = ("trip_distance", "trip_duration", "trip_average_mpg", "odometer")
_MODEL_SHA256 = "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2"
_MEMORY_BYTES = 1024 ** 3
_DECODE_SECONDS = 30
_OCR_SECONDS = 15
_PHOTO_SECONDS = 120
_PRIMARY_PIXELS = 16_000_000
_CROP_PIXELS = 4_000_000
_SCALED_PIXELS = 16_000_000

@dataclass(frozen=True)
class InterpretationAssets:
    tesseract_executable: Path
    tessdata_directory: Path
    executable_sha256: str

@dataclass(frozen=True)
class CropEvidence:
    bounds: tuple[int, int, int, int]
    views: tuple[str, ...]
    view_ids: tuple[int, ...] = ()

@dataclass(frozen=True)
class FieldObservation:
    field_id: str
    status: str
    raw_text: str | None = None
    value: str | None = None
    unit: str | None = None
    evidence: tuple[CropEvidence, ...] = ()

@dataclass(frozen=True)
class InterpretationIssue:
    path: Path
    reason: str
    action: str

@dataclass(frozen=True)
class PhotoInterpretation:
    path: Path
    layout: str
    observations: tuple[FieldObservation, ...] = ()
    metadata: CaptureMetadata | None = None
    metadata_error: MetadataError | None = None
    issues: tuple[InterpretationIssue, ...] = ()
    diagnostic_trace: str | None = None


def _diagnostic_trace(error: BaseException) -> str:
    """Format stack locations only, without exception text, locals or OCR data."""
    import traceback
    frames = [(Path(frame.filename).name, frame.lineno, frame.name, "")
              for frame in traceback.StackSummary.extract(
                  traceback.walk_tb(error.__traceback__), lookup_lines=False)]
    trace = "".join(traceback.format_list(frames)) + type(error).__name__ + "\n"
    if len(trace) > 8192:
        trace = trace[:4096] + "\n[diagnostic stack size limit]\n" + trace[-4000:]
    return trace

class SharedAssetError(Exception):
    """Stop the caller incomplete, before any moves or monthly output effects."""


def _digest(path: Path, limit: int) -> str:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > limit:
        raise SharedAssetError("shared asset unavailable or invalid")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_assets(assets: InterpretationAssets) -> None:
    try:
        if not re.fullmatch(r"[0-9a-f]{64}", assets.executable_sha256):
            raise SharedAssetError("invalid executable identity")
        if _digest(assets.tesseract_executable, 64 * 1024 * 1024) != assets.executable_sha256:
            raise SharedAssetError("shared executable identity changed")
        if _digest(assets.tessdata_directory / "eng.traineddata", 4_113_088) != _MODEL_SHA256:
            raise SharedAssetError("shared English model identity changed")
        if os.name != "nt" and not os.access(assets.tesseract_executable, os.X_OK):
            raise SharedAssetError("shared executable unavailable")
    except OSError as error:
        raise SharedAssetError("shared asset unavailable") from error


def _parse_field(field_id: str, text: str) -> tuple[str, str | None] | None:
    text = " ".join(text.split())
    label = {"trip_distance": "Trip Distance", "trip_duration": "Trip Time",
             "trip_average_mpg": "Trip Average", "odometer": ""}[field_id]
    if label:
        if not text.startswith(label + " "):
            return None
        text = text[len(label):].strip()
    if field_id == "trip_duration":
        match = re.fullmatch(r"([0-9]+):([0-5][0-9])", text)
        return (match[1].zfill(2) + ":" + match[2], None) if match else None
    unit = "MPG" if field_id == "trip_average_mpg" else "mi"
    grammar = r"(-?[0-9]+(?:\.[0-9]+)?)\s*"
    match = re.fullmatch(grammar + unit, text)
    return (match[1], unit) if match else None


def validate_interpretation_assets(assets: InterpretationAssets) -> None:
    """Validate shared files and native loading in the bounded worker before effects."""
    _validate_assets(assets)
    from ._interpretation_worker import run_bounded
    try:
        payload = run_bounded(None, assets)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        raise SharedAssetError("shared native runtime validation failed") from error
    _validate_assets(assets)
    if payload.get("shared_error"):
        raise SharedAssetError(payload["shared_error"])
    if payload.get("validated") is not True:
        raise SharedAssetError("shared native runtime validation failed")


def interpret_photo(path: Path, assets: InterpretationAssets, *, diagnostics: bool = False) -> PhotoInterpretation:
    """Interpret locally without modifying the original or publishing any files."""
    _validate_assets(assets)
    from ._interpretation_worker import run_bounded
    try:
        payload = run_bounded(path, assets, diagnostics=True) if diagnostics else run_bounded(path, assets)
    except SharedAssetError:
        raise
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        _validate_assets(assets)
        return PhotoInterpretation(path, "unresolved", issues=(InterpretationIssue(
            path, "individual native execution or containment failure", "preserve/report/continue"),),
            diagnostic_trace=_diagnostic_trace(error) if diagnostics else None)
    _validate_assets(assets)
    if payload.get("shared_error"):
        raise SharedAssetError(payload["shared_error"])
    if "error" in payload:
        return PhotoInterpretation(path, "unresolved", issues=(InterpretationIssue(
            path, payload["error"], "preserve/report/continue"),),
            diagnostic_trace=payload.get("diagnostic_trace") if diagnostics else None)
    observations = tuple(FieldObservation(item["field_id"], item["status"], item.get("raw_text"),
        item.get("value"), item.get("unit"), tuple(CropEvidence(tuple(e["bounds"]), tuple(e["views"]),
                                                              tuple(e.get("view_ids", ())))
        for e in item.get("evidence", ()))) for item in payload.get("observations", ()))
    issues = [InterpretationIssue(path, reason, "report/retain earlier valid candidates")
              for reason in payload.get("issues", ())]
    metadata = metadata_error = None
    if payload["layout"] in ("trip_summary", "drive_info"):
        try:
            metadata = read_capture_metadata(path)
        except MetadataError as error:
            metadata_error = error
            issues.append(InterpretationIssue(path, error.reason, "preserve/report/exclude from grouping"))
    _validate_assets(assets)
    return PhotoInterpretation(path, payload["layout"], observations, metadata, metadata_error, tuple(issues))
