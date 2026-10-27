# Setup and execution

Install the `flex-photo` console application on CPython 3.13 or 3.14. It provides [HEIC discovery](heic-discovery.md) and an integrated `process` command using separately provisioned upstream native/OCR assets. The [user guide](user-guide.md) describes processing options and asset provisioning.

## Windows setup

Use PowerShell from the repository root with Git and CPython 3.13 or 3.14 installed. The commands below use the Windows Python launcher and 3.13; select `-3.14` instead if that is your installed supported interpreter. Activation is unnecessary, so no PowerShell execution-policy change is needed.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes --only-binary=:all: -r requirements-build.txt
.\.venv\Scripts\python.exe -m pip install --require-hashes --only-binary=:all: -r requirements-runtime.txt
.\.venv\Scripts\python.exe -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir dist .
.\.venv\Scripts\python.exe -m pip install --no-deps --no-index dist/flex_photo-0.1.0-py3-none-any.whl
.\.venv\Scripts\flex-photo.exe
.\.venv\Scripts\flex-photo.exe --help
.\.venv\Scripts\python.exe -m flex_photo --version
.\.venv\Scripts\python.exe -m pip check
```

The version output is `flex-photo 0.1.0`. With no arguments, the command points to `process --help`; it does not process files. Unknown arguments fail with exit code 2. `discover SOURCE` inventories candidate paths; `process --help` lists explicit folder and OCR options. Rebuild and reinstall the wheel after package changes; use `--force-reinstall` when installing an updated wheel with the same version. Acceptance uses wheel installation, not imports from the source tree.

Provisioning the hash-pinned build/runtime dependencies needs package-index access. The wheel build/install commands use provisioned assets and `--no-index`; `--no-deps` requires installing `requirements-runtime.txt` first. `pip` comes with the environment. Discovery needs no OCR assets; processing needs the [local engine/model setup](user-guide.md#install-on-windows). One-time online provisioning is allowed; processing then uses local assets offline. Artifact-entry review has passed under the [recorded constraints](offline-photo-interpretation.md); candidate probes do not establish full application acceptance. Our source/wheel/source Dockerfiles do not convey a native wheelhouse, portable OCR bundle or prebuilt image. Retain upstream licenses/notices; binary redistribution requires a separate assessment.

On Linux, create `.venv` using `python3 -m venv .venv`; replace `.\.venv\Scripts\python.exe` with `.venv/bin/python` and the console path with `.venv/bin/flex-photo`. The checked-in CI exercises Windows and Ubuntu on Python 3.13/3.14.

## Tests and measurements

After building and installing the wheel, run from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts/build_wheel.py
.\.venv\Scripts\python.exe scripts/run_checks.py --wheel dist/flex_photo-0.1.0-py3-none-any.whl
```

`build_wheel.py` rebuilds and force-reinstalls exactly one generated wheel using the provisioned backend, without an index. If `dist/` contains multiple `flex_photo-*.whl` versions, move stale generated artifacts aside before retrying; do not remove private originals or feature state. `run_checks.py` runs unit and installed integration suites, then separate startup and discovery benchmarks; nonzero suite/benchmark outcomes fail the runner. Use `--reports <directory>` to select a different report location. Default sanitized reports are `reports/unit.log`, `reports/integration.log`, `reports/bootstrap-startup.json` and `reports/discovery-performance.json`.

The startup report measures ten fresh installed-module processes after one warmup and records interpreter/platform, command, sample count and min/median/max elapsed milliseconds. This is warm-cache process startup, not cold startup, OCR throughput, memory profiling or application processing. There is no performance pass/fail threshold. Timings vary with laptop/runner load; compare like environments. Bootstrap tests do not open HEIC samples.

The discovery report measures an installed CLI process on a synthetic tree: 1,000 candidate and 1,000 ignored zero-byte files, 40 directories below the root, maximum directory depth two. Construction is excluded; construction/validation warm the cache. It includes process spawn, traversal and JSON serialization after one warmup, with ten measured repetitions. It does not measure cold-cache I/O, photo decoding/OCR, memory or container performance, and has no speed threshold. To run it separately:

```powershell
.\.venv\Scripts\python.exe tests/performance/benchmark_discovery.py reports/discovery-performance.json
```

## Container

Use a Linux container engine. Podman is an open-source option; Docker commands are shown below and require an available engine. Docker Desktop has usage-dependent terms. Build from the repository root so the allowlisted context is applied:

```powershell
docker build --file container/Dockerfile --tag flex-photo:bootstrap .
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges flex-photo:bootstrap
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges flex-photo:bootstrap --help
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges flex-photo:bootstrap --version
```

`podman` can replace `docker` for these commands; local Podman execution has not been validated. The multi-stage source Dockerfile defaults to the pinned official Python 3.13 bookworm image, builds a wheel and provisions the reviewed bookworm OCR engine and hash-verified model. CI also builds the pinned 3.14 base through `PYTHON_IMAGE`. Runtime uses numeric user `10001:10001`. Builds need registry/dependency/model access; processing then uses local assets. No ports are needed. The context allowlists application files and public artifact-probe fixtures, excluding private photos/state, Git and generated reports. The commands above exercise readiness/help/version; they do not establish dashboard OCR accuracy. Latest-head CI evidence belongs in the PR.

For automated CLI, discovery, installed metadata and numeric nonroot checks after the image build:

```powershell
.\.venv\Scripts\python.exe scripts/check_container.py flex-photo:bootstrap
```

The helper mounts disposable public fixtures and tests read-only. It checks candidate inventory, metadata/time/grouping/selection composition, parser guards and dependency notice retention, then runs installed interpretation and batch integration with local engine/model assets. Native tests use `--memory 1g` and a bounded writable `/tmp`; networking remains disabled, root remains read-only and execution nonroot. Corrupt/blank HEIC checks and resource/lock tests establish mechanics rather than real-dashboard accuracy. The helper invokes Docker; a Podman-specific helper has not been provided. An unavailable engine prevents local validation. Record actual container results separately from native tests and candidate probes.

## Validation and acceptance

Environment acceptance requires wheel installation on supported Windows/Linux runtimes, correct installed CLI/module behavior outside the source root, unit/integration results, accurately labeled repeated startup measurements, successful container smoke checks and independent review. The [testing plan](testing-plan.md) separates this coverage from integrated application acceptance. [GitHub automation](github-test-automation.md) describes CI checks and reports.

Setup outputs `.venv/`, `build/`, `dist/` and generated reports are ignored. Do not commit them or `.agent-state/`. Private `sample-pictures/` originals and inventory are unrelated to bootstrap tests; preserve them through cleanup.

## WSL 2 for Linux validation

In an elevated PowerShell window, run `wsl --install --distribution Ubuntu --no-launch`. Save work and restart Windows if the installer requests it; the project never restarts the laptop automatically. After restarting, run the same install command if Ubuntu is not yet listed, then launch `wsl --distribution Ubuntu` and complete its Linux account setup. Verify `wsl --list --verbose` shows Ubuntu using version 2. Follow [Microsoft's installation guide](https://learn.microsoft.com/en-us/windows/wsl/install) if the machine reports missing virtualization support after the restart.

Verify read access to this checkout with `wsl --distribution Ubuntu -- test -r /mnt/c/Parraga/Code/sandbox/AGENTS.md`, adjusting the path for another checkout. Keep Windows and Linux build environments separate. Do not run source-writing agents simultaneously against the same files from both operating systems, reuse the Windows virtual environment in Linux, or send private samples to CI. Install Linux/container tooling only after WSL is operational. Record WSL-native, WSL-container and hosted CI results separately; WSL installation alone does not validate the application.

For Ubuntu validation, install the distro engine and Python environment tooling inside WSL:

```sh
sudo apt-get update
sudo apt-get install --no-install-recommends docker.io python3-venv
sudo systemctl start docker
sudo docker version
python3 --version
```

These use [Ubuntu's Docker package](https://ubuntu.com/server/docs/how-to/containers/docker-for-system-admins/), not Docker Desktop. Choose a supported Python 3.13/3.14 interpreter for the application environment. Create a separate Linux virtual environment; then use the hash-pinned setup requirements above. The source Dockerfile retains the reviewed bookworm OCR version even when the host Ubuntu version differs. The container helper uses Docker and accepts the image tag as its argument; run it under a user with engine access, using `sudo` where needed.
