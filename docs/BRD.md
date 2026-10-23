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
| R04 | Moves matches to the user's destination; unrelated photos remain untouched. Move/error policies require decisions below. |
| R05 | Extracts all available displayed fields and photo capture timestamps. |
| R06 | Groups matches into trips using capture metadata timestamps. |
| R07 | Configurable first-to-last trip window defaults to three minutes. A group never grows through consecutive-photo chaining beyond that window. |
| R08 | Produces one JSON file per month and exactly one entry per trip; month assignment policy is pending. |
| R09 | Selects the most recent clearly readable value independently per field. |
| R10 | Retains earlier clear values when later photos omit or obscure those fields. |
| R11 | Emits JSON null for a field with no clear value across the trip. |
| R12 | Uses only free, open-source libraries and models. Review direct/transitive/native and model licensing. |
| R13 | Photo processing works entirely offline, including any AI OCR; no external processing API calls. |
| R14 | Keep trip distance, trip duration, EV driving ratio, average MPG, odometer, remaining range and dashboard clock distinct. Capture date/time comes from photo metadata, not dashboard clock. Preserve any additional displayed fields discovered in samples. |

Acceptance will use user-provided, permissioned samples and approved policies. No OCR accuracy, coverage or performance target has been set. Local decode/metadata and visual sample evaluation are documented separately; no application OCR or processing results have been measured.

## Constraints and exclusions

No cloud processing, paid/proprietary processing dependencies, GUI, or extra business features are requested. Installation/model provisioning is separate from offline execution. The existing Apache-2.0 license is retained pending the user's evaluation of alternatives; dependency/model licenses and the JSON schema need decisions before dependent work.

Destination filename collisions add a sequential `-##` suffix. Trip Time means hours:minutes and must be stored as `hh:mm`; capture timestamps retain their full metadata date, time, and offset. Exact suffix formatting/start/placement and unsupported duration formats remain open. The user has no preference for missing timestamps; a handling policy still needs approval. Local HEIC samples are authorized for evaluation and testing, not publication. See [sample evaluation](sample-evaluation.md).

## Open decisions

- Original samples of both layouts are available locally. Complete human field/readability labels and obtain additional nonmatches/edge cases; publication of tracked fixtures is not authorized.
- Confirm project license, exact future native/OCR artifacts and proposed JSON schema before dependent work.
- Missing/invalid capture timestamps and absent timezone/offset: skip, stop or another explicitly approved policy? Never silently substitute file modification time or dashboard clock.
- Timestamp ties and the exact grouping boundary (inclusive/exclusive) need approval; fixed first-to-last bound is mandatory regardless.
- Details of the approved sequential collision suffix, nested/overlapping source/destination, repeat runs/duplicate trip handling, partial move/write failures and recovery behavior.
- Trips crossing month boundaries: which month owns the single entry, and which timezone determines month?
- Other duration formats, if encountered, and raw readings versus normalized values/units in the schema remain open.
- What establishes “clearly readable,” handles conflicting readings and validates layout recognition? Requires samples; OCR confidence alone is not established evidence.
- Expected workload/laptop resources for performance evaluation; no limits assumed.

Obtain decisions before implementing dependent behavior. Discovery approval is limited to its feature contract; later processing needs its own scoped approval.
