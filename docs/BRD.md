# Business requirements

## Purpose and scope

Reduce manual organization and transcription of Amazon Flex vehicle dashboard photos through a local console application. All photos matching either supported layout are Amazon Flex photos; do not add a separate Flex classifier. This feature delivers planning and role definitions only.

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

Acceptance will use user-provided, permissioned samples and approved policies. No OCR accuracy, coverage or performance target has been set. No readings or results have been measured.

## Constraints and exclusions

Language/runtime, OCR engine, project license and exact JSON schema remain proposals. Existing Apache-2.0 LICENSE is unchanged, not newly selected; the user requested evaluation of alternatives. No cloud processing, paid/proprietary processing dependencies, GUI or extra business features are requested. Installation/model provisioning must be distinguished from offline execution.

User decisions on 2026-10-21: destination filename collisions add a sequential `-##` suffix; dashboard trip duration output is minutes. Exact suffix formatting/start/placement and duration input parsing/precision remain proposals in TRD. The user has no preference for missing timestamps; that does not approve a handling policy.

## Open decisions

- Supply original HEIC samples of both layouts, including blurry/omitted fields and capture metadata; decide permission for any tracked fixtures.
- Confirm project license and proposed technical stack/schema after research/review.
- Missing/invalid capture timestamps and absent timezone/offset: skip, stop or another explicitly approved policy? Never silently substitute file modification time or dashboard clock.
- Timestamp ties and the exact grouping boundary (inclusive/exclusive) need approval; fixed first-to-last bound is mandatory regardless.
- Details of the approved sequential collision suffix, nested/overlapping source/destination, repeat runs/duplicate trip handling, partial move/write failures and recovery behavior.
- Trips crossing month boundaries: which month owns the single entry, and which timezone determines month?
- Dashboard duration input notation and conversion/precision to approved minutes output; retain raw readings versus normalized values and units in schema.
- What establishes “clearly readable,” handles conflicting readings and validates layout recognition? Requires samples; OCR confidence alone is not established evidence.
- Expected workload/laptop resources for performance evaluation; no limits assumed.

Open policies may remain unresolved during documentation planning; obtain decisions before implementing dependent behavior. Application implementation needs separate explicit approval.
