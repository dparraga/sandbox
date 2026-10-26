"""Bounded candidate-asset evaluation, never application adoption or accuracy proof.

Use --provision reports/interpretation-assets, then --probe that same directory.
Provisioning needs network access; probing makes no intentional network requests,
but is not OS network isolation. --tesseract must name an explicitly provisioned
executable; its provenance/security/licenses remain separate audit requirements.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import tempfile
import urllib.request
import venv

MANIFEST = Path(__file__).resolve().parents[1] / "tests/assets/interpretation-candidates.json"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verified(path, entry):
    if path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
        raise RuntimeError("Asset size or SHA-256 mismatch: " + entry["filename"])


def download(folder, entry):
    target = folder / entry["filename"]
    if target.exists():
        verified(target, entry)
        return target
    temporary = target.with_suffix(target.suffix + ".part")
    deadline = time.monotonic() + 120
    try:
        with urllib.request.urlopen(entry["url"], timeout=30) as response, temporary.open("wb") as out:
            count = 0
            while chunk := response.read(1024 * 1024):
                count += len(chunk)
                if count > entry["bytes"] or time.monotonic() > deadline:
                    raise RuntimeError("Bounded asset download exceeded limit")
                out.write(chunk)
        verified(temporary, entry)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def python_path(folder):
    return folder / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def provision(folder, manifest):
    abi = f"cp{sys.version_info.major}{sys.version_info.minor}"
    system = platform.system()
    if platform.machine().lower() not in {"amd64", "x86_64"} or abi not in {"cp313", "cp314"}:
        raise RuntimeError("Evaluation requires x86_64 CPython 3.13 or 3.14")
    if sys.implementation.name != "cpython" or sysconfig_free_threaded():
        raise RuntimeError("Evaluation requires standard non-free-threaded CPython")
    selected = [item for item in manifest["wheels"] if item["python"] == abi and item["platform"] == system]
    if len(selected) != 2:
        raise RuntimeError("No exact candidate pair for this platform")
    wheels = folder / "wheels"
    wheels.mkdir(exist_ok=True)
    paths = [download(wheels, item) for item in selected]
    models = folder / "models"
    models.mkdir(exist_ok=True)
    download(models, manifest["model"])
    interpreter = python_path(folder)
    if not interpreter.exists():
        venv.EnvBuilder(with_pip=True).create(folder / "venv")
    # pip's wheel-tag validation also prevents reuse under an incompatible ABI.
    subprocess.run([str(interpreter), "-I", "-m", "pip", "install", "--no-index", "--no-deps",
                    "--only-binary=:all:", "--force-reinstall", *map(str, paths)], check=True, timeout=120)
    (folder / "provision.json").write_text(json.dumps({"python": abi, "platform": system,
        "artifacts": selected, "model": manifest["model"], "adopted": False}, indent=2) + "\n")


def sysconfig_free_threaded():
    import sysconfig
    return bool(sysconfig.get_config_var("Py_GIL_DISABLED"))


def worker(folder, manifest, executable, output):
    from PIL import Image, ImageDraw, ImageFont, __version__ as pillow_version
    import pillow_heif

    native = pillow_heif.libheif_info()
    if (pillow_version != "13.0.0" or pillow_heif.__version__ != "1.8.1"
            or native.get("libheif") != "1.23.6"
            or native.get("decoders", {}).get("libde265") != "libde265 HEVC decoder, version 1.1.3"):
        raise RuntimeError("Unexpected candidate Pillow/pillow-heif/libheif/libde265 versions")
    model = folder / "models" / manifest["model"]["filename"]
    verified(model, manifest["model"])
    fixture = MANIFEST.parent / manifest["synthetic_fixture"]["filename"]
    verified(fixture, manifest["synthetic_fixture"])
    pillow_heif.options.DISABLE_SECURITY_LIMITS = False
    pillow_heif.options.THUMBNAILS = False
    pillow_heif.options.DEPTH_IMAGES = False
    pillow_heif.options.AUX_IMAGES = False
    pillow_heif.options.DECODE_THREADS = 1
    decoded = pillow_heif.open_heif(fixture, convert_hdr_to_8bit=True)
    if len(decoded) != 1 or decoded.size != (64, 64) or decoded.mode != "RGB":
        raise RuntimeError("Synthetic HEVC fixture dimensions/frame count/mode changed")
    extrema = decoded.to_pillow().getextrema()
    if len(extrema) != 3 or any(low < 250 or high > 255 for low, high in extrema):
        raise RuntimeError("Synthetic HEVC fixture is not within white tolerance")
    report = {"status": "candidate evaluation only", "python": sys.version,
              "platform": platform.platform(), "pillow": pillow_version,
              "pillow_heif": pillow_heif.__version__, "native": native,
              "synthetic_hevc_decode": {"sha256": digest(fixture), "size": list(decoded.size),
                  "mode": decoded.mode, "channel_extrema": extrema, "within_white_tolerance": True},
              "model_sha256": digest(model), "network_isolation": False,
              "adoption_or_accuracy_proof": False, "tesseract": {"status": "unavailable: no executable supplied"}}
    if executable:
        executable = executable.resolve(strict=True)
        image = Image.new("RGB", (500, 100), "white")
        ImageDraw.Draw(image).text((20, 15), "HELLO", fill="black", font=ImageFont.load_default(size=48))
        with tempfile.TemporaryDirectory(prefix="flex-photo-assets-") as temporary:
            ppm = Path(temporary) / "synthetic-hello.ppm"
            image.save(ppm)
            env = {key: value for key, value in os.environ.items() if not key.startswith(("TESS", "OMP"))}
            env["OMP_THREAD_LIMIT"] = "1"
            # Keep OS loader paths but do not search PATH for the executable.
            version = subprocess.run([str(executable), "--version"], capture_output=True, text=True,
                                     cwd=ppm.parent, env=env, timeout=15)
            result = subprocess.run([str(executable), str(ppm), "stdout", "--tessdata-dir", str(model.parent),
                                     "-l", "eng", "--oem", "1", "--psm", "6"],
                                    capture_output=True, text=True, cwd=ppm.parent, env=env, timeout=15)
        report["tesseract"] = {"version_returncode": version.returncode,
            "version": version.stdout + version.stderr, "executable_sha256": digest(executable),
            "returncode": result.returncode, "synthetic_text": result.stdout.strip(),
            "synthetic_expected": "HELLO", "synthetic_match": result.stdout.strip() == "HELLO"}
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if executable and (version.returncode or result.returncode or result.stdout.strip() != "HELLO"):
        return 1
    return 0 if executable else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--provision", type=Path, metavar="DIRECTORY")
    modes.add_argument("--probe", type=Path, metavar="DIRECTORY")
    modes.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--tesseract", type=Path, help="explicit evaluation executable; missing is a gap, exit 2")
    parser.add_argument("--output", type=Path, help="probe JSON destination (default DIRECTORY/probe.json)")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    folder = (args.provision or args.probe or args.worker).resolve()
    output = (args.output or folder / "probe.json").resolve()
    if args.provision:
        folder.mkdir(parents=True, exist_ok=True)
        provision(folder, manifest)
        return 0
    if args.worker:
        return worker(folder, manifest, args.tesseract, output)
    command = [str(python_path(folder)), "-I", str(Path(__file__).resolve()), "--worker", str(folder), "--output", str(output)]
    if args.tesseract:
        command.extend(["--tesseract", str(args.tesseract.resolve())])
    return subprocess.run(command, check=False, timeout=60).returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Candidate evaluation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
