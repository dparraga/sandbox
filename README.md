# Offline dashboard photo organizer — planning

Plan an open-source console application for a Windows laptop, with container testing. It will find HEIC photos matching Trip Summary or Drive Info dashboards, move matches, group them by capture metadata, and produce monthly trip JSON with the most recent clear value for each field.

**Status:** Planning foundation only. No application, runnable tests, container or automation exists. Technical choices are proposals. Application implementation requires explicit approval after architecture and independent review reports are presented. This feature completes only when its PR is merged by a human.

- [Business requirements and open questions](docs/BRD.md)
- [Proposed technical design and sources](docs/TRD.md)
- [Proposed repository structure](docs/repository-structure.md)
- [Development pipeline and pause/resume](docs/development-pipeline.md)
- [Testing plan](docs/testing-plan.md) and [planned GitHub automation](docs/github-test-automation.md)
- [Review guidance](docs/review-guidance.md), [contributing](CONTRIBUTING.md), [shared agent rules](AGENTS.md), [role contracts](agents/lead.md)

The repository contains an existing Apache-2.0 [LICENSE](LICENSE), preserved unchanged; the user has not yet confirmed the project license choice. Real sample HEIC photos of both layouts are needed before OCR feasibility or readings can be validated. Do not commit personal photos without permission.
