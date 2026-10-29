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

Destination collisions add `-01`, `-02` and so on to the original stem, without overwriting. Monthly `YYYY-MM.json` files append disjoint trips while preserving existing entries. The console refreshes progress periodically, followed by a JSON summary with status, verified report path and final counts. Progress includes candidates, evaluated/remaining counts, percentage, stage, status, active time, average time per newly processed photo and measured ETA. ETA shows `Calculating...` until measurements are available; finalization is identified separately when its duration cannot yet be estimated. Paused time is excluded. Redirected terminals receive infrequent lines. Exit 0 means complete or gracefully paused, 1 means incomplete/failure and 2 means invalid command syntax.

## Reports, repeats and recovery

Inspect the unique `report-<UTC timestamp>-<token>.json` in the JSON output folder after every processing run. It records affected items, issues, actions and separate stage/category counts. Repeated identical item issues are collapsed. Reports have no arbitrary size cap and contain no raw OCR. Normal processing creates no diagnostic log; `--diagnostics` enables sanitized exception stacks with one representative per category, limited to two 64 KiB private log files. Unreadable fields differ from execution failures: per-photo decode/OCR/resource failures leave that photo untouched and continue independent photos. Missing shared assets stop the run incomplete before photo moves or monthly changes. Conflicting equally latest clear values stop preflight. Qualifying photos with unusable original timestamps remain untouched and are reported.

An `incomplete` summary can mean every candidate was evaluated but some photos were skipped; it does not by itself indicate a crash. Completed moves and trips remain saved. Check `counts`, `progress.remaining` and `issue_summary` in the report before retrying. Use `--resume` only while saved work remains; a finished run with reported skips has no extraction checkpoint to resume. Newly qualifying photos can still overlap existing trips and require reconciliation under the existing output rules.

Keep `.flex-photo-state.json`, `.flex-photo-checkpoint/`, `.flex-photo.lock`, monthly files, destination copies and reports together. The checkpoint is private recovery data, separate from public monthly JSON. The private state stores original-byte identity and pending work; it is needed because public monthly JSON contains no photo identifiers. Exact complete repeats are skipped. Partial or overlapping memberships are left untouched for reconciliation; the command never silently rewrites old trips or imports externally edited output.

Press `Ctrl+C` once to request pause. The current photo or safe movement unit finishes, its progress is flushed, a paused report is saved and the command exits cleanly. Resume by adding `--resume` to the same processing command with unchanged folders, window and assets. Completed interpretations, failures and active timing survive restart; unchanged verified photos avoid repeated decoding/OCR. Changed original bytes are reprocessed and prior failures remain reportable. New photos added after the saved candidate inventory wait for a later normal run.

Pending moves/monthly updates receive recovery-only handling before any fresh work, using saved values and hashes. Existing effect plans also retain their previous automatic recovery behavior when the command is rerun without `--resume`; their saved grouping window remains authoritative. After recovery completes, use a normal invocation for new input. Repeated `--resume` after a completed checkpoint reports that no operation remains. Preserve unexpected bytes and unresolved evidence; do not delete state to start over. Abrupt termination may require repeating only the uncheckpointed current unit; a torn final journal append is discarded, while corrupt completed entries stop for reconciliation.

## Troubleshooting

- Rebuild and reinstall a stale command using [setup](bootstrap.md#windows-setup). Use supported Python 3.14 if 3.13 is unavailable.
- For missing assets, verify the provisioned executable/model paths and recorded identity. Restore reviewed assets before retrying; do not bypass integrity checks.
- For ownership errors, wait for the active process to finish. A leftover lock file alone is not ownership and need not be deleted.
- For changed files, overlaps or recovery reconciliation, preserve originals, copies, state and reports. Follow the reported action; automatic repair/import is unavailable.
- Images above the approved 16-million-pixel primary-image guard remain untouched and are reported explicitly. Recognition still requires both approved title/label geometry rules; unknown layouts remain unresolved.
- If no report can be saved, inspect the sanitized filesystem/serialization category and errno on stderr, output-folder permissions, storage and file locks. An unsaved report is never evidence of completed work.

Use the [test commands](bootstrap.md#tests-and-measurements) and [restricted-container instructions](bootstrap.md#container). Record real OCR, synthetic composition, native resource checks and platform skips separately; synthetic tests do not establish private-image accuracy.
