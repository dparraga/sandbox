# Solution design and repository structure

## Implemented design

The `flex_photo` package uses a standard-library Python CLI. `cli.py` owns argument parsing, console JSON and sanitized diagnostics; `discovery.py` owns filesystem traversal. `metadata.py` reads original-capture fields through pinned ExifRead under its [contract](capture-metadata.md). `capture_time.py`, `grouping.py` and `selection.py` implement their pure [timestamp](capture-time.md), [grouping](trip-grouping.md) and [candidate-selection](field-selection.md) contracts. `capture_fallback.py` resolves the authorized metadata/creation/filename hierarchy with pinned Los Angeles rules. The `interpretation.py` interface uses a contained native worker for four-field OCR; `batch.py` composes preflight, exact value resolution, private identity/recovery state, movement and monthly output. Component contracts and the testing plan define required acceptance and coverage limits.

Packaging uses a `src/` layout and hash-pinned setuptools to build a wheel. A digest-pinned, multi-stage Linux container installs that wheel and runs as a nonroot user. SHA-pinned GitHub Actions run installed-package tests on Windows/Linux and restricted container smoke checks. See [setup](bootstrap.md), [test coverage](testing-plan.md), and [automation](github-test-automation.md).

## Repository map

| Location | Purpose / status |
| --- | --- |
| `README.md`, `CONTRIBUTING.md` | Purpose, current scope, setup and contribution navigation. |
| `AGENTS.md`, `CLAUDE.md`, `agents/` | Shared instructions and six role contracts; role files do not launch workers. |
| `.agents/skills/project-documentation/SKILL.md` | Repository-local documentation skill loaded before documentation edits and reviews. |
| `docs/` | Business/technical requirements, design, setup instructions, pipeline, testing, automation and persistent review guidance. |
| `pyproject.toml`, `requirements-build.txt`, `requirements-runtime.txt` | Package configuration and hash-pinned build/runtime dependencies. |
| `src/flex_photo/` | CLI, discovery, metadata/time/grouping/selection, contained interpretation and recoverable batch composition. |
| `tests/unit/` | Component semantics, authored reading/batch filesystem scenarios and fault/recovery checks. |
| `tests/integration/` | Installed wheel/module/console, native resource controls, source preservation, locks and command failures. |
| `tests/performance/` | Separate startup and synthetic discovery measurements; no photo workload. |
| `scripts/` | Repeatable tests, installed-wheel build and restricted-container helpers. |
| `container/Dockerfile`, `.dockerignore` | Multi-stage image, nonroot runtime and allowlisted build context. |
| `.github/workflows/` | Windows/Linux Python tests, reports and Linux container smoke checks. |
| `.github/pull_request_template.md` | Scope, approval, independent review and actual validation evidence. |
| `sample-pictures/` | Ignored local originals and `fixture-manifest.json`; excluded from CI, package and container. |
| `.agent-state/<feature>/` | Ignored laptop-local approval, status, reports, resume instructions and per-agent handoffs. |
| `.venv/`, `build/`, `dist/`, `reports/` | Ignored local environment, package outputs and sanitized validation reports. |

Models and native binaries are provisioned from upstream rather than bundled. Keep generated data, downloaded assets and sensitive photos out of tracked history; public synthetic fixtures establish mechanics rather than real-layout accuracy.

## Remaining delivery design

The [integrated delivery plan](delivery-plan.md) defines approved batch composition, identity, recovery and end-to-end acceptance. Artifact-entry and architecture reviews passed; installed-package validation remains distinct from source presence. Existing component contracts remain authoritative for their APIs.

## Project license

The application's own code and documentation use the MIT [LICENSE](../LICENSE). Third-party dependencies, models and binaries retain their own licenses, attribution and notices. MIT does not waive redistribution obligations or establish codec patent clearance; the [artifact contract](offline-photo-interpretation.md) records the scoped deployment route and gates.
