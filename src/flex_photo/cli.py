"""Console entry point for bootstrap readiness and candidate discovery."""

import argparse
from collections.abc import Sequence
import json
from datetime import timedelta
import math
from pathlib import Path
import sys

from flex_photo import __version__
from flex_photo.discovery import DiscoveryError, discover_heic


def _main(argv: Sequence[str] | None) -> int:
    parser = argparse.ArgumentParser(
        prog="flex-photo",
        description="Offline HEIC dashboard processing and candidate discovery.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command")
    discovery = commands.add_parser("discover", help="list HEIC filename candidates as JSON")
    discovery.add_argument("source", metavar="SOURCE", type=Path, help="local source directory")
    processing = commands.add_parser("process", help="organize dashboard originals and append monthly trip JSON")
    processing.add_argument("source", metavar="SOURCE", type=Path)
    processing.add_argument("--destination", required=True, type=Path)
    processing.add_argument("--json-output", required=True, type=Path)
    processing.add_argument("--window-seconds", default=180.0, type=float)
    processing.add_argument("--tesseract", required=True, type=Path)
    processing.add_argument("--tessdata", required=True, type=Path)
    processing.add_argument("--tesseract-sha256", required=True)
    processing.add_argument("--resume", action="store_true", help="resume the saved operation with unchanged folders and settings")
    processing.add_argument("--diagnostics", action="store_true", help="enable bounded private exception traces")
    arguments = parser.parse_args(argv)
    if arguments.command == "process":
        if not math.isfinite(arguments.window_seconds) or arguments.window_seconds < 0:
            processing.error("--window-seconds must be finite and nonnegative")
        try:
            window = timedelta(seconds=arguments.window_seconds)
        except OverflowError:
            processing.error("--window-seconds exceeds the supported range")
        from .batch import process_batch
        from .interpretation import InterpretationAssets
        result = process_batch(arguments.source, arguments.destination, arguments.json_output,
            assets=InterpretationAssets(arguments.tesseract, arguments.tessdata, arguments.tesseract_sha256),
            window=window, resume=arguments.resume, diagnostics=arguments.diagnostics, display_progress=True)
        print(json.dumps(result.summary(), ensure_ascii=True))
        sys.stdout.flush()
        return 0 if result.complete or result.status == "paused" else 1
    if arguments.command == "discover":
        try:
            candidates = discover_heic(arguments.source)
        except DiscoveryError as error:
            message = f"{error.category}: {error.reason}"
            print(message, file=sys.stderr)
            return 1
        print(json.dumps([path.as_posix() for path in candidates], ensure_ascii=True))
        sys.stdout.flush()
        return 0
    print("Offline photo processing ready. Use 'process --help' for local asset and folder options.")
    sys.stdout.flush()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI, reporting stream failures without an OS traceback."""
    try:
        return _main(argv)
    except (OSError, UnicodeError):
        # Close a broken pipe so interpreter shutdown does not retry its buffer.
        try:
            sys.stdout.close()
        except (OSError, UnicodeError):
            pass
        try:
            print("output-failed: unable to write console output", file=sys.stderr)
        except (OSError, UnicodeError):
            pass
        return 1
