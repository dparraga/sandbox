# Contributing

Read [AGENTS.md](AGENTS.md), [BRD](docs/BRD.md), [TRD](docs/TRD.md) and the [pipeline](docs/development-pipeline.md). Keep one feature active. Inspect Git status/remotes/default branch and preserve unrelated changes. Create a feature branch from the current usable base; coordinate initialization if none exists. Current branch is `feature/planning-foundation`, base `main`.

Planning approval does not authorize application implementation. Architect proposal → independent Review → Architect corrections → Lead presents both reports → explicit user implementation approval. After approval, coding and test planning proceed in parallel, with documentation synchronized and tests run as soon as code is runnable.

Before any PR, resolve independent review findings, recheck changes and run applicable local checks. Use the PR template and report actual evidence; label plans as plans. Inspect staged paths and ensure `.agent-state/` and private fixtures are absent. Commit/push the reviewed feature and create its PR against the verified base.

Lead routes PR comments to owners on the same branch. Rerun affected checks and obtain independent re-review before pushing corrections. Review evaluates every comment for reusable missed checks in `docs/review-guidance.md`. Do not invent project requirements from personal preferences.

Never merge automatically. Completion requires verified PR merge into base, stopped workers and deletion of only that feature's local temporary state. No next feature until then. No application tests or CI are operational in this planning feature; [testing plan](docs/testing-plan.md) describes later validation.
