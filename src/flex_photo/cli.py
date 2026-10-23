"""Console entry point for bootstrap readiness and candidate discovery."""

import argparse
from collections.abc import Sequence
import json
from pathlib import Path
import sys

from flex_photo import __version__
from flex_photo.discovery import DiscoveryError, discover_heic


def _main(argv: Sequence[str] | None) -> int:
    parser = argparse.ArgumentParser(
        prog="flex-photo",
        description="Development environment bootstrap and offline HEIC candidate discovery.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command")
    discovery = commands.add_parser("discover", help="list HEIC filename candidates as JSON")
    discovery.add_argument("source", metavar="SOURCE", type=Path, help="local source directory")
    arguments = parser.parse_args(argv)
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
    print("Development environment bootstrap ready. Photo processing is unavailable.")
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
