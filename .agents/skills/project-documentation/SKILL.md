---
name: project-documentation
description: Maintain this repository's requirements, design, feature, setup, testing, and agent documentation with concise current-state content and traceable contracts.
---

# Project documentation

Read this skill before creating or modifying project documentation. Inspect the relevant requirements, approved contract, actual code and configuration, and available validation evidence. Review existing documents one at a time and reuse them rather than adding documents without a distinct purpose.

## Document purposes

- BRD: business objective, value, process, scope, business rules, and business acceptance criteria.
- TRD: technical requirements the solution must satisfy. Keep implementation mechanisms in design documents.
- Design documents: how requirements are met, including components, interfaces, and relevant tradeoffs.
- Feature stories: Story, Description, Scope, Acceptance Criteria, and Definition of Done where useful. Do not force irrelevant template sections into documents.

Give each requirement or feature contract one authoritative location and reference it elsewhere. Preserve requirement identifiers and useful links to design and tests. Keep terminology, commands, examples, and status consistent with actual code.

## Current state

Describe current requirements, approved design, implemented capabilities, limitations, and open decisions. Distinguish proposed, approved, implemented, and verified behavior. Implementation is not verification; a planned check or existing workflow is not a passed result. Do not invent requirements, approvals, targets, or results. Ask Lead about ambiguities affecting behavior.

Replace outdated descriptions when behavior changes. Remove obsolete status notes, superseded proposals, resolved questions, revision logs, and repetitive progress summaries. Preserve decisions and rationale that still explain the current design. Use Git and PRs for change history.

Keep temporary progress, reports, handoffs, approval evidence, and resume instructions only in the gitignored feature-state folder. Keep reusable review lessons as concise, actionable guidance rather than a chronology of comments.

## Writing and review

Include only information needed to understand, implement, operate, test, or maintain the project. Use plain English, active voice, short paragraphs, and descriptive headings. Avoid repetition, filler, lengthy introductions, unnecessary summaries, em dashes, and all-caps headings except established acronyms. Use lists and tables when they improve clarity.

When shortening text, preserve necessary rules, exceptions, constraints, acceptance criteria, and unresolved decisions. Do not change application behavior through documentation edits. Independently review changed documentation for accuracy, concision, consistency, purpose separation, authoritative references, and agreement with code and evidence before the feature PR or corrective push.
