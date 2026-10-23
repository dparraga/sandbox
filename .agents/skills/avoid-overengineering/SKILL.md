---
name: avoid-overengineering
description: Keep this project's designs, code, tests and documentation proportional to the approved feature and demonstrated needs.
---

# Avoid overengineering

Read the active requirements, approved scope and existing implementation before choosing a solution. Prefer the simplest approach that satisfies them; reuse existing interfaces, dependencies and automation where suitable.

- Justify new dependencies, abstractions, interfaces, configuration, infrastructure, services, documents or other files with a current requirement or demonstrated limitation. Explain the practical benefit and cost of a necessary addition.
- Defer speculative extensibility, generalized frameworks, optional features and unrelated cleanup. A possible future need is not a present requirement.
- Keep documentation and tests proportional to the behavior and risk. Use one authoritative contract, focused behavioral checks and existing test infrastructure; avoid duplicate specifications and tests that merely mirror implementation details.
- Preserve approved constraints and demonstrated security or reliability protections. Simplification must address the evidence behind a safeguard, not remove it because it adds code. Prefer a smaller safe alternative when one meets the same need.

When proposing or reviewing a change, identify what is needed now, what existing mechanism can serve it and which optional work can remain deferred. Do not turn this check into additional product features or a lengthy process artifact.
