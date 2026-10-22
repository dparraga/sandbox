"""Console entry point; photo processing is not implemented yet."""

import argparse
from collections.abc import Sequence

from flex_photo import __version__


def main(argv: Sequence[str] | None = None) -> int:
    """Parse bootstrap options and report readiness without accessing files."""
    parser = argparse.ArgumentParser(
        prog="flex-photo",
        description="Development environment bootstrap for the offline photo organizer.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.parse_args(argv)
    print("Development environment bootstrap ready. Photo processing is unavailable.")
    return 0
