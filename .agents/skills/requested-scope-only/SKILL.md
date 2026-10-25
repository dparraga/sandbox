---
name: requested-scope-only
description: Keep this project's proposals and changes traceable to the user's request, confirmed decisions and scoped implementation approval.
---

# Requested scope only

Read the current user request, confirmed decisions, active feature state and authoritative contract before work. Trace proposed behavior and changed files to an explicit requirement, approved proposal or necessary correction. Keep one feature active and preserve unrelated work.

- Distinguish requirements and confirmed decisions from recommendations, assumptions and unresolved questions. An agent recommendation or reviewer suggestion is not user authorization. A proposal, planning permission or related approval does not authorize application implementation.
- Preserve settled decisions instead of reopening them. Ask about an ambiguity when it affects observable behavior; do not invent a policy or encode an unapproved expectation in tests.
- Carry out routine coding details needed to satisfy approved behavior without seeking approval for each choice. Obtain explicit user approval through Lead before material changes to behavior, scope, dependency choices, cost or risk.
- Defer unrelated improvements, new features and speculative requirements. Raise a necessary out-of-scope issue with its evidence and impact rather than silently including it.
- Keep test coverage and documentation aligned with the authorized behavior. Report implemented and verified capabilities accurately, including limitations; do not imply approval or results that do not exist.

Before handoff or review, check that each change serves the request or a recorded approval and that deferred work remains deferred. Keep approval evidence and temporary reasoning in the ignored feature-state folder.
