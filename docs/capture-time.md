# Capture-time conversion

**Approved and implemented.** This is the authoritative contract for converting the existing [capture metadata](capture-metadata.md) into usable original-capture times, supporting BRD R05/R06/R14 and TRD T05. Raw metadata extraction remains unchanged.

## Scope and acceptance criteria

1. Provide one pure internal function, `parse_capture_time(metadata: CaptureMetadata) -> datetime`, in `src/flex_photo/capture_time.py`. Return a fixed-offset, timezone-aware standard-library datetime. Preserve the supplied local date/time, offset and supported fractional value; do not normalize to UTC, serialize, perform I/O or mutate the input. Original metadata remains available for exact text, including trailing fractional zeros and the sign of a zero offset.
2. Require `date_time_original` in exactly `YYYY:MM:DD HH:MM:SS`, using ASCII digits. Validate Gregorian dates and clock fields; years range from 0001 through 9999. Reject alternate formats, surrounding whitespace, zero dates and leap seconds.
3. Require `offset_time_original` in exactly `+HH:MM` or `-HH:MM`, with ASCII digits, hours 00–23 and minutes 00–59. Preserve this fixed offset without claiming a geographic timezone. Never infer an offset from the machine or another source.
4. Represent absent (`None`) `subsec_time_original` with microsecond zero at the available whole-second resolution; this does not establish measured fractional precision or change the raw `None`. Present values must contain one through six ASCII digits; right-pad to six for exact numeric conversion. Reject empty, nondecimal or longer values without rounding or truncation. Check lengths before numeric conversion.
5. Raise `CaptureTimeError` for rejected values, with fixed `field` values naming the three input fields and fixed `reason` values `missing`, `invalid` or `unsupported precision`. Validate date, offset and subseconds in that order. Its public string contains no raw metadata, paths or underlying exception text; print and log nothing. Component errors do not decide whether a future batch skips a photo or stops.
6. Add no CLI, batch workflow, configuration, fallback fields, timezone database, grouping, timestamp-tie policy, moves, JSON schema, decoding, recognition or OCR. Do not use float/POSIX timestamp conversion. The three-field capture scope is separate from the four approved dashboard readings in [BRD R05/R14](BRD.md); capture metadata supplies trip date. The confirmed inclusive first-to-last trip window, default three minutes, and `hh:mm` trip duration remain unchanged.

## Design and tradeoffs

Reuse immutable `CaptureMetadata`, standard-library `datetime` and existing package/test conventions. No new dependency, infrastructure, license obligation or processing network access is needed. Preserve the ExifRead pin and parser safeguards; this converter does not replace the reader.

Requiring an explicit offset prevents silent timezone assumptions and mixed aware/naive comparisons, but leaves photos without offsets without a usable timestamp. A naive result preserves wall time without establishing an instant. Rejecting fractions beyond six digits preserves numeric fidelity within datetime's precision; supporting arbitrary precision would require a more complex representation. Exact original text remains available in either case.

Validation is bounded by fixed field sizes. Reuse existing automation rather than adding benchmark infrastructure or targets. Costs are local CPU/test storage and existing CI usage; startup/discovery measurements do not establish converter throughput.

## Validation requirements

Cover valid/leap dates; invalid calendar, clock, syntax and non-ASCII inputs; signed/zero/nonwhole-hour offsets; missing offsets; absent and one-to-six-digit fractions; longer or malformed fractions; deterministic sanitized errors; unchanged input; and independence from I/O/environment settings.

Verify reader-to-converter composition through installed-library tests outside the checkout, the existing Windows/Linux Python 3.13/3.14 matrix, and an actual network-disabled, read-only, nonroot container. Update exact wheel payload/container checks only as needed. Use disposable private sample copies and existing manifest evidence, publishing aggregate results only. Preserve existing reader/CLI/discovery checks. These are acceptance requirements; actual results and outstanding validation belong in the PR and ignored feature state.

## Policy boundaries

Approval covers the required explicit offset, rejection of fractions longer than six digits, and strict original-only conversion/error contract. Future processing follows the confirmed [BRD](BRD.md) rules for excluded timestamps, equal-time values, month assignment and reporting. Those batch rules do not change this converter or its sanitized rejection contract.

Technical basis: official Python [3.13 datetime](https://docs.python.org/3.13/library/datetime.html) and [3.14 datetime](https://docs.python.org/3.14/library/datetime.html). Their representation limits support the approved strict grammar and rejection policies above.
