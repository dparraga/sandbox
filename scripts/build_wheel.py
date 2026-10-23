"""Build one wheel offline using the already provisioned backend."""

from pathlib import Path
import subprocess
import sys


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
                    "--no-index", "--wheel-dir", str(root / "dist"), str(root)], check=True)
    wheels = list((root / "dist").glob("flex_photo-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError("Expected exactly one flex-photo wheel; use a clean dist directory")
    subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", "--no-index",
                    "--force-reinstall", str(wheels[0])], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
