"""Warm-cache installed CLI discovery plus process spawn on a public synthetic tree."""

import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time


def measure(output: Path, repetitions: int = 10) -> None:
    if repetitions < 10:
        raise ValueError("At least ten measured repetitions are required")
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    samples = []
    with tempfile.TemporaryDirectory(prefix="flex-discovery-benchmark-") as directory:
        source = Path(directory) / "source"
        expected = []
        for group in range(20):
            leaf = source / f"group-{group:02d}" / "leaf"
            leaf.mkdir(parents=True)
            for index in range(50):
                (leaf / f"photo-{index:02d}.HEIC").touch()
                (leaf / f"other-{index:02d}.txt").touch()
                expected.append(f"group-{group:02d}/leaf/photo-{index:02d}.HEIC")
        command = [sys.executable, "-m", "flex_photo", "discover", str(source)]
        for iteration in range(repetitions + 1):
            started = time.perf_counter()
            result = subprocess.run(command, cwd=directory, env=environment, capture_output=True,
                                    text=True, timeout=30, check=False)
            elapsed = time.perf_counter() - started
            if result.returncode or result.stderr or json.loads(result.stdout) != expected:
                raise RuntimeError("Discovery benchmark inventory failed validation")
            if iteration:
                samples.append(elapsed * 1000)
    report = {
        "measurement": "warm-cache installed CLI discovery plus process spawn",
        "limitations": "Construction excluded; cache warmed by construction and validation. Includes process spawn and console serialization. Not cold-cache, photo/OCR throughput, memory, or container performance. No speed threshold.",
        "workload": {"candidate_files": 1000, "other_files": 1000, "file_bytes": 0,
                     "directories_below_root": 40, "maximum_directory_depth": 2},
        "platform": platform.platform(), "architecture": platform.machine(),
        "python": platform.python_version(), "implementation": platform.python_implementation(),
        "logical_cpu_count": os.cpu_count(),
        "runner": {key: os.environ[key] for key in ("RUNNER_OS", "RUNNER_ARCH", "ImageOS", "ImageVersion") if key in os.environ},
        "command": ["<installed-python>", "-m", "flex_photo", "discover", "<synthetic-source>"],
        "warmup_count": 1, "sample_count": repetitions, "timeout_seconds": 30,
        "unit": "milliseconds", "samples": samples,
        "minimum": min(samples), "median": statistics.median(samples), "maximum": max(samples),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    measure(Path(sys.argv[1]) if len(sys.argv) == 2 else Path("reports/discovery-performance.json"))
