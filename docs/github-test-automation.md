# GitHub test automation plan

Status: planned only. This feature creates no executable tests, Dockerfiles, or GitHub Actions workflows. No CI checks are operational or reported as passing.

Testing owns automation; Documentation maintains verified instructions; Review checks tests and instructions; Lead validates actual results. Implement only after application implementation approval and selection of the language, runtime, test framework, dependencies, and container approach.

## Proposed automation

- Run applicable unit, integration, and performance tests when pull requests open or update.
- Support manual execution through GitHub Actions (`workflow_dispatch`).
- Validate Windows on a Windows runner and the Linux container on a suitable Linux runner. Document which suites run in each environment and any approved differences.
- Use the same approved commands locally and in CI where practical. Record dependency/model provisioning separately from offline processing; exercise the processing path without network access.
- Publish test reports, failure diagnostics, and performance measurements with workload and environment details. Keep personal photos, metadata, tokens, and other secrets out of logs and artifacts; use only approved fixtures.
- Report failures visibly. Retention, runner/image versions, permissions, job layout, fork-PR behavior, and required status checks need implementation-time decisions. Do not require secrets for ordinary test execution without an explicit approved need.

No performance pass/fail thresholds or coverage targets are approved. Measurements must identify workload, hardware/runner resources, OS/container image, runtime/dependency/model versions, and measurement method. Establish any proposed limits from representative evidence and obtain approval. Consider hosted-runner time, model downloads, artifact storage, and applicable account allowances without promising free hosting capacity.

## Instructions to deliver with implementation

Documentation must verify and publish these steps against the real workflow, using its actual name and commands:

1. Prerequisites and setup for local Windows tests and Linux container validation, including dependency/model provisioning and offline execution.
2. Exact local commands for unit, integration, and performance suites, fixture preparation, output locations, and safe cleanup.
3. In GitHub, open the repository's **Actions** tab, select the implemented workflow, choose **Run workflow**, select the intended branch and any documented inputs, then start the run.
4. For PR execution, open the PR's checks and the linked workflow run. Explain the expected Windows and container jobs and how to distinguish pending, skipped, failed, and successful results.
5. Open individual jobs and steps to inspect logs; locate and download the actual report/diagnostic/performance artifacts. Explain artifact contents and retention.
6. Investigate failures using the failing command, environment versions, fixture manifest, and diagnostics. Reproduce locally where possible and distinguish application defects from provisioning or infrastructure failures.
7. Explain GitHub's rerun controls for failed jobs or all jobs, applicable permissions, and how a code correction triggers a new run. Preserve the failing evidence rather than treating rerun success alone as a fix.

Until those commands and workflows exist, these are documentation deliverables, not runnable instructions. See [testing-plan.md](testing-plan.md) for requirement coverage and unresolved expectations.
