# Trip grouping

**Approved and implemented.** This is the authoritative internal grouping contract for [BRD R06/R07](BRD.md) and [TRD T06](TRD.md). Qualifying dashboard photos within the configured first-to-last grouping window belong to the same trip; no additional trip-identity validation is required.

## Scope and interface

Provide one pure function in `src/flex_photo/grouping.py`:

`group_capture_times(capture_times: Sequence[datetime], window: timedelta = timedelta(minutes=3)) -> tuple[tuple[int, ...], ...]`

The caller supplies a finite sequence of timestamps corresponding to already-qualified photo observations. Return groups of zero-based original input indices; the caller retains the observations, original timestamps and raw metadata. This avoids introducing a photo/reading schema, wrapper class or callback before extraction is designed. The function neither reads metadata nor decides whether a photo qualifies. Do not mutate inputs, deduplicate observations or select field values.

## Behavior and acceptance criteria

1. Accept standard-library `datetime` values whose `tzinfo` is a `datetime.timezone` instance, matching the fixed-offset output of the approved [capture-time converter](capture-time.md). Support its full date/offset/microsecond range. Reject naive values, non-datetimes and geographic/custom timezone objects. No machine timezone inference, fallback or conversion of the retained timestamp is allowed.
2. Require a `timedelta` window greater than or equal to zero. Zero groups only equal instants; accept any representable nonnegative `timedelta` without an arbitrary upper limit. Validate the window first, even for empty input, then require the outer input to satisfy `collections.abc.Sequence`, then validate timestamps in input order. Iterators/generators are unsupported. Raise `TypeError` for wrong types (including the outer container and unsupported timezone types) and `ValueError` for naive timestamps or a negative window. Use fixed diagnostics without raw input values; emit no output or logs. Rejection aborts this call without a partial result; future batch handling remains separate.
3. Sort input indices by capture instant ascending, preserving original input order for equal instants, including equivalent instants with different offsets. Every input index appears exactly once. Empty input returns `()`; each returned group is nonempty and chronological, and groups are ordered by their earliest member.
4. Anchor each group at the earliest unassigned instant. Include subsequent sorted captures while `capture - anchor <= window`; the first outside starts the next group. For example, inputs at minutes 0, 2 and 4 with the default window return `((0, 1), (2,))`. Consecutive two-minute gaps never extend the first group to minute 4. A capture exactly three minutes after its anchor is included; one microsecond later is excluded.
5. Compare elapsed instants across differing fixed offsets, date/month/year boundaries and microseconds. Use direct aware-datetime comparison/subtraction and compare the resulting duration with the window. Do not construct `anchor + window`, normalize through `astimezone(UTC)`, or use float/POSIX timestamps: adding or normalizing can overflow at converter-supported date extremes. Fixed offsets make direct comparisons appropriate even when objects share a timezone instance. Python documents overflow-safe aware comparison/subtraction in its [datetime operations](https://docs.python.org/3.13/library/datetime.html#datetime-objects).

## Decisions and limitations

Earliest-unassigned anchoring creates one deterministic partition while enforcing the first-to-last bound. Stable equal-time input order preserves caller identity without choosing a newest or winning reading. Later value resolution and month assignment follow the confirmed [BRD](BRD.md) rules; grouping order is not a tie-breaking policy.

The caller supplies already-qualified observations; grouping does not perform layout recognition. Readability validation, artifact/schema approval and detailed move/output mechanics remain gates in the [delivery plan](delivery-plan.md). Confirmed batch exclusions, value resolution and month rules do not change this pure grouping component. All available dashboard fields remain required for later extraction and independent latest-clear selection.

No CLI, configuration parser, I/O, decoding, recognition/OCR, field extraction/selection, serialization, trip identifiers, dependencies, model assets or framework are included.

## Design and cost

Reuse the standard library, converter output and existing package/test automation. Sort indices once, then scan once: O(n log n) time and O(n) auxiliary/output space. Caller input must fit memory; no workload or performance target is approved. No network processing, added license obligation or external API cost is introduced; local compute/storage and existing CI usage still have costs. Private samples are unnecessary for this pure component and must remain unpublished. Preserve the existing project license.

## Validation requirements

Cover empty/singleton/unsorted input; complete index coverage and unchanged input; inclusive boundary and one-microsecond exclusion; no gap chaining; equal and equivalent-offset instants with stable order; offset-driven order reversal; midnight/month/year crossings; year 1/9999 with extreme offsets; zero, negative, wrong-type and maximum windows; invalid container/timestamp/timezone inputs, validation order and fixed diagnostics. Compose converter outputs with grouping through installed-package tests. Reuse applicable Windows/Linux Python 3.13/3.14 and restricted-container checks, updating payload assertions only as needed. Preserve existing reader/discovery/CLI behavior. Actual results and outstanding validation belong in the PR and ignored feature state.
