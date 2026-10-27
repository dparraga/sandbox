---
name: avoid-overengineering
description: Keep this project's designs, code, tests and documentation proportional to the approved feature and demonstrated needs.
---

# Avoid overengineering

Implement the simplest maintainable solution that fully satisfies the approved requirements and constraints.

Before designing or implementing, review the relevant requirements, existing code, interfaces, dependencies, and established project conventions. Prefer extending or reusing existing mechanisms rather than introducing new ones.

## Core principles

- **Build only what is needed now.** Do not implement speculative features, extensibility, configuration, or infrastructure for hypothetical future requirements.
- **Prefer simplicity over abstraction.** Use straightforward code and existing patterns. Introduce abstractions, interfaces, inheritance, or design patterns only when they solve a concrete problem or meaningfully reduce complexity.
- **Minimize dependencies.** Prefer existing libraries and platform capabilities. Add dependencies only when their practical benefits justify their maintenance, security, and compatibility costs.
- **Avoid premature optimization.** Optimize when requirements, measurements, or demonstrated limitations justify it. Do not sacrifice clarity for hypothetical performance improvements.
- **Avoid excessive defensive programming.** Validate inputs and handle realistic failure scenarios at appropriate boundaries. Do not add redundant checks, unnecessary fallback paths, or elaborate error handling for unsupported scenarios.
- **Keep changes focused.** Avoid unrelated refactoring, cleanup, compatibility layers, or modifications outside the approved scope.
- **Keep tests proportional.** Test required behavior, important boundaries, and meaningful failure scenarios. Reuse existing test infrastructure. Avoid redundant tests and tests coupled unnecessarily to implementation details.
- **Keep documentation concise.** Maintain one authoritative source for each requirement or contract. Update existing documentation rather than creating overlapping documents.

## Preserve necessary safeguards

Simplicity must not compromise approved requirements, correctness, security, reliability, or maintainability.

Do not remove an existing safeguard solely because it adds complexity. Understand the risk it addresses and preserve the protection, using a simpler alternative when appropriate.

## Decision rules

Before introducing a new dependency, abstraction, configuration option, file, service, or infrastructure component, consider:

1. Is it required by the approved scope or a demonstrated technical limitation?
2. Can an existing mechanism satisfy the need adequately?
3. Does the benefit justify the additional complexity and maintenance cost?

If the addition is not justified, omit it.

When multiple solutions satisfy the requirements, prefer the one with fewer moving parts, clearer behavior, and lower ongoing maintenance costs.

## Agent behavior

Apply these principles throughout design, implementation, testing, and code review.

- Do not expand the approved scope to make the solution more complete or future-proof.
- Do not create additional deliverables merely to demonstrate compliance with this skill.
- When reviewing, flag unnecessary complexity and recommend a simpler alternative.
- Explain significant tradeoffs when they affect a decision or require approval.
- Otherwise, apply the skill without generating additional reports, checklists, or approval steps.

**The goal is not the fewest lines of code. It is the least complexity necessary to deliver a correct, secure, understandable, and maintainable solution.**