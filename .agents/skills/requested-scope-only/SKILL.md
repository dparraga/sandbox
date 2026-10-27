---
name: requested-scope-only
description: Keep proposals, implementation, tests, and documentation within the user's approved scope. Preserve decisions, enforce approval boundaries, and allow routine technical autonomy.
---

# Requested scope only

Work only within the scope authorized by the user and recorded project decisions.

Before starting, review the current request, relevant approved requirements, existing implementation, active feature state, and authoritative contracts.

Every material change must support an explicit requirement, an approved decision, or a necessary correction to authorized behavior.

## Scope and authorization

- **Distinguish authorization levels.** Permission to investigate, design, propose, or review does not automatically authorize implementation.
- **Respect approval boundaries.** Agent recommendations, reviewer suggestions, assumptions, and proposed improvements are not user authorization.
- **Preserve confirmed decisions.** Do not reopen settled decisions without new evidence, conflicting requirements, or an explicit user request.
- **Implement only authorized work.** Do not add features, behaviors, dependencies, or architectural changes outside the approved scope.
- **Respect execution boundaries.** Work only on features authorized for the current execution. Multiple features may be implemented together when explicitly approved.

## Agent autonomy

Agents may independently make routine implementation decisions necessary to satisfy approved requirements, including internal code structure, naming, and appropriate tests.

Do not request additional approval for ordinary technical choices that remain within approved constraints.

Escalate through Lead when a decision would materially affect:

- User-visible behavior or established contracts.
- Approved scope, architecture, or significant dependencies.
- Security, privacy, reliability, performance requirements, or operating costs.
- Previously confirmed decisions.

Do not silently resolve such decisions by making assumptions.

## Ambiguities and blockers

- Distinguish confirmed requirements from assumptions, recommendations, and unresolved questions.
- Ask for clarification only when an ambiguity materially affects behavior, compliance, or implementation safety.
- Do not invent business rules, default behaviors, or acceptance criteria to resolve unresolved requirements.
- Continue with independently authorized work when an unresolved decision does not block it.
- Raise genuine blockers through Lead with the relevant evidence, impact, and available options.

## Scope changes and review feedback

- Do not implement unrelated improvements, speculative requirements, or opportunistic refactoring.
- Treat review comments as findings or recommendations, not automatic approval for additional scope.
- Correct defects within approved behavior without requiring new authorization unless the correction materially changes an approved decision or constraint.
- Report necessary out-of-scope changes through Lead rather than incorporating them silently.
- Preserve unrelated code and work unless modification is necessary for an approved change.

## Tests and documentation

- Test only approved behavior and meaningful failure scenarios.
- Do not encode unresolved assumptions as acceptance criteria or expected behavior.
- Update relevant existing documentation to reflect approved and implemented functionality.
- Do not document proposed features as implemented.
- Report verification results, limitations, and incomplete work accurately.

## Handoff and verification

Before handoff or review, verify that:

1. All material changes are supported by the current request or recorded approval.
2. No unapproved features or behaviors were introduced.
3. Unresolved decisions remain unresolved rather than silently implemented.
4. Deferred work remains outside the implementation.
5. Reported implementation and test results reflect actual evidence.

Use existing project mechanisms to retain approval evidence and temporary feature state. Do not create additional tracking documents or approval processes solely to satisfy this skill.

**The goal is to complete authorized work independently and efficiently without expanding scope or making material decisions on the user's behalf.**