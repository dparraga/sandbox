# Offline dashboard photo organizer

A Windows console application with Linux container validation. It currently lists HEIC filename candidates in local folders. Recognition, OCR, trip grouping, photo movement and monthly trip JSON remain future work.

Start with [setup, container and test commands](docs/bootstrap.md). Use `flex-photo discover SOURCE` for a console JSON inventory; see [discovery usage and limits](docs/heic-discovery.md#usage). With no arguments, the CLI reports bootstrap readiness. It also supports `--help` and `--version`.

- [Business requirements](docs/BRD.md) and [technical requirements](docs/TRD.md)
- [Solution design and repository structure](docs/repository-structure.md)
- [Development pipeline](docs/development-pipeline.md) and [contributing](CONTRIBUTING.md)
- [Testing plan](docs/testing-plan.md) and [GitHub automation](docs/github-test-automation.md)
- [Local sample evidence and handling](docs/sample-evaluation.md)
- [Review guidance](docs/review-guidance.md) and [shared agent rules](AGENTS.md)

The existing Apache-2.0 [LICENSE](LICENSE) is retained pending a project-license decision. Runtime dependencies are currently empty; future imaging/OCR artifacts and models need license validation. Private photos and their inventory stay in ignored `sample-pictures/`; publication requires separate authorization.
