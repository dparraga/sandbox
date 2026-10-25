# Latest-clear field candidates

**Approved and implemented internally.** This candidate-selection contract supports [BRD R09-R11](BRD.md) and [TRD T06](TRD.md). It identifies the latest clear observations for one field without defining a dashboard schema, judging readability or resolving equal-time field conflicts. Validation evidence belongs in the feature PR and ignored state.

## Scope and interface

One pure function in `src/flex_photo/selection.py`:

`latest_clear_indices(capture_times: Sequence[datetime], clear_flags: Sequence[bool]) -> tuple[int, ...]`

The caller supplies one already-grouped trip's timestamps and a matching flag for each observation of one field. `True` means the caller has established that field is clearly readable; `False` covers both absent and unclear. The function does not establish clarity from OCR confidence or inspect values. The caller retains values and observation identity, and calls the function independently for every field. No field names, value types, unit rules, reading class or extraction schema are introduced.

Output indices refer to this function's input sequences. A future caller using the [grouping API](trip-grouping.md) maps them through that group's original indices to recover photo observations. Do not pass multiple trips as one call. Selection does not repeat grouping or validate trip identity/window; the approved inclusive first-to-last bound, default three minutes, remains unchanged.

## Behavior and acceptance criteria

1. Accept finite `collections.abc.Sequence` inputs of equal length. Require timestamps to be standard-library `datetime` values whose `tzinfo` is a `datetime.timezone` instance, matching the approved [capture-time converter](capture-time.md). Reject naive, geographic/custom-timezone and non-datetime inputs. Require actual `bool` flags; never interpret values such as `0`, `1`, strings or field values by truthiness. Empty matching inputs return `()`; iterators/generators are unsupported.
2. Return all indices with a `True` flag at the greatest clear capture instant, in original input order. A single latest clear observation yields a one-element tuple. Empty output means no clear observation, including an empty trip. Unsorted input is supported. Never mutate either input or retained timestamps.
3. Ignore newer observations marked `False`. For timestamps at minutes 0, 1 and 2, flags `(True, False, False)` return `(0,)`; `(False, True, True)` return `(2,)`; all false return `()`. Different fields may therefore select different photos. A clear value of zero remains eligible when its supplied flag is `True`.
4. Compare aware datetimes directly by instant, including equivalent instants with different fixed offsets, date boundaries and microseconds. Preserve the converter's full supported date/offset range. Do not normalize through UTC, use float/POSIX timestamps or add a duration. Reuse the overflow-safe aware comparison basis documented in the approved [grouping contract](trip-grouping.md#behavior-and-acceptance-criteria).
5. Retain every tied latest clear candidate. For equal instants with flags `(True, True)`, return `(0, 1)` without inspecting whether the values agree. The output order records caller identity only; it never authorizes selecting the first or last candidate. Older ties do not matter when a later clear observation exists. This preserves ambiguity without selecting a winner, rejecting a trip or treating the field as unreadable.
6. Validate both outer containers in argument order, then matching lengths, then all timestamps in input order, then all flags in input order, before selection. Raise `TypeError` for wrong containers, timestamp/flag types and unsupported timezone types; raise `ValueError` for unequal lengths or naive timestamps. Use fixed diagnostics containing no supplied values, paths or metadata; emit no logs/output. Abort an invalid call without a partial result. Future batch failure handling remains separate.

A future value/serialization layer can use the sole candidate's value or emit JSON `null` when there are no candidates. Multiple candidates require an approved resolution policy before emitting a field winner. This component does not serialize JSON or complete end-to-end R09-R11 acceptance.

## Decisions and boundaries

Approval covers this API, bool-mask interpretation, candidate-result semantics and validation behavior. Returning tied candidates preserves evidence for later value resolution. The confirmed business rule stops preflight and reports conflicting equally latest clear readings; identical-value collapse remains open. This component neither inspects values nor implements those batch policies.

All available displayed dashboard fields remain required for later extraction and independent selection, including additional fields discovered in samples. Trip distance, `hh:mm` trip duration, EV driving ratio, average MPG, odometer, remaining range and dashboard clock stay distinct. Capture metadata supplies selection time; dashboard clock never substitutes for it. Readability criteria, OCR/layout recognition, value normalization, schema, timestamp batch handling, month assignment, CLI orchestration, moves and monthly output remain outside this feature.

## Design, alternatives and cost

A single-field index function reuses grouping's caller-owned observation identity and avoids speculative value/schema abstractions. A timestamp sequence plus bool mask distinguishes eligibility from field-value truthiness while keeping absent and unclear equivalent for this rule. Retaining tied indices avoids inspecting arbitrary values or adopting a conflict policy. Returning one index would silently choose a tie winner; rejecting every tie would also reject agreeing values and add an unapproved failure policy. A field dictionary or reading class is unnecessary until extraction has an approved representation.

Scan once after validation: O(n) time and O(n) worst-case auxiliary/result space when candidates tie. No sorting, dependency, model, network call, filesystem access or new framework is needed. Reuse the standard library, existing package and test automation. Preserve the current project license and dependency pins. No external API fees or new license obligations are introduced; local compute/storage and existing CI usage still have costs. No workload or performance target is approved, and private samples are unnecessary for this pure component.

## Validation requirements

Cover empty/singleton/unsorted inputs; newest clear selection; retention across newer absent/unclear flags; all-false input; independent masks that select different photos; clear zero-valued caller observations; unchanged inputs; equal and equivalent-offset ties; offset-driven order reversal; microseconds, midnight/month/year transitions and converter date/offset extremes. Verify that no candidate order implies a winner. Cover invalid containers, lengths, timestamp/timezone/flag types, validation order and fixed diagnostics.

Compose synthetic converter output, grouping and per-field candidate selection through installed-package tests outside the checkout, explicitly mapping group-local indices back to source observations. Reuse applicable Windows/Linux CPython 3.13/3.14 and network-disabled, read-only, nonroot container checks; update package/container payload assertions only as needed. Preserve existing CLI, discovery, reader, converter and grouping behavior. These are planned requirements, not executed results. Record actual evidence and outstanding work in the PR and ignored feature state.
