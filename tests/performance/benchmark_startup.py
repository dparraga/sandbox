"""Warm-cache installed CLI process startup; no photo-processing benchmark."""

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
    command = [sys.executable, "-m", "flex_photo"]
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    samples = []
    with tempfile.TemporaryDirectory(prefix="flex benchmark é ") as directory:
        for iteration in range(repetitions + 1):
            started = time.perf_counter()
            result = subprocess.run(command, cwd=directory, env=environment, capture_output=True,
                                    text=True, timeout=15, check=False)
            elapsed = time.perf_counter() - started
            if result.returncode != 0 or result.stderr or "bootstrap" not in result.stdout.lower() or "unavailable" not in result.stdout.lower():
                raise RuntimeError("Installed bootstrap command did not return expected readiness output")
            if list(Path(directory).iterdir()):
                raise RuntimeError("Bootstrap command created files")
            if iteration:
                samples.append(elapsed * 1000)
    report = {
        "measurement": "warm-cache installed CLI process startup",
        "limitations": "Includes process spawn; not cold startup, OCR, photo throughput, memory, or container performance. No speed threshold.",
        "platform": platform.platform(), "architecture": platform.machine(),
        "logical_cpu_count": os.cpu_count(), "processor": platform.processor(),
        "runner": {key: os.environ[key] for key in ("RUNNER_OS", "RUNNER_ARCH", "ImageOS", "ImageVersion")
                   if key in os.environ},
        "python": platform.python_version(), "implementation": platform.python_implementation(),
        "interpreter": Path(sys.executable).name,
        "command": ["<installed-python>", "-m", "flex_photo"],
        "warmup_count": 1, "sample_count": repetitions, "timeout_seconds": 15,
        "unit": "milliseconds", "samples": samples,
        "minimum": min(samples), "median": statistics.median(samples), "maximum": max(samples),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    measure(Path(sys.argv[1]) if len(sys.argv) == 2 else Path("reports/bootstrap-startup.json"))
