# Testing plan

Unit/integration automation covers the installed CLI, packaging, HEIC candidate discovery and capture-metadata reader, capture-time converter and trip grouper. Separate synthetic discovery and process-startup benchmarks are implemented. Actual results, platform skips and outstanding validation belong in the feature PR and ignored local state. The internal [capture metadata contract](capture-metadata.md#validation-requirements) defines its additional acceptance gates; it does not introduce a CLI command or dashboard extraction. The [capture-time contract](capture-time.md#validation-requirements) defines conversion acceptance without adding CLI or grouping behavior. The [grouping contract](trip-grouping.md#validation-requirements) defines internal trip partition acceptance. No recognition/OCR, field selection, moves or monthly JSON coverage is claimed. Use [setup instructions](bootstrap.md) for commands, [automation](github-test-automation.md) for CI, and the authoritative [discovery contract](heic-discovery.md) for R02 acceptance scenarios.

Testing owns cases, fixtures, automation, execution, and results. After explicit implementation approval, Testing develops cases in parallel with Implementation and runs applicable tests as soon as code is runnable. Documentation records verified commands; Review independently checks coverage and findings; Lead validates evidence.

## Implemented acceptance coverage

Unit tests exercise readiness/help/version and argument errors. Integration tests execute installed module and console commands from an isolated path containing spaces/Unicode, verify exit/stdout/stderr semantics, wheel metadata/payload and no created files. Performance automation times repeated installed-process startup after warmup and records environment and sample counts; no speed threshold is approved. Container smoke checks exercise the installed CLI with network disabled, read-only filesystem and nonroot execution. Discovery tests additionally cover the approved traversal, inventory and failure contract. Metadata tests exercise original-capture text fidelity, missing values, sanitized errors, parser guards and file-handling failures. Installed-library integration runs outside the checkout with network calls blocked and checks source preservation. Container checks exercise extraction, capture-time conversion, grouping, a guard failure and dependency version/license retention using public metadata-only fixtures. Capture-time unit checks cover strict syntax, dates, offsets, fractional precision, sanitized errors and unchanged input; installed integration composes the reader with conversion. Grouping unit checks cover ordering, bounded windows, date/offset extremes and sanitized validation; installed integration composes metadata reading, conversion and grouping while preserving synthetic source bytes. These fixtures establish no image decodability or OCR accuracy.

## Application requirement coverage

| Requirements | Scenarios and evidence |
| --- | --- |
| R01 | Run applicable unit and integration tests on Windows and in a Linux container. Record OS, runtime, dependency versions, container image, commands, and results. |
| R02 | Scan nested folders containing HEIC and other files; verify discovery against an approved fixture manifest. Use the approved [discovery contract](heic-discovery.md) for selection, traversal and error expectations. |
| R03 | Use user-supplied, labeled samples of both Trip Summary and Drive Info, plus labeled nonmatching photos. Verify recognition against approved labels without inventing OCR readings. |
| R04 | Integration-test moving recognized photos to the selected destination and keeping nonmatches in place. Collision, existing destination, partial failure, interruption, retry, cross-volume movement, and recovery expectations require decisions before destructive cases run. Use disposable copies only. |
| R05, R14 | Compare extraction to human-verified fixture readings and capture metadata. Keep distance, duration, EV driving ratio, average MPG, odometer, remaining range, dashboard clock, and capture time separate. Cover all available displayed fields. |
| R06, R07 | Use the authoritative [grouping contract](trip-grouping.md) for partition, ordering, boundary and validation scenarios. Stable equal-time order does not establish field-value winners. |
| R08 | Verify one JSON file per applicable month and exactly one entry per trip using the approved schema. Cross-month trips and repeated-run output behavior remain unresolved. |
| R09 | Test each field independently with clear values at different capture times: the latest clearly readable value for each field wins. Do not select one entire photo as the source for all fields. |
| R10 | For each field, a newer absent or unclear value retains the earlier clear value. Include photos where some fields improve while others become unclear. |
| R11 | A field with no clearly readable value across a trip is JSON `null`; distinguish null from zero and from omitted properties according to the eventual schema. |
| R12 | Review direct and transitive dependency/model licenses and any redistributed assets against the approved project license. Record authoritative license evidence; no paid service dependency is permitted. |
| R13 | Exercise the complete processing path with network access disabled after documented provisioning. Verify recognition/OCR and metadata extraction make no external API calls; document model availability and loading. |

## Future processing tests and fixtures

- Unit: per-field selection/retention/null behavior and approved serialization rules.
- Integration: folder scan through recognition, metadata extraction, grouping, movement, and monthly JSON output on disposable fixture trees; compare file inventories and approved JSON expectations.
- Performance: measure end-to-end processing and useful stage timings, throughput, memory, and workload size. Record photo count, dimensions, nesting, hardware, OS/container resources, runtime/model versions, cold versus warm setup, and repetitions. Propose limits only after representative measurements and user approval; no limits or coverage targets are currently set.

Use the [sample handling rules and coverage limits](sample-evaluation.md) for originals, hashes, disposable copies, pending labels and publication authorization. Synthetic filesystem and metadata-only fixtures do not establish image decodability or OCR accuracy. Validate capture metadata against the existing original-capture evidence using disposable private sample copies; publish only aggregate results, never raw metadata.

## Decisions needed before affected tests

The [BRD open decisions](BRD.md#open-decisions) are authoritative. Apply the approved [capture-time rules](capture-time.md); do not encode unapproved batch timestamp, suffix, cross-month, recovery, repeated-run, readability or schema policies as expected results. Trip duration expectations must preserve approved `hh:mm` storage.

Before an implementation PR, run applicable local tests and independently review fixes. On PR updates, rerun affected tests and review corrections before pushing. Preserve commands, environment, results, failures, and remaining gaps in the feature's ignored local state; publish only suitable sanitized evidence.
