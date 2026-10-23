# Setup and execution

Install the `flex-photo` console application on CPython 3.13 or 3.14. Its CLI provides bootstrap readiness/help/version and [HEIC candidate discovery](heic-discovery.md); the package also provides the internal [capture metadata reader](capture-metadata.md). Future imaging/native dependencies need separate compatibility and license validation.

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
```

The version output is `flex-photo 0.1.0`. The default command prints `Development environment bootstrap ready. Photo processing is unavailable.` Unknown arguments fail with exit code 2. The `discover SOURCE` subcommand inventories candidate paths; there are no destination or OCR options. Rebuild and reinstall the wheel after package changes; use `--force-reinstall` on the install command when testing an updated wheel with the same version. The test acceptance path is wheel installation, not imports from the source tree.

Provisioning the hash-pinned setuptools backend and ExifRead runtime dependency needs package-index access. The application wheel build/install commands above use provisioned assets and `--no-index`; `--no-deps` requires installing `requirements-runtime.txt` first. `pip` comes with the selected environment. No imaging codecs or models are required.

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

`podman` can replace `docker` for these commands; local Podman execution has not been validated. The multi-stage image pins the official Python 3.13 base digest, builds a wheel, and runs the installed CLI as numeric user `10001:10001`. Build needs access to the base-image registry and pinned build/runtime dependencies; runtime checks disable networking. No ports or photo mounts are needed. The context excludes local photos/state, Git, tests and generated reports. These commands exercise readiness/help/version; the automated helper below also checks candidate discovery and installed metadata extraction. They do not establish HEIC decoding/OCR. Exact CI validation status belongs in the feature PR.

For automated CLI, discovery, installed metadata and numeric nonroot checks after the image build:

```powershell
.\.venv\Scripts\python.exe scripts/check_container.py flex-photo:bootstrap
```

The helper mounts disposable public filesystem and metadata-only fixtures read-only. It checks candidate JSON, invalid-source behavior, installed-library capture extraction, a huge-header guard failure, and the pinned ExifRead version and retained license. It verifies source bytes remain unchanged; the fixtures establish no image decodability. It invokes Docker; a Podman-specific helper has not been provided. An unavailable local engine prevents local container validation. Latest-head container evidence belongs in the feature PR; native test success does not substitute for actual restricted container execution.

## Validation and acceptance

Environment acceptance requires wheel installation on supported Windows/Linux runtimes, correct installed CLI/module behavior outside the source root, unit/integration results, accurately labeled repeated startup measurements, successful container smoke checks and independent review. The [testing plan](testing-plan.md) separates this coverage from future processing tests. [GitHub automation](github-test-automation.md) describes CI checks and reports.

Setup outputs `.venv/`, `build/`, `dist/` and generated reports are ignored. Do not commit them or `.agent-state/`. Private `sample-pictures/` originals and inventory are unrelated to bootstrap tests; preserve them through cleanup.
