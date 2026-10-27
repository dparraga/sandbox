# Review guidance

Every feature requires independent Review before a PR is created. Review architecture proposals as well as completed changes; the author cannot supply their own independent review. Lead resolves assignments and validates the evidence. Planning or documentation approval does not authorize application implementation.

## Persistent checklist

- Scope and correctness: match approved requirements and decisions; preserve unrelated changes; expose unresolved behavior instead of inventing it. Check first-to-last trip limits, one entry per trip, per-field latest-clear selection, earlier-value retention, and JSON null behavior where relevant.
- Decision consistency: compare open questions with confirmed user decisions and approved contracts. Preserve settled choices; ask only about details that remain unresolved.
- Outcome classification: distinguish normal nonmatches and absent/unclear fields from processing failures. Preserve earlier clear values or null; do not let broad failure wording override field rules.
- Incremental outputs: check existing-entry preservation and duplicate prevention for exact repeats, subsets, observations that change existing group partitions, and interrupted retries. Persist enough planned output to recover after source movement; hashes alone cannot reconstruct readings. Make matching conflicts and recovery guarantees explicit before adopting a policy.
- Data fidelity: keep only the requested readings and metadata-derived trip date; distinguish recognition anchors from retained observations and exclude unrelated dashboard data. Verify conversions, time zones, boundaries, cross-month handling, and filename/move behavior only against approved decisions and fixtures.
- Safety and security: inspect filesystem handling, move failure/recovery risks, logging, secrets, fixture privacy, dependency/model provenance, and offline processing. Confirm no external API is required during processing.
- Performance: review algorithm and resource use against measured workload/environment evidence. Do not invent thresholds or claim unrun measurements.
- Maintainability and best practices: prefer the simplest approved design; review interfaces, error handling, dependencies, portability, and configuration without adding features.
- Tests: check requirement coverage, meaningful assertions, approved expected readings, Windows/container execution, offline validation, failure cases, and actual local evidence before implementation PR creation. Confirm CI plans are clearly distinguished from operational checks.
- Build and automation paths: verify workflow/container commands name the actual Dockerfile and checked-in helpers. Rebuild/reinstall the final package after README or package-metadata changes before validating artifact contents.
- Documentation: load [project-documentation](../.agents/skills/project-documentation/SKILL.md); check purpose separation, authoritative references, current-state accuracy, concision and agreement with code/evidence. Scan copyable Windows commands for unexpected control characters and verify paths; verify instructions against actual behavior; keep BRD/TRD, structure, setup, test guidance, and approval status consistent. Planning documents must label proposals and open questions.
- Text encoding: inspect changed text for mojibake, replacement characters and unexpected control characters. Verify intended Unicode characters in examples, fixtures and packaged metadata; rerun affected checks after correction.
- Licensing and cost: verify free, open-source dependency/model licenses, redistribution compatibility, and applicable runtime/hosting/storage costs. Keep the application's MIT license distinct from dependency/model/binary terms; verify copyright attribution and retained third-party notices in built artifacts.
- Process and hygiene: confirm feature branch, independent review and recheck, required approval gates, and exclusion of `.agent-state/` from staging and the PR. Feature completion requires a verified merge; never merge automatically.

Apply each category proportionately and record exclusions with reasons. Check installed CLI/package correctness, measurement labeling and container/CI evidence. Distinguish authored batch scenarios, native resource/mechanics tests and private dashboard accuracy; one cannot substitute for the others.

## PR feedback and lessons

Lead assigns each PR comment to the relevant role. Correct code, tests, or documentation on the same feature branch, rerun affected tests, and obtain Review's independent evaluation of corrections before pushing. Lead coordinates responses and verifies resolution.

Review evaluates every PR comment for something missed. When a comment reveals a reusable gap, update this tracked document with the lesson and an improved check. Distinguish a confirmed requirement or defect from an optional preference; do not promote every preference into a requirement. Link the real PR/comment and evidence when available. Temporary investigation and raw reports remain in ignored local state.

- When CLI readiness text changes, search its consumers, including performance and container helpers, and run the affected installed checks. Passing unit/integration suites can miss stale benchmark assertions, as [PR 8](https://github.com/dparraga/sandbox/pull/8) and [CI run 40538084077](https://github.com/dparraga/sandbox/actions/runs/40538084077) showed.
