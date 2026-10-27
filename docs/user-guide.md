# User guide

The application discovers HEIC candidates and processes supported Trip Summary and Drive Info photos using local assets. It writes monthly trip JSON, moves eligible originals without overwriting and retains verified recovery progress. Validation covers the existing 16 positive samples; unknown layouts remain untouched and are reported as unresolved. This does not establish general unseen-layout or real nonmatch accuracy. See the [testing plan](testing-plan.md) for coverage.

## Install on Windows

Install Git and CPython 3.13 or 3.14, then follow the [Windows setup commands](bootstrap.md#windows-setup) to provision hash-pinned dependencies and build/install the wheel. Activation and an execution-policy change are unnecessary. Rebuild/reinstall after package changes.

Provision local OCR assets from the repository root:

```powershell
./scripts/provision_windows_ocr.ps1 -Destination reports/ocr-assets
$assets = Get-Content reports/ocr-assets/assets.json -Raw | ConvertFrom-Json
```

This helper downloads hash-verified upstream assets and extracts the engine without running its installer. It also preserves upstream documentation/notices. One-time provisioning requires internet access; processing uses only local assets. The source, application wheel and source Dockerfiles do not bundle native wheels, portable OCR or a prebuilt image. Keep upstream licenses/notices. An arbitrary executable/model does not satisfy the reviewed [artifact contract](offline-photo-interpretation.md).

## Commands

```powershell
./.venv/Scripts/flex-photo.exe --help
./.venv/Scripts/flex-photo.exe --version
./.venv/Scripts/flex-photo.exe discover 'C:\Photos\Source'
./.venv/Scripts/flex-photo.exe process --help
```

Discovery prints a JSON array of candidate paths and leaves files untouched. See its [traversal and error rules](heic-discovery.md#usage).

The processing command uses three separate, nonnested local folders and explicit assets:

```powershell
./.venv/Scripts/flex-photo.exe process 'C:\Photos\Source' --destination 'C:\Photos\Organized' --json-output 'C:\Photos\Trip JSON' --window-seconds 180 --tesseract $assets.tesseract_executable --tessdata $assets.tessdata_directory --tesseract-sha256 $assets.executable_sha256
```

Processing moves eligible originals. Use disposable copies for development evaluation. The source must exist; requested destination/output folders may be created. Linked/reparse paths are rejected where safe containment cannot be verified. The default grouping window is three minutes, including the boundary, measured from first to last capture without chaining.

Only Trip Summary and Drive Info are recognized. Readings are trip distance, elapsed duration (`hh:mm`), Trip Average (`MPG`) and odometer when present. Each field independently retains its latest clear value; a later absent/unclear field does not remove an earlier clear one. Zero remains a value. Trip date and month come from original capture metadata, using the reported date/month exceptions in the [monthly JSON contract](monthly-json.md). No dashboard-clock or filename fallback applies.

Destination collisions add `-01`, `-02` and so on to the original stem, without overwriting. Monthly `YYYY-MM.json` files append disjoint trips while preserving existing entries. Console output is a small JSON summary containing status, report path when saved and counts. Exit 0 means complete, 1 means incomplete/failure and 2 means invalid command syntax.

## Reports, repeats and recovery

Inspect the unique `report-<UTC timestamp>-<token>.json` in the JSON output folder after every processing run. It records affected items, issues and actions. Unreadable fields differ from execution failures: per-photo decode/OCR/resource failures leave that photo untouched and continue independent photos. Missing shared assets stop the run incomplete before photo moves or monthly changes. Conflicting equally latest clear values stop preflight. Qualifying photos with unusable original timestamps remain untouched and are reported.

Keep `.flex-photo-state.json`, `.flex-photo.lock`, monthly files, destination copies and reports together. The private state stores original-byte identity and pending work; it is needed because public monthly JSON contains no photo identifiers. Exact complete repeats are skipped. Partial or overlapping memberships are left untouched for reconciliation; the command never silently rewrites old trips or imports externally edited output.

After interruption, rerun the same command with the same folders and available local assets. A pending plan receives recovery-only handling using saved values and hashes; it does not reinterpret remaining sources or process new input in that invocation. After recovery completes, another normal invocation can process new photos. Preserve unexpected bytes and unresolved pending evidence; do not manually delete state or treat an interrupted move as a fresh run. Completed earlier trips remain completed.

## Troubleshooting

- Rebuild and reinstall a stale command using [setup](bootstrap.md#windows-setup). Use supported Python 3.14 if 3.13 is unavailable.
- For missing assets, verify the provisioned executable/model paths and recorded identity. Restore reviewed assets before retrying; do not bypass integrity checks.
- For ownership errors, wait for the active process to finish. A leftover lock file alone is not ownership and need not be deleted.
- For changed files, overlaps or recovery reconciliation, preserve originals, copies, state and reports. Follow the reported action; automatic repair/import is unavailable.
- If no report can be saved, inspect stderr and output-folder permissions. An unsaved report is never evidence of completed work.

Use the [test commands](bootstrap.md#tests-and-measurements) and [restricted-container instructions](bootstrap.md#container). Record real OCR, synthetic composition, native resource checks and platform skips separately; synthetic tests do not establish private-image accuracy.
