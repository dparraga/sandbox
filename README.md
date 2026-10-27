# Offline dashboard photo organizer

A console application for offline HEIC dashboard processing on Windows and Linux. The process command recognizes supported Trip Summary and Drive Info photos, selects four readings independently, moves eligible originals without overwriting, and appends monthly trip JSON with verified recovery. Validation uses the existing 16 positive samples; unknown layouts remain unresolved, and this corpus does not establish general nonmatch or unseen-layout accuracy.

Start with the [user guide](docs/user-guide.md) and [setup, container and test commands](docs/bootstrap.md). Use `flex-photo discover SOURCE` for a console JSON inventory; see [discovery usage and limits](docs/heic-discovery.md#usage). The `process` command composes local interpretation with the [batch design](docs/delivery-plan.md); use `process --help` for its explicit folder and asset options. The CLI also supports `--help` and `--version`.

- [Business requirements](docs/BRD.md) and [technical requirements](docs/TRD.md)
- [Solution design and repository structure](docs/repository-structure.md)
- [Development pipeline](docs/development-pipeline.md) and [contributing](CONTRIBUTING.md)
- [Testing plan](docs/testing-plan.md) and [GitHub automation](docs/github-test-automation.md)
- [Local sample evidence and handling](docs/sample-evaluation.md)
- [Review guidance](docs/review-guidance.md) and [shared agent rules](AGENTS.md)

The internal [capture metadata reader](docs/capture-metadata.md), [capture-time converter](docs/capture-time.md), [trip grouper](docs/trip-grouping.md) and [field candidate selector](docs/field-selection.md) preserve original metadata and select fields independently. Reading scope is trip distance, trip duration, Trip Average MPG and odometer when present, plus a trip date derived from capture metadata. See the [monthly JSON contract](docs/monthly-json.md) and component contracts for acceptance requirements; actual validation results belong in the feature PR.

The application's own code and documentation use the MIT [LICENSE](LICENSE). Third-party code, models and binaries retain their own licenses, attribution and notices; MIT does not waive their redistribution obligations. The reader uses pinned BSD-3-Clause ExifRead; the approved interpretation design uses separately provisioned upstream imaging/OCR artifacts and a pinned model. This repository delivers MIT source, the application wheel and source Dockerfiles; it does not bundle native wheels, portable OCR binaries or a prebuilt image. Preserve upstream notices; binary redistribution needs a separate licensing assessment. Private photos and their inventory stay in ignored `sample-pictures/`; publication requires separate authorization.
