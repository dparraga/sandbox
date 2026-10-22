# Testing plan

Status: proposed; no executable tests or test results exist in this planning feature. Requirement IDs R01–R13 follow the numbered application requirements in [BRD.md](BRD.md); R14 covers distinct displayed fields and metadata capture time.

Testing owns cases, fixtures, automation, execution, and results. After explicit implementation approval, Testing develops cases in parallel with Implementation and runs applicable tests as soon as code is runnable. Documentation records verified commands; Review independently checks coverage and findings; Lead validates evidence.

## Requirement coverage

| Requirements | Planned scenarios and evidence |
| --- | --- |
| R01 | Run applicable unit and integration tests on Windows and in a Linux container. Record OS, runtime, dependency versions, container image, commands, and results. |
| R02 | Scan nested folders containing HEIC and other files; verify discovery against an approved fixture manifest. Resolve extension variants, unreadable files, and traversal errors before fixing expectations. |
| R03 | Use user-supplied, labeled samples of both Trip Summary and Drive Info, plus labeled nonmatching photos. Verify recognition against approved labels without inventing OCR readings. |
| R04 | Integration-test moving recognized photos to the selected destination and keeping nonmatches in place. Collision, existing destination, partial failure, interruption, retry, cross-volume movement, and recovery expectations require decisions before destructive cases run. Use disposable copies only. |
| R05, R14 | Compare extraction to human-verified fixture readings and capture metadata. Keep distance, duration, EV driving ratio, average MPG, odometer, remaining range, dashboard clock, and capture time separate. Cover all available displayed fields. |
| R06, R07 | Test grouping by capture time and configured windows, including the default three minutes. Photos at 00:00, 00:02, and 00:04 must not form one three-minute trip through consecutive-photo chaining. Confirm boundary inclusivity and tie handling before exact partition expectations. |
| R08 | Verify one JSON file per applicable month and exactly one entry per trip using the approved schema. Cross-month trips and repeated-run output behavior remain unresolved. |
| R09 | Test each field independently with clear values at different capture times: the latest clearly readable value for each field wins. Do not select one entire photo as the source for all fields. |
| R10 | For each field, a newer absent or unclear value retains the earlier clear value. Include photos where some fields improve while others become unclear. |
| R11 | A field with no clearly readable value across a trip is JSON `null`; distinguish null from zero and from omitted properties according to the eventual schema. |
| R12 | Review direct and transitive dependency/model licenses and any redistributed assets against the approved project license. Record authoritative license evidence; no paid service dependency is permitted. |
| R13 | Exercise the complete processing path with network access disabled after documented provisioning. Verify recognition/OCR and metadata extraction make no external API calls; document model availability and loading. |

## Test levels and fixtures

- Unit: grouping window invariants, per-field selection/retention/null behavior, and approved serialization/conversion rules.
- Integration: folder scan through recognition, metadata extraction, grouping, movement, and monthly JSON output on disposable fixture trees; compare file inventories and approved JSON expectations.
- Performance: measure end-to-end processing and useful stage timings, throughput, memory, and workload size. Record photo count, dimensions, nesting, hardware, OS/container resources, runtime/model versions, cold versus warm setup, and repetitions. Propose limits only after representative measurements and user approval; no limits or coverage targets are currently set.

Keep original sample photos outside public history unless the user authorizes publication. Use synthetic metadata and disposable copies for filesystem cases; synthetic files do not establish OCR accuracy. Human verification must label expected values and readability per field. Record fixture origin, consent, license, and expected readings without exposing personal metadata. Do not fabricate samples or passed results.

## Decisions needed before affected tests

User decisions: filename collisions receive a sequential `-##` suffix and duration output is minutes. Plan cases for sequential allocation without overwriting and duration output once input parsing is agreed. Missing or invalid capture timestamps; time zone and daylight-saving interpretation; timestamp ties and grouping boundary rules; suffix formatting/start/placement; cross-month grouping/output; duration input conversion/precision; move failure and recovery behavior; repeated runs and JSON update behavior; recognition/readability criteria; and exact schema remain open. Ask for decisions and representative photos when needed. Record decisions in BRD/TRD before encoding expectations.

Before an implementation PR, run applicable local tests and independently review fixes. On PR updates, rerun affected tests and review corrections before pushing. Preserve commands, environment, results, failures, and remaining gaps in the feature's ignored local state; publish only suitable sanitized evidence.
