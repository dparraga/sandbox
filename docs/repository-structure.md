# Proposed repository structure

Status: planning foundation. The directories below describe intended responsibilities; they do not select a language, runtime, test framework, OCR engine, exact schema, or container image. Create application assets only after explicit implementation approval.

| Location | Purpose / status |
| --- | --- |
| `README.md` | Purpose, planning status, and navigation. |
| `AGENTS.md` | Shared agent and collaboration rules. |
| `CLAUDE.md` | Entry point referring to shared rules; does not launch workers. |
| `agents/` | Lead, Architect, Implementation, Testing, Documentation, and Review role definitions. |
| `docs/` | BRD, TRD, pipeline, repository plan, testing, automation, and persistent review guidance. |
| `.github/pull_request_template.md` | Reviewable scope, approvals, validation evidence, and open questions. |
| `src/` | Future application source; internal organization follows the approved design. |
| `tests/unit/` | Future grouping, field selection, and approved data-conversion/serialization tests. |
| `tests/integration/` | Future scan-to-output, offline, move, and portability tests. |
| `tests/performance/` | Future representative workload measurements and environment records. |
| `tests/fixtures/` | Only approved, publishable fixture manifests/assets and verified expectations; personal originals remain outside public history. |
| `scripts/` | Future repeatable development/test helpers if needed. |
| `container/` | Future container build/validation assets after design approval. |
| `.github/workflows/` | Future PR and manual Windows/container test automation. No workflows are created in this feature. |
| `.agent-state/planning-foundation/` | Ignored, laptop-local phase status, reports, assignments, approval evidence, test records, and per-agent handoffs. Never included in PRs. |

Names and locations of runtime-specific manifests, lockfiles, model assets/caches, and generated outputs remain subject to the approved technical design. Keep generated data, downloaded models, sensitive photos, and temporary outputs out of tracked history unless their inclusion is explicitly justified and approved.

Each agent writes its own handoff; Lead owns overall status. Retain local state while the PR is open. After verifying merge into the base branch, stop the feature's workers and delete only that feature's state. Resume on the same laptop by reading saved state and inspecting actual Git/filesystem state before acting; unsaved context is not recoverable by promise.
