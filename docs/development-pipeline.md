# Development pipeline

## Roles and environment

Use [shared instructions](../AGENTS.md) and six role contracts under `agents/`. Lead coordinates; Architect designs/researches; Implementation codes approved work; Testing owns tests/automation; Documentation maintains verified instructions; independent Review assesses proposals and changes.

Verified during planning: installed VS Code-bundled `codex-cli 0.162.0-alpha.17.2`; GitHub CLI 2.92.0; this session's collaboration tools successfully launched separate workers. There are four concurrent slots including Lead, so six role definitions do not imply six simultaneous workers. Recheck capability when recreating sessions. Workers run during active orchestration; persistent unattended operation after closing the app is not established.

[Official subagent guidance](https://learn.chatgpt.com/docs/agent-configuration/subagents) describes delegation in IDE chat. [AGENTS.md guidance](https://learn.chatgpt.com/docs/agent-configuration/agents-md) establishes the shared instruction entry point. The current session can assign role files directly to workers; no extra launcher/configuration is necessary. Role Markdown does not launch agents. No unverified `.codex` or Claude worker configuration is included. `CLAUDE.md` points to shared rules; Claude execution was not tested.

## Sequence and gates

1. Inspect repository/status/remotes/base, preserve unrelated work, create feature branch; ignore local state before use. If no usable base exists, coordinate initialization.
2. Architect researches/proposes; independent Review evaluates; Architect addresses findings. Lead presents both reports and open decisions. Wait for explicit implementation approval. This planning PR does not supply that approval.
3. After approval, on the next authorized feature only after planning merge/cleanup: Implementation and Testing work in parallel. Documentation stays synchronized; runnable increments trigger tests promptly. Keep interfaces coordinated and file ownership explicit.
4. Before every PR, including planning: independent review of all changes; resolve/recheck findings; applicable local tests/checks; inspect staged files; commit/push/create PR. GitHub checks run afterward once implemented.
5. Lead triages every PR comment to relevant owners, correct on same branch, rerun affected checks, obtain Review recheck before pushing corrections. Review records reusable lessons and evaluates each comment for misses.
6. Human merges. Lead verifies actual merge into base, stops workers and cleans only the feature's local state. Only then begin another feature.

## Safe pause/resume on this laptop

Temporary records live only under ignored `.agent-state/<feature>/`. Lead owns `status.md`; each worker owns its handoff and reports. Record phase, branch/base/head commits, assignments, completed/remaining work, questions, approval evidence, results and next actions after milestones. Do not concurrently edit the same file. Keep lasting decisions in BRD/TRD and reusable review lessons tracked.

**Pause:** tell Lead “Pause Planning foundation.” Lead stops new assignments, brings workers to safe boundaries, gathers handoffs, records actual Git/PR state and outstanding actions, and reports the saved location. Preserve files; do not merge or delete active state.

**Resume:** open this same repository on this laptop with local state intact and tell Lead “Resume Planning foundation; read `.agent-state/planning-foundation/` and verify Git and PR state before acting.” Lead reads instructions/status/handoffs, runs `git status`, `git diff`, `git log`, verifies branch/remote/PR, checks approval evidence, recreates needed workers, and resumes the first uncompleted action. Inspect actual state after unexpected interruption/credit exhaustion; do not assume last commands completed. Unsaved context is not recoverable by promise.

Retain local state while PR is open. After merge verification and worker stop, resolve the exact feature directory under the workspace before deleting only that directory. Preserve other features' state and all permanent files. Verify `.agent-state/` is absent from staged paths before every commit.
