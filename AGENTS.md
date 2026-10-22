# Shared project instructions

## Scope and authority

- Lead is the user's communication point. Keep scope simple; ask about ambiguity and do not add features.
- Current feature: **Planning foundation**, branch `feature/planning-foundation`, base `main`. Only planning documents and verified agent configuration are authorized. No application code, executable tests, Dockerfiles, or Actions workflows in this feature.
- Requirements live in [BRD](docs/BRD.md); proposals and decision status live in [TRD](docs/TRD.md). Proposals are not approvals. Existing LICENSE is preserved pending the user's license decision.
- Work on one feature at a time, always on a feature branch. Inspect status, remotes, base and existing changes first. Never bypass an absent usable base; coordinate initialization with the user.
- Preserve unrelated files and changes. Do not fabricate photos, readings, results, approvals, or operational capabilities.

## Roles and delegation

Role contracts: [Lead](agents/lead.md), [Architect](agents/architect.md), [Implementation](agents/implementation.md), [Testing](agents/testing.md), [Documentation](agents/documentation.md), [Review](agents/review.md).
Use separate background workers where supported; verify capability each environment/session. Role Markdown does not launch workers. Respect concurrency limits, use bounded assignments, and assign one writer per file. Roles may be activated sequentially; never represent self-review as independent review. If independent workers are unavailable, tell the user and arrange independent review before a PR.

## Gates and completion

1. Architect researches authoritative sources and proposes a design; separate Review evaluates it; Architect addresses findings; Lead presents both reports. Explicit user approval is required before application implementation. Planning/PR approval is not implementation approval.
2. After approval, Implementation codes the approved feature while Testing plans tests in parallel. Documentation stays synchronized. Tests run as soon as applicable code is runnable.
3. Every feature, including documentation, needs independent review before PR creation. Resolve findings, recheck, and run applicable local tests before creating the PR. State accurately what ran and what remains planned.
4. Lead routes PR comments; corrections stay on the same branch; affected tests rerun; Review rechecks before pushing corrections. Review evaluates every comment for missed checks and records reusable lessons in `docs/review-guidance.md`, without promoting every preference into a requirement.
5. Never merge automatically. A feature completes only after its PR is verified merged into base. Do not start the next feature until its temporary state is cleaned up.

## Local state and safe resume

Ignore `.agent-state/` before writing temporary files. Use `.agent-state/<feature>/` for phase, branch/commits, assignments, progress, questions, approval evidence, reports, results and next actions. Each agent owns a separate handoff; Lead owns overall status. Save after meaningful milestones. Verify no temporary state is staged before every commit.
On pause, stop at a safe boundary and save all handoffs. On resume or interruption, inspect saved state and actual Git/PR state before acting; sessions may need recreation. Recovery requires this laptop and intact local state; unsaved context is not guaranteed. Retain state while PR is open. After verifying merge, stop feature workers and delete only that feature's resolved, workspace-contained state folder.

## Code review rules

Review correctness, performance, security, maintainability, best practices, tests, documentation and cost where applicable. Enforce fully offline photo processing, free/open-source dependencies and models, bounded first-to-last trip windows, independent latest-clear field selection, and preservation of unresolved decisions. Follow [review guidance](docs/review-guidance.md).
