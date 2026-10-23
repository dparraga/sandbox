# Repository structure

Planning PR #1 is merged. Development environment bootstrap creates the source, packaging, CLI, container and automation below; future processing responsibilities remain unimplemented. [TRD](TRD.md) records approval and unresolved decisions.

| Location | Purpose / status |
| --- | --- |
| `README.md`, `CONTRIBUTING.md` | Purpose, current scope, setup and contribution navigation. |
| `AGENTS.md`, `CLAUDE.md`, `agents/` | Shared instructions and six role contracts; role files do not launch workers. |
| `docs/` | BRD/TRD, bootstrap instructions, pipeline, testing, automation and persistent review guidance. |
| `pyproject.toml`, `requirements-build.txt` | Python package/runtime configuration and hash-pinned build backend; no runtime dependencies. |
| `src/flex_photo/` | Minimal standard-library CLI, version and module entry point. |
| `tests/unit/` | Bootstrap CLI behavior assertions. |
| `tests/integration/` | Installed wheel, module/console behavior and no output-file effects outside source root. |
| `tests/performance/` | Bootstrap startup measurement contract; no photo workload. |
| `scripts/` | Repeatable tests and installed-process startup benchmark. |
| `container/Dockerfile`, `.dockerignore` | Multi-stage image, nonroot runtime and allowlisted build context. |
| `.github/workflows/` | Windows/Linux Python tests, reports and Linux container smoke checks. |
| `.github/pull_request_template.md` | Scope, approval, independent review and actual validation evidence. |
| `sample-pictures/` | Ignored local originals and `fixture-manifest.json`; excluded from CI, package and container. |
| `.agent-state/development-environment-bootstrap/` | Ignored laptop-local approval evidence, status, design/review reports, results and per-agent handoffs. |
| `.venv/`, `build/`, `dist/`, `reports/` | Ignored local environment, package outputs and sanitized validation reports. |

Future recognition/OCR, grouping/selection, move/JSON modules, models and publishable processing fixtures are deliberately absent. Native dependency artifacts and JSON schema require later validation/decisions. Keep generated data, downloaded assets and sensitive photos out of tracked history.

Each agent writes its own handoff; Lead owns overall status. Retain active feature state while its PR is open. After verifying merge into base, stop feature workers and remove only its resolved workspace-contained state directory. Preserve local originals/inventory and permanent docs. Resume on the same laptop using saved state plus actual Git/PR verification.
