# Business requirements

## Purpose and scope

Reduce manual organization and transcription of Amazon Flex vehicle dashboard photos through a local console application. The intended process selects a source, identifies supported dashboard photos, groups readings by trip, organizes matching originals, and emits monthly trip records. All photos matching either supported layout qualify as Flex photos; no separate Flex classifier is required.

Candidate discovery is implemented. Photo-content processing remains future work. See the [discovery contract](heic-discovery.md) for its approved scope and limits and [technical requirements](TRD.md) for platform constraints.

## Requirements and acceptance criteria

| ID | Requirement / observable acceptance criterion |
| --- | --- |
| R01 | Runs on a Windows laptop; validates processing in a container. |
| R02 | Recursively discovers HEIC photos in the selected folder/subfolders. |
| R03 | Recognizes Trip Summary and Drive Info layouts; matching photos qualify as Flex photos. |
| R04 | Moves eligible matches to the user's destination; nonmatches remain untouched and processing continues. Leave qualifying photos with missing/invalid original-capture timestamps untouched, report them and continue without a timestamp fallback. Preserve completed work after interruption, safely resume verified pending work and provide concise recovery instructions; detailed mechanisms remain proposed. |
| R05 | Extracts all available displayed fields and photo capture timestamps. Preserve displayed units without conversion. Trip Time is hours:minutes and is stored as `hh:mm`; an unexpected duration format produces null for duration, is reported and does not block other fields. |
| R06 | Groups qualifying dashboard photos into trips using capture metadata timestamps. Photos within the configured first-to-last window belong to the same trip; no additional trip-identity validation is required. See the [grouping contract](trip-grouping.md) for the deterministic partition. |
| R07 | Configurable first-to-last trip window defaults to three minutes. Include the boundary: elapsed time from first to last capture must be less than or equal to the configured window. A group never grows through consecutive-photo chaining beyond that window. |
| R08 | Produces one JSON file per month and exactly one entry per trip, assigned to the last photo's metadata-local month. If equally latest photos have different local months, use their shared instant's UTC month and report the exception. Append new trips to existing monthly JSON, skip exact repeats and report overlaps for reconciliation without silently changing existing entries; matching details remain proposed. |
| R09 | Selects the most recent clearly readable value independently per field; clear zero is valid. Identical equally latest parsed values with identical units collapse to one value; conflicting equally latest clear readings stop preflight and are reported. |
| R10 | Retains earlier clear values when later photos omit or obscure those fields. |
| R11 | Emits JSON null for a field with no clear value across the trip. |
| R12 | Uses only free, open-source libraries and models. Review direct/transitive/native and model licensing. |
| R13 | One-time dependency/model downloads and installation are allowed, with clear setup and verification instructions. Subsequent photo processing works entirely offline, including any AI OCR; no external processing API calls. |
| R14 | Keep trip distance, trip duration, EV driving ratio, average MPG, odometer, remaining range and dashboard clock distinct. Capture date/time comes from photo metadata, not dashboard clock. Preserve any additional displayed fields discovered in samples. |
| R15 | Produce one report file per run in the JSON output folder, identifying each affected photo, issue and action. Preserve the report through preflight stops and failures where possible; report persistence must not depend on successful monthly output or moves. |

Acceptance starts with the 16 private, permissioned samples and must state their coverage limitations; publication is not authorized. Expected batches contain 500-1000 photos, about 300 matching, on a Windows laptop with 32 GB RAM and an Intel Core Ultra 9 288V. These describe evaluation conditions, not speed, memory or accuracy targets. Local decode/metadata and visual sample evaluation are documented separately; no application OCR or processing results have been measured.

## Constraints and exclusions

No cloud processing, paid/proprietary processing dependencies, GUI, or extra business features are requested. Installation/model provisioning is separate from offline execution. The application's own code and documentation use MIT; preserve third-party licenses, attribution and notices. MIT does not waive dependency or binary-distribution obligations. Exact dependency/model artifacts and the JSON schema remain gates before dependent work.

Destination filename collisions append `-01`, `-02`, and so on to the original stem before the extension, expanding beyond two digits and never overwriting an existing file; `photo-01.HEIC` becomes `photo-01-01.HEIC` on collision. Source, destination and JSON output folders must be separate and nonnested. Capture timestamps retain their full metadata date, time and offset under the approved [capture-time contract](capture-time.md). See [sample evaluation](sample-evaluation.md) for private evidence.

## Open decisions

- Complete human field/readability labels and field inventory; validate recognition and document sample coverage limitations. OCR confidence alone is not established evidence.
- Validate exact native/OCR artifacts and redistribution compatibility before adoption.
- Present a complete monthly JSON example for user approval before dependent implementation; exact field names/types, equality representation and report format remain design work. Preserve all displayed fields without inventing a complete inventory.
- Exact-repeat/overlap identity and matching, provenance, partial move/write recovery and other failure policies remain proposed. Incremental append, exact-repeat skipping, overlap reporting and safe resume are confirmed.
- Clarify only if material: how the unexpected-duration null rule interacts with an earlier clear duration in the same trip. Ordinary omitted/unclear fields retain the R10 rule; do not silently choose cross-photo semantics for the exception.

Obtain decisions before implementing dependent behavior. The proposed [integrated delivery plan](delivery-plan.md) consolidates remaining work and decision recommendations; approval must explicitly cover its scope and policies. Existing component approvals remain limited to their contracts.
