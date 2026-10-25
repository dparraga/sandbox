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
| R04 | Moves matches to the user's destination; nonmatches remain untouched and processing continues. Preserve completed work after interruption and support safe resume; detailed move/recovery policies require decisions below. |
| R05 | Extracts all available displayed fields and photo capture timestamps. |
| R06 | Groups qualifying dashboard photos into trips using capture metadata timestamps. Photos within the configured first-to-last window belong to the same trip; no additional trip-identity validation is required. See the [grouping contract](trip-grouping.md) for the deterministic partition. |
| R07 | Configurable first-to-last trip window defaults to three minutes. Include the boundary: elapsed time from first to last capture must be less than or equal to the configured window. A group never grows through consecutive-photo chaining beyond that window. |
| R08 | Produces one JSON file per month and exactly one entry per trip, assigned to the last photo's metadata-local month. Append new trips to existing monthly JSON, skip exact repeats and report overlaps for reconciliation; matching details remain open. |
| R09 | Selects the most recent clearly readable value independently per field. Conflicting equally latest clear readings stop preflight and are reported. |
| R10 | Retains earlier clear values when later photos omit or obscure those fields. |
| R11 | Emits JSON null for a field with no clear value across the trip. |
| R12 | Uses only free, open-source libraries and models. Review direct/transitive/native and model licensing. |
| R13 | One-time dependency/model downloads and installation are allowed, with clear setup and verification instructions. Subsequent photo processing works entirely offline, including any AI OCR; no external processing API calls. |
| R14 | Keep trip distance, trip duration, EV driving ratio, average MPG, odometer, remaining range and dashboard clock distinct. Capture date/time comes from photo metadata, not dashboard clock. Preserve any additional displayed fields discovered in samples. |

Acceptance will use user-provided, permissioned samples and approved policies. No OCR accuracy, coverage or performance target has been set. Local decode/metadata and visual sample evaluation are documented separately; no application OCR or processing results have been measured.

## Constraints and exclusions

No cloud processing, paid/proprietary processing dependencies, GUI, or extra business features are requested. Installation/model provisioning is separate from offline execution. The application's own code and documentation use MIT; preserve third-party licenses, attribution and notices. MIT does not waive dependency or binary-distribution obligations. Exact dependency/model artifacts and the JSON schema remain gates before dependent work.

Destination filename collisions add a sequential `-##` suffix. Trip Time means hours:minutes and must be stored as `hh:mm`; capture timestamps retain their full metadata date, time, and offset. Exact suffix formatting/start/placement and unsupported duration formats remain open. The approved [capture-time contract](capture-time.md) validates original-capture timestamps without fallbacks. The user has no preference for missing timestamps; a future batch handling policy still needs approval. Local HEIC samples are authorized for evaluation and testing, not publication. See [sample evaluation](sample-evaluation.md).

## Open decisions

- Original samples of both layouts are available locally. Complete human field/readability labels and obtain additional nonmatches/edge cases; publication of tracked fixtures is not authorized.
- Validate exact future native/OCR artifacts, redistribution compatibility and the proposed JSON schema before dependent work.
- Batch handling of rejected or missing original-capture timestamps: skip, stop or another explicitly approved policy? The [converter](capture-time.md) requires an explicit offset and uses no fallback; never silently substitute file modification time or dashboard clock.
- Identical equally latest clear readings: whether and how to collapse equivalent parsed values/units remains open. Conflicting readings already stop preflight and are reported; stable input order does not choose a winner.
- Details of the approved sequential collision suffix, nested/overlapping folders, exact-repeat/overlap identity and matching, and partial move/write recovery mechanics. Incremental append, exact-repeat skipping, overlap reporting and safe resume are confirmed.
- Equally latest photos can have offsets placing them in different local months: how should that month conflict be handled? Otherwise the last photo's metadata-local month owns the single trip entry.
- Other duration formats, if encountered, and raw readings versus normalized values/units in the schema remain open.
- What establishes “clearly readable,” handles conflicting readings and validates layout recognition? Requires samples; OCR confidence alone is not established evidence.
- Expected workload/laptop resources for performance evaluation; no limits assumed.

Obtain decisions before implementing dependent behavior. The proposed [integrated delivery plan](delivery-plan.md) consolidates remaining work and decision recommendations; approval must explicitly cover its scope and policies. Existing component approvals remain limited to their contracts.
