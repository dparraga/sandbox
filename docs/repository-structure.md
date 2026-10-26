# Solution design and repository structure

## Implemented design

The `flex_photo` package uses a standard-library Python CLI. `cli.py` owns argument parsing, console JSON and sanitized diagnostics; `discovery.py` owns filesystem traversal. `metadata.py` reads original-capture fields through pinned ExifRead; its [contract](capture-metadata.md) defines the library interface, parser guards and acceptance gates. The [discovery contract](heic-discovery.md) is authoritative for its interfaces, selection rules, failure semantics and limitations. `capture_time.py` converts those fields through the [capture-time contract](capture-time.md). `grouping.py` implements the pure [trip-grouping contract](trip-grouping.md). `selection.py` implements the pure [field-candidate contract](field-selection.md). Recognition/OCR, tied-value resolution, photo movement and monthly JSON are not implemented.

Packaging uses a `src/` layout and hash-pinned setuptools to build a wheel. A digest-pinned, multi-stage Linux container installs that wheel and runs as a nonroot user. SHA-pinned GitHub Actions run installed-package tests on Windows/Linux and restricted container smoke checks. See [setup](bootstrap.md), [test coverage](testing-plan.md), and [automation](github-test-automation.md).

## Repository map

| Location | Purpose / status |
| --- | --- |
| `README.md`, `CONTRIBUTING.md` | Purpose, current scope, setup and contribution navigation. |
| `AGENTS.md`, `CLAUDE.md`, `agents/` | Shared instructions and six role contracts; role files do not launch workers. |
| `.agents/skills/project-documentation/SKILL.md` | Repository-local documentation skill loaded before documentation edits and reviews. |
| `docs/` | Business/technical requirements, design, setup instructions, pipeline, testing, automation and persistent review guidance. |
| `pyproject.toml`, `requirements-build.txt`, `requirements-runtime.txt` | Package configuration and hash-pinned build/runtime dependencies. |
| `src/flex_photo/` | Candidate discovery, bounded capture-metadata reader, pure capture-time conversion, trip grouping and field-candidate selection, CLI, version and module entry point. |
| `tests/unit/` | CLI behavior, discovery traversal/error assertions, capture-metadata/parser-guard checks, capture-time validation, grouping invariants and field-candidate selection. |
| `tests/integration/` | Installed wheel, module/console behavior and no output-file effects outside source root. |
| `tests/performance/` | Separate startup and synthetic discovery measurements; no photo workload. |
| `scripts/` | Repeatable tests, installed-wheel build and restricted-container helpers. |
| `container/Dockerfile`, `.dockerignore` | Multi-stage image, nonroot runtime and allowlisted build context. |
| `.github/workflows/` | Windows/Linux Python tests, reports and Linux container smoke checks. |
| `.github/pull_request_template.md` | Scope, approval, independent review and actual validation evidence. |
| `sample-pictures/` | Ignored local originals and `fixture-manifest.json`; excluded from CI, package and container. |
| `.agent-state/<feature>/` | Ignored laptop-local approval, status, reports, resume instructions and per-agent handoffs. |
| `.venv/`, `build/`, `dist/`, `reports/` | Ignored local environment, package outputs and sanitized validation reports. |

Future recognition/OCR and move/JSON modules, models and publishable processing fixtures are deliberately absent. Native dependency artifacts and JSON schema require later validation/decisions. Keep generated data, downloaded assets and sensitive photos out of tracked history.

## Remaining delivery design

The [integrated delivery plan](delivery-plan.md) is the authoritative proposal for completing offline photo interpretation and the complete batch console workflow. It defines the remaining feature sequence, interfaces, dependency/model and native-license gates, policy recommendations and end-to-end acceptance. These remaining features require explicit approval; existing component contracts remain authoritative for their implemented APIs.

## Project license

The application's own code and documentation use the MIT [LICENSE](../LICENSE). Third-party dependencies, models and binaries retain their own licenses, attribution and notices. MIT does not waive their redistribution obligations or establish codec patent clearance; exact artifact compatibility remains a [delivery gate](delivery-plan.md#dependency-compatibility-and-offline-gates).
