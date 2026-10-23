"""Run installed-wheel checks, preserving sanitized diagnostic reports and exits."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--reports", type=Path, default=Path("reports"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    reports = args.reports.resolve()
    reports.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["FLEX_PHOTO_WHEEL"] = str(args.wheel.resolve(strict=True))
    failed = False
    for suite in ("unit", "integration"):
        command = [sys.executable, "-m", "unittest", "discover", "-s", str(root / "tests" / suite), "-v"]
        try:
            result = subprocess.run(command, cwd=root, env=environment, capture_output=True,
                                    text=True, timeout=120, check=False)
            status, log = result.returncode, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            status, log = 1, "Suite exceeded the 120 second timeout.\n"
        # Do not publish local usernames, checkout paths, or temporary directories.
        for path, label in [(str(root), "<checkout>"), (str(Path.home()), "<home>"),
                            (tempfile.gettempdir(), "<temp>")]:
            log = log.replace(path, label).replace(path.replace("\\", "/"), label)
        log = f"{suite} suite; exit status {status}\n" + log
        (reports / f"{suite}.log").write_text(log, encoding="utf-8")
        print(log, end="")
        failed |= status != 0
    result = subprocess.run([sys.executable, str(root / "tests/performance/benchmark_startup.py"),
                             str(reports / "bootstrap-startup.json")], cwd=root,
                            env=environment, timeout=240, check=False)
    failed |= result.returncode != 0
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
