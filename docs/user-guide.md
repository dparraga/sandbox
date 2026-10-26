# User guide

The current application inventories HEIC filename candidates. Dashboard recognition, OCR, photo movement, monthly JSON and processing reports are **unavailable**. The interpretation interface and monthly schema are approved design; artifact validation and implementation remain pending. The [delivery plan](delivery-plan.md) tracks their approval and validation gates.

## Install and check on Windows

Install Git and CPython 3.13 or 3.14, then follow the one-time [Windows setup commands](bootstrap.md#windows-setup) from the repository root. They create an isolated environment, install hash-pinned dependencies, build/install the wheel and check it. Activation and an execution-policy change are unnecessary. Package provisioning needs internet access; the installed discovery command needs no models or codecs.

Future processing will also need validated local decoder/OCR binaries and a model. Exact installer provenance, native versions, SHA-256 values, licenses and model verification commands must pass the [artifact gates](delivery-plan.md#dependency-compatibility-and-offline-gates) before installation instructions are finalized. No processing install command or offline-readiness success is currently available. A downloaded model or successfully decoded photo alone does not establish offline readiness; the full installed processing path must run with network access disabled after provisioning.

## Commands available now

From the repository root after setup:

```powershell
.\.venv\Scripts\flex-photo.exe --help
.\.venv\Scripts\flex-photo.exe --version
.\.venv\Scripts\flex-photo.exe discover 'C:\Photos\Source'
```

Discovery writes a JSON array of candidate paths to the console. It does not decode, identify, move or edit photos and does not produce monthly files or a processing report. Running without arguments reports that photo processing is unavailable. The [discovery guide](heic-discovery.md#usage) covers traversal, links/reparse points and errors.

## Planned processing flow

These are intended steps, **not commands available today**. Exact processing options, report filename/format and resume instructions await the approved implementation.

1. Select local source, destination and JSON output folders that are separate and nonnested. Keep originals backed up. Select a first-to-last trip window; the default is three minutes, including its boundary. Nearby-photo chaining never extends that bound.
2. Recognize Trip Summary or Drive Info and read only trip distance, trip duration (`hh:mm`), Trip Average (`MPG`) and odometer when present. Each field independently keeps its latest clear value. Missing or unreadable readings become null only if no earlier clear reading is available; clear zero remains zero. Report malformed duration, exclude it as a clear candidate and keep an earlier valid duration eligible.
3. Derive trip date from original capture metadata according to the approved [monthly JSON contract](monthly-json.md). Dashboard clock and filenames do not supply the date. The last capture's local month owns the trip, with the approved reported UTC-month exception for equally latest captures in different local months. If equally latest captures have different local days within one month, use the greatest local calendar date and report the ambiguity.
4. Organize eligible matches without overwriting destination files; collisions add `-01`, `-02` and so on to the original stem. Emit one monthly JSON file with one entry per trip and the four fields plus explicit trip date. Append new trips, skip exact repeats and report overlaps for reconciliation without changing old entries. Detailed matching and recovery remain proposed.
5. Read the per-run report in the JSON output folder. It will identify the affected photo/item, issue and action, including timestamp exclusions, unavailable/exceptional readings, month exceptions, conflicts and overlaps. It must survive preflight stops where possible; if it cannot be saved, diagnostics must say so. The report is separate from the discovery console inventory.

## Exceptions, repeats and recovery

Ordinary nonmatches remain untouched. Qualifying photos with missing or invalid original capture timestamps remain untouched and are reported while processing continues. An unavailable reading does not invalidate available fields. Conflicting equally latest clear readings stop preflight and are reported; identical parsed values with identical units collapse.

An individual decode/OCR/resource failure leaves the affected photo untouched, reports the issue and continues. Missing required shared assets stop the run and report it incomplete, with no photo moves or monthly JSON changes. These execution failures are different from an unreadable individual field. The [interpretation contract](offline-photo-interpretation.md) defines the approved policy; these behaviors remain unimplemented.

The future organizer must preserve completed work and safely resume verified pending work after interruption. No processing/resume command exists yet. Until verified recovery instructions are supplied, retain originals, destination contents, JSON, reports and private recovery evidence; avoid manual edits or rerunning an interrupted move as if it were a new run. Exact repeats should be skipped and overlaps reported once the approved matching mechanism exists.

## Troubleshooting and validation

- If the Python launcher cannot find 3.13, use an installed supported 3.14 interpreter as described in setup. If the command is missing or stale, rebuild and reinstall the wheel using [setup](bootstrap.md#windows-setup).
- For discovery errors, check that the source is a real local directory and is readable. A selected symlink/reparse root is rejected; linked/reparse children are skipped. Cloud-managed folders are outside the intended input.
- An unavailable OCR command or missing processing report is expected in the current version. Do not download an arbitrary binary/model to bypass the artifact gates. Future missing-asset, permission, conflict and recovery diagnostics must give verified next actions before delivery.
- Use the existing [test and measurement commands](bootstrap.md#tests-and-measurements) and [restricted-container instructions](bootstrap.md#container). These exercise implemented components; they do not establish end-to-end OCR processing. The [testing plan](testing-plan.md) lists remaining checks and sample limitations.
