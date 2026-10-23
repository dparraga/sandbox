# Contributing

Read [AGENTS.md](AGENTS.md), [BRD](docs/BRD.md), [TRD](docs/TRD.md) and the [pipeline](docs/development-pipeline.md). Keep one feature active. Inspect Git status/remotes/default branch and preserve unrelated changes. Create a feature branch from the updated usable base; coordinate initialization if none exists.

Before creating or modifying documentation, read [project-documentation](.agents/skills/project-documentation/SKILL.md). Keep requirements, design and operational instructions distinct and current. After scoped approval, Implementation and Testing work in parallel while Documentation stays synchronized.

Use [setup instructions](docs/bootstrap.md) to create an isolated environment, build/install the wheel and execute unit, integration and separate startup/discovery measurements. Private HEIC samples are unnecessary for public tests and must stay outside public history.

Before any PR, resolve independent review findings, recheck changes and run applicable local checks. Use the PR template and report actual evidence; label plans as plans. Inspect staged paths and ensure `.agent-state/`, private fixtures, environments and generated reports/build outputs are absent. Commit/push the reviewed feature and create its PR against the verified base.

Lead routes PR comments to owners on the same branch. Rerun affected checks and obtain independent re-review before pushing corrections. Review evaluates each comment for reusable missed checks in `docs/review-guidance.md`; do not turn preferences into project requirements.

Never merge automatically. Completion requires verified merge into base, stopped workers and deletion of only that feature's local temporary state. Preserve permanent docs and review lessons. No next feature starts before then.
