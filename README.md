# Offline dashboard photo organizer

An open-source console application planned for a Windows laptop, with Linux container validation. Future processing will recognize HEIC Trip Summary and Drive Info photos, organize matching originals, and produce monthly trip JSON using the latest clear value for each field.

**Current feature: Development environment bootstrap.** Planning PR #1 is merged. The user approved the reviewed architecture and this bootstrap scope: source/package structure, a minimal installed CLI, container configuration, tests, CI and instructions. Photo recognition, OCR, grouping, movement and monthly JSON are not implemented. The feature remains active until its PR is merged by a human.

Start with [Windows setup, CLI, container and test commands](docs/bootstrap.md). The CLI reports bootstrap readiness and supports `--help` and `--version`.

- [Business requirements and open decisions](docs/BRD.md)
- [Technical design and approval boundaries](docs/TRD.md)
- [Repository structure](docs/repository-structure.md)
- [Development pipeline and pause/resume](docs/development-pipeline.md)
- [Testing plan](docs/testing-plan.md) and [GitHub automation](docs/github-test-automation.md)
- [Local HEIC sample evaluation and future fixture use](docs/sample-evaluation.md)
- [Review guidance](docs/review-guidance.md), [contributing](CONTRIBUTING.md), [shared agent rules](AGENTS.md), [role contracts](agents/lead.md)

Trip duration will be stored as `hh:mm`; capture metadata retains its full date/time/offset. No duration handling is implemented here. The existing Apache-2.0 [LICENSE](LICENSE) remains unchanged pending the user's license decision. Imaging/OCR artifact and model licensing remain future gates.

The 16 user-provided HEIC files and their durable inventory remain local in ignored `sample-pictures/`. Planning evaluated decode/metadata and visual layout; OCR accuracy remains untested. Original photos, metadata and derived previews require separate publication authorization.
