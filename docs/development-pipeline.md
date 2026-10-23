# Development pipeline

## Roles and environment

Use [shared instructions](../AGENTS.md) and six role contracts under `agents/`. Lead coordinates; Architect designs/researches; Implementation codes approved work; Testing owns tests/automation; Documentation maintains verified instructions; independent Review assesses proposals and changes.

Use background workers where supported and verify capability in each session. Respect concurrency limits and assign one writer per file. Role Markdown does not launch agents. Unattended operation after closing the app is not established.

Before documentation changes, load [project-documentation](../.agents/skills/project-documentation/SKILL.md). Codex discovers repository skills under `.agents/skills` from the working directory through the repository root, reads skill metadata for selection and loads the body when selected. AGENTS.md requires direct loading as a fallback. `CLAUDE.md` imports the same skill and shared instructions; live Claude execution and a skill-picker UI have not been tested. See official [Codex skills](https://learn.chatgpt.com/docs/build-skills) and [Claude imports](https://code.claude.com/docs/en/memory).

## Sequence and gates

1. Inspect repository/status/remotes/base, preserve unrelated work, create feature branch; ignore local state before use. If no usable base exists, coordinate initialization.
2. Architect researches/proposes; independent Review evaluates; Architect addresses findings. Lead presents both reports and open decisions. Wait for explicit implementation approval. Keep scoped approval evidence in ignored feature state.
3. After approval and the previous feature's verified merge/cleanup: Implementation and Testing work in parallel. Documentation stays synchronized; runnable increments trigger tests promptly. Keep interfaces coordinated and file ownership explicit.
4. Before every PR, including planning: independent review of all changes; resolve/recheck findings; applicable local tests/checks; inspect staged files; commit/push/create PR. Verify actual GitHub checks on the PR; distinguish workflow configuration from successful runs.
5. Lead triages every PR comment to relevant owners, correct on same branch, rerun affected checks, obtain Review recheck before pushing corrections. Review records reusable lessons and evaluates each comment for misses.
6. Human merges. Lead verifies actual merge into base, stops workers and cleans only the feature's local state. Only then begin another feature.

## State and handoffs

Keep temporary status, reports, approval evidence, results, handoffs and resume instructions only in ignored `.agent-state/<feature>/`. Lead owns overall status; each worker owns its handoff. Save after meaningful milestones and safe stopping points. Keep permanent requirements/design current and reusable lessons in [review guidance](review-guidance.md).

On interruption, inspect saved state and actual Git/PR state before continuing; do not assume the last action completed. Approval remains scoped across pauses. Preserve active state until verified merge, then stop workers and remove only the resolved feature's workspace-contained state directory. Preserve unrelated files, samples and durable fixture inventory. Recovery requires this laptop and intact saved state; unsaved context is not guaranteed.
