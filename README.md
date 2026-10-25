# Offline dashboard photo organizer

A Windows console application with Linux container validation. Its CLI lists HEIC filename candidates in local folders; internal libraries read original-capture metadata and convert valid original timestamps, group them into trips and identify latest-clear field candidates. Recognition, OCR, photo movement and monthly trip JSON remain future work.

Start with [setup, container and test commands](docs/bootstrap.md). Use `flex-photo discover SOURCE` for a console JSON inventory; see [discovery usage and limits](docs/heic-discovery.md#usage). With no arguments, the CLI reports bootstrap readiness. It also supports `--help` and `--version`.

- [Business requirements](docs/BRD.md) and [technical requirements](docs/TRD.md)
- [Solution design and repository structure](docs/repository-structure.md)
- [Development pipeline](docs/development-pipeline.md) and [contributing](CONTRIBUTING.md)
- [Testing plan](docs/testing-plan.md) and [GitHub automation](docs/github-test-automation.md)
- [Local sample evidence and handling](docs/sample-evaluation.md)
- [Review guidance](docs/review-guidance.md) and [shared agent rules](AGENTS.md)

The [capture metadata reader](docs/capture-metadata.md) implements an internal three-field EXIF interface, with no new CLI command. The [capture-time converter](docs/capture-time.md) validates those fields as fixed-offset timestamps without fallback selection. The [trip grouper](docs/trip-grouping.md) returns original input indices within the configured first-to-last window. The [field candidate selector](docs/field-selection.md) retains every equally latest clear observation per field without choosing tied values. These internal components add no CLI command. See the component contracts for acceptance gates and limits; actual validation results belong in the feature PR. This restriction applies only to capture metadata; all available dashboard fields remain required for later extraction.

The existing Apache-2.0 [LICENSE](LICENSE) is retained pending a project-license decision. The reader uses pinned BSD-3-Clause ExifRead; future imaging/OCR artifacts and models need separate license validation. Private photos and their inventory stay in ignored `sample-pictures/`; publication requires separate authorization.
