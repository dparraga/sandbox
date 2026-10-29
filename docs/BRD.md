# Business requirements

## Purpose and scope

Reduce manual organization and transcription of Amazon Flex vehicle dashboard photos through a local console application. The intended process selects a source, identifies supported dashboard photos, groups readings by trip, organizes matching originals, and emits monthly trip records. All photos matching either supported layout qualify as Flex photos; no separate Flex classifier is required.

Discovery, metadata/grouping/selection, interpretation and the recoverable batch workflow are implemented. See the [discovery contract](heic-discovery.md) for its approved scope and limits and [technical requirements](TRD.md) for platform constraints; verification results and coverage limits are recorded separately.

## Requirements and acceptance criteria

| ID | Requirement / observable acceptance criterion |
| --- | --- |
| R01 | Runs on a Windows laptop; validates processing in a container. |
| R02 | Recursively discovers HEIC photos in the selected folder/subfolders. |
| R03 | Recognizes Trip Summary and Drive Info layouts; matching photos qualify as Flex photos. |
| R04 | Moves eligible matches to the user's destination; nonmatches remain untouched and processing continues. Leave qualifying photos with missing/invalid original-capture timestamps untouched, report them and continue without a timestamp fallback. Preserve completed work after interruption, safely resume verified pending work and provide concise recovery instructions; the [delivery design](delivery-plan.md#durable-effects-and-safe-resume) defines mechanisms for independent Review. |
| R05 | Extracts only trip distance (miles), trip duration (`hh:mm`), Trip Average (MPG) and odometer when present, plus original capture metadata and an explicit metadata-derived trip date. Preserve literal displayed units without conversion. An unexpected duration format produces null for that observation, is reported and does not block other fields; a malformed observation is excluded from clear candidates, so an earlier valid duration remains eligible. |
| R06 | Groups qualifying dashboard photos into trips using capture metadata timestamps. Photos within the configured first-to-last window belong to the same trip; no additional trip-identity validation is required. See the [grouping contract](trip-grouping.md) for the deterministic partition. |
| R07 | Configurable first-to-last trip window defaults to three minutes. Include the boundary: elapsed time from first to last capture must be less than or equal to the configured window. A group never grows through consecutive-photo chaining beyond that window. |
| R08 | Produces one JSON file per month and exactly one entry per trip, assigned to the last photo's metadata-local month. If equally latest photos have different local months, use their shared instant's UTC month and report the exception. Append new trips to existing monthly JSON, skip exact repeats and report overlaps for reconciliation without silently changing existing entries; the [delivery design](delivery-plan.md#repeat-identity-and-overlap-reconciliation) defines matching mechanisms for independent Review. |
| R09 | Selects the most recent clearly readable value independently per field; clear zero is valid. Identical equally latest parsed values with identical units collapse to one value; conflicting equally latest clear readings stop preflight and are reported. |
| R10 | Retains earlier clear values when later photos omit or obscure those fields. |
| R11 | Emits JSON null for a field with no clear value across the trip. |
| R12 | Uses only free, open-source libraries and models. Review direct/transitive/native and model licensing. |
| R13 | One-time dependency/model downloads and installation are allowed, with clear setup and verification instructions. Subsequent photo processing works entirely offline, including any AI OCR; no external processing API calls. |
| R14 | Do not extract, retain as field observations or serialize any other dashboard data, including EV ratio, range, clock, temperature, speed, gear, indicators, symbols and gauges. Inspect only necessary layout anchors and the four requested reading regions; retained recognition evidence must be limited to those needs. Derive trip date from original capture metadata, never dashboard clock. |
| R15 | Produce one report file per run in the JSON output folder, identifying each affected photo, issue and action. Preserve the report through preflight stops and failures where possible; report persistence must not depend on successful monthly output or moves. |
| R16 | For an unexpected error or case, skip the affected item or operation, record the affected photo/item, issue and action in the report or log, and continue independent work. Preserve originals, completed work and pending progress; do not write/delete unverified or unsafe items, overwrite/corrupt data or claim skipped work completed. If a shared failure prevents all remaining work, report where possible and finish without repeated futile attempts. Explicit known-case rules, including R09's conflicting-reading preflight stop, remain in force. For individual decode, OCR execution or resource failures, leave that photo untouched, report it and continue independent photos. Missing or unavailable shared assets stop the run, report it incomplete and permit no moves or monthly JSON changes. Preserve earlier completed runs and safe recovery evidence. |
| R17 | Support durable graceful pause with Ctrl+C and explicit resume, preserving verified interpretations, failures, pending effects and active timing across process/system restart. Detect changed inputs/configuration. Display compact periodic progress and measured pause-aware ETA; retain essential item reports while aggregating repeated diagnostics and bounding optional logs. |

Acceptance starts with the 16 private, permissioned samples and must state their coverage limitations; publication is not authorized. Expected batches contain 500-1000 photos, about 300 matching, on a Windows laptop with 32 GB RAM and an Intel Core Ultra 9 288V. These describe evaluation conditions, not speed, memory or accuracy targets. Compare application readings and integrated outcomes against the existing private expectations, and report their coverage limitations.

## Constraints and exclusions

No cloud processing, paid/proprietary processing dependencies, GUI, or extra business features are requested. Installation/model provisioning is separate from offline execution. The application's own code and documentation use MIT; preserve third-party licenses, attribution and notices. MIT does not waive dependency or binary-distribution obligations. The JSON schema and scoped artifact recommendation are approved; complete application validation remains a delivery gate.

R16 governs integrated batch orchestration. Existing discovery, metadata, capture-time, grouping and field-candidate APIs retain their approved validation and error contracts.

Destination filename collisions append `-01`, `-02`, and so on to the original stem before the extension, expanding beyond two digits and never overwriting an existing file; `photo-01.HEIC` becomes `photo-01-01.HEIC` on collision. Source, destination and JSON output folders must be separate and nonnested. Capture timestamps retain their full metadata date, time and offset under the approved [capture-time contract](capture-time.md). See [sample evaluation](sample-evaluation.md) for private evidence.

## Acceptance conditions

- Validate actual recognition and four-reading output against the existing 16 private readability expectations; disclose primarily positive-sample coverage. Additional photos are not a new prerequisite. OCR confidence alone is not established evidence.
- Complete installed Windows/Linux interpretation, monthly output, movement, reporting and recovery acceptance. Artifact-entry and batch architecture reviews have passed under their recorded constraints; installed results must be recorded separately.
- Preserve the source-only deployment route and upstream artifact notices. A native binary bundle or published prebuilt image requires a separate redistribution assessment.

The approved trip date uses the last capture's metadata-local date; when equally latest captures have different days within the same local month, choose the greatest local calendar date and report it. The approved differing-local-month exception uses the shared instant's UTC date/month and is reported. No dashboard clock fallback is allowed.

Obtain any remaining material decisions before implementing dependent behavior. The [integrated delivery plan](delivery-plan.md) applies the user's one-branch/one-PR authorization for interpretation and batch processing together; this overrides the former merge-between-features gate for this run. Existing component approvals remain limited to their contracts.
