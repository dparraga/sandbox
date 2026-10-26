# GitHub test automation

Workflow **Bootstrap checks** in `.github/workflows/bootstrap.yml` validates installed CLI, discovery, capture-metadata, capture-time, internal grouping and field-candidate behavior. Private fixtures are excluded. Actual latest-head outcomes belong in the feature PR; workflow configuration alone does not prove a passing run.

## Jobs and evidence

- **Native ubuntu-latest Python 3.13/3.14** and **Native windows-latest Python 3.13/3.14** create isolated environments, provision hash-pinned build/runtime dependencies, build/install the wheel, run unit/integration checks and measure warm-cache installed-module startup and synthetic discovery separately. The four matrix jobs use the same `scripts/build_wheel.py` and `scripts/run_checks.py` documented in [bootstrap instructions](bootstrap.md).
- **Linux container smoke** builds `container/Dockerfile` and runs `scripts/check_container.py` against default/help/version/invalid arguments and read-only mounted public filesystem/metadata-only fixtures. It checks installed metadata extraction, capture-time conversion, grouping and field-candidate selection, a huge-header guard failure and the pinned dependency version/license. Runtime uses network disabled, read-only filesystem, dropped capabilities, no-new-privileges and nonroot user. This exercises offline CLI, candidate discovery and installed-library metadata extraction/conversion/grouping/field-candidate selection; no Linux HEIC decoding or OCR is established.

Native jobs upload named reports `unit.log`, `integration.log`, `bootstrap-startup.json` and `discovery-performance.json` as `bootstrap-<runner>-python-<version>` artifacts, retained seven days. Only these files are uploaded. Upload is attempted even on failure; a failure before report creation can produce a missing-file warning and no artifact. Container evidence remains in job logs. Logs/reports must not contain private photos/metadata, secrets or temporary feature state.

No processing-performance thresholds or coverage goals are approved. Startup and discovery reports include method, repetitions and environment; see [measurement instructions and limits](bootstrap.md#tests-and-measurements). They do not measure representative photo workloads, cold-cache performance or memory. Review actual runner/interpreter versions in logs when comparing results. GitHub hosted runner time and artifact storage remain subject to account allowances/costs.

## Run and inspect

Pushes to `main` and pull-request events trigger the workflow. Feature pushes rely on the PR event to avoid duplicate matrix runs. On the feature PR, open **Checks**, select each native/container job and open its linked run to inspect steps, command output and failures. A pending, skipped or cancelled job is not a passing result. The workflow bounds jobs to 15 minutes and cancels superseded runs on the same ref; latest-head evidence matters.

Manual `workflow_dispatch` execution normally becomes available after the workflow exists on the default branch. After human merge, open **Actions > Bootstrap checks > Run workflow**, select the intended branch and start the run. There are no workflow inputs. Do not merge merely to enable that UI; PR-triggered runs provide validation before merge.

Open individual jobs/steps for logs. Download native reports from the run's **Artifacts** area before their seven-day retention expires. Review suite exits and benchmark JSON; an uploaded artifact alone is not a passing check. Builds and tests propagate failed subprocess status.

Reproduce failures using [local setup/test commands](bootstrap.md). Distinguish provisioning/runner problems from bootstrap defects. Preserve failing command, versions and diagnostics in ignored feature state; rerun affected checks after a correction. Authorized users can use GitHub's **Re-run failed jobs** or **Re-run all jobs** controls; a rerun without an explained cause does not resolve a defect. Code corrections trigger fresh checks on the same PR. Repository branch-protection required-check settings are not configured by this feature.

## Security and future coverage

The workflow uses read-only contents permission, SHA-pinned official actions, disabled persisted checkout credentials, no secrets, and no package/image publishing. Base-image, build-backend and runtime-dependency pins are reviewed separately. Downloads during provisioning/build are distinct from restricted runtime execution.

Recognition/OCR, tied-value resolution, file moves, monthly JSON, native artifact/model licensing and full offline processing remain future features. See [testing plan](testing-plan.md) for unresolved application policies and fixture permissions. Personal ignored samples are unavailable to public runners and are not published by this automation. Capture-metadata and capture-time validation use public metadata-only fixtures in CI and separate private sample-copy checks; their [reader](capture-metadata.md#validation-requirements) and [converter](capture-time.md#validation-requirements) contracts define required coverage.
