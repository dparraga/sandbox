# Development environment bootstrap

This feature installs a minimal `flex-photo` CLI. It reports readiness, help and version; photo processing is unavailable. Python 3.13 and 3.14 are supported for bootstrap; future imaging/native dependencies need separate validation. Existing licensing and open business policies remain in [TRD](TRD.md).

## Windows setup

Use PowerShell from the repository root with Git and CPython 3.13 or 3.14 installed. The commands below use the Windows Python launcher and 3.13; select `-3.14` instead if that is your installed supported interpreter. Activation is unnecessary, so no PowerShell execution-policy change is needed.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes --only-binary=:all: -r requirements-build.txt
.\.venv\Scripts\python.exe -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir dist .
.\.venv\Scripts\python.exe -m pip install --no-deps --no-index dist/flex_photo-0.1.0-py3-none-any.whl
.\.venv\Scripts\flex-photo.exe
.\.venv\Scripts\flex-photo.exe --help
.\.venv\Scripts\python.exe -m flex_photo --version
```

The version output is `flex-photo 0.1.0`. The default command prints `Development environment bootstrap ready. Photo processing is unavailable.` Unknown arguments fail with exit code 2. There are no source/destination, scanning or OCR options. Rebuild and reinstall the wheel after package changes; use `--force-reinstall` on the install command when testing an updated wheel with the same version. The test acceptance path is wheel installation, not imports from the source tree.

Only provisioning the hash-pinned setuptools build backend needs package-index access. Wheel build/install commands above use local assets and `--no-index`; application runtime dependencies are empty. `pip` comes with the selected environment. Do not install imaging libraries/models for this feature.

On Linux, create `.venv` using `python3 -m venv .venv`; replace `.\.venv\Scripts\python.exe` with `.venv/bin/python` and the console path with `.venv/bin/flex-photo`. The checked-in CI exercises Windows and Ubuntu on Python 3.13/3.14.

## Tests and startup measurements

After building and installing the wheel, run from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts/build_wheel.py
.\.venv\Scripts\python.exe scripts/run_checks.py --wheel dist/flex_photo-0.1.0-py3-none-any.whl
```

`build_wheel.py` rebuilds and force-reinstalls exactly one generated wheel using the provisioned backend, without an index. If `dist/` contains multiple `flex_photo-*.whl` versions, move stale generated artifacts aside before retrying; do not remove private originals or feature state. `run_checks.py` runs unit and installed integration suites, then the startup benchmark; nonzero suite/benchmark outcomes fail the runner. Use `--reports <directory>` to select a different report location. Default sanitized reports are `reports/unit.log`, `reports/integration.log` and `reports/bootstrap-startup.json`.

The startup report measures ten fresh installed-module processes after one warmup and records interpreter/platform, command, sample count and min/median/max elapsed milliseconds. This is warm-cache process startup, not cold startup, OCR throughput, memory profiling or application processing. There is no performance pass/fail threshold. Timings vary with laptop/runner load; compare like environments. Bootstrap tests do not open HEIC samples.

## Container

Use a Linux container engine. Podman is an open-source option; Docker commands are shown below and require an available engine. Docker Desktop has usage-dependent terms. Build from the repository root so the allowlisted context is applied:

```powershell
docker build --file container/Dockerfile --tag flex-photo:bootstrap .
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges flex-photo:bootstrap
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges flex-photo:bootstrap --help
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges flex-photo:bootstrap --version
```

`podman` can replace `docker` for these commands; local Podman execution has not been validated. The multi-stage image pins the official Python 3.13 base digest, builds a wheel, and runs the installed CLI as numeric user `10001:10001`. Build needs access to the base-image registry and pinned build dependency; runtime checks disable networking. No ports or photo mounts are needed. The context excludes local photos/state, Git, tests and generated reports. This establishes bootstrap execution only, not offline HEIC/OCR processing. Exact CI validation status belongs in the feature PR.

For automated default/help/version/invalid-option and numeric nonroot checks after the image build:

```powershell
.\.venv\Scripts\python.exe scripts/check_container.py flex-photo:bootstrap
```

This helper invokes Docker; a Podman-specific helper has not been provided. Local Docker/Podman was unavailable during development, so container acceptance requires the actual CI result rather than a local success claim.

## Validation and acceptance

Bootstrap acceptance requires wheel installation on supported Windows/Linux runtimes, correct installed CLI/module behavior outside the source root, unit/integration results, accurately labeled repeated startup measurements, successful container smoke checks and independent review. The [testing plan](testing-plan.md) separates this coverage from future processing tests. [GitHub automation](github-test-automation.md) describes CI checks and reports.

Setup outputs `.venv/`, `build/`, `dist/` and generated reports are ignored. Do not commit them or `.agent-state/`. Private `sample-pictures/` originals and inventory are unrelated to bootstrap tests; preserve them through cleanup.
