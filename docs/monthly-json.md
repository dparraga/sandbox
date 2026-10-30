# Monthly trip JSON

**Implemented serialization contract.** This is the serialization contract for [BRD R05 and R08-R14](BRD.md), including the four readings, field names, representations, structural metadata, date and duration rules. The batch command emits this format; authored composition tests and real private-photo acceptance remain distinct checks.

## File, captures and trip date

Write one `YYYY-MM.json` per assigned month, with exactly `schema_version` (integer `2`; legacy `1` remains readable), `month` (`YYYY-MM`) and `trips` (array). Each trip appears once in one month. Existing non-null values, trip order and memberships remain unchanged; append disjoint trips, skip exact repeats and report overlaps. Legacy monthly files convert to sparse schema 2 through the verified rewrite transaction in the delivery design before a new append. The delivery plan defines [identity and overlap reconciliation](delivery-plan.md#repeat-identity-and-overlap-reconciliation) and [recovery](delivery-plan.md#durable-effects-and-safe-resume).

Each trip has exactly `trip_date`, `first_capture_times`, `last_capture_times`, `month_assignment` and `fields`. Public JSON contains no photo paths, hashes, per-field provenance or generated trip ID.

The capture arrays keep distinct selected timestamp spellings at the earliest/latest instant, sorted lexically. Original metadata retains its exact spelling; fallback provenance is private and reported under the delivery design. An array allows two photos taken at the same instant with different offsets to retain both original representations without arbitrarily choosing a photo. These are bounds, not every photo's metadata. Preserve original date, time, fractional precision when present and signed offset (`YYYY-MM-DDTHH:MM:SS[.fraction]+HH:MM` or negative offset); preserve supplied `-00:00`. Do not invent fractional digits or rewrite these timestamps as UTC. Both arrays describe the same instant for a one-instant trip.

Month ownership follows BRD R08: use the common local month of the latest selected captures. Only when equally latest captures have different local months, use their shared instant's UTC month, set `month_assignment` to `latest_instant_utc` and report the exception; otherwise use `latest_capture_local`. Different offsets alone do not trigger UTC assignment.

**Trip-date derivation:** `trip_date` is a `YYYY-MM-DD` string from the latest selected capture's local date when equally latest captures agree on that date. For the approved differing-local-month exception, use their shared instant's UTC date so date and owning month agree. Never derive it from a dashboard clock or modification time. The approved creation/filename fallback hierarchy is defined in BRD R04 and the delivery design; no date-only time is invented. Preserve the converter's supported date/offset range without overflowing during UTC calculations; an out-of-range UTC date needs a reported preflight failure rather than truncation or wraparound.

When equally latest captures have different local days within the same month, use the greatest local calendar date among those captures and report the ambiguity. This keeps the date within the owning month. Do not silently use a UTC date that could move the date into a previous month.

Order newly appended trips by earliest capture instant, preserving input order on equal earliest instants; append after existing entries. This is not a durable identity or global chronological ordering across runs.

## Four readings

Only available readings below are present. A missing reading means null. Each present reading has `value` (string) and a literal `unit` when applicable; omit a null-valued unit, so duration normally has only `value`. An all-unavailable trip retains `fields: {}`. New monthly JSON contains no null-valued properties; legacy explicit nulls remain readable. Missing odometer does not block the other readings. No other dashboard observations are retained or serialized; necessary layout anchors are recognition context only.

| Key | Value | Unit |
| --- | --- | --- |
| `trip_distance` | Exact decimal text; miles driven | Literal displayed unit, such as `mi` |
| `trip_duration` | Elapsed hours and minutes as `hh:mm` | Omitted when no unit is printed |
| `trip_average_mpg` | Exact decimal text; Trip Average | Literal displayed `MPG` |
| `odometer` | Exact decimal text when present | Literal displayed unit, such as `mi` |

Decimal strings keep the displayed precision without floating-point rounding: `"42.0"` remains `"42.0"`. Preserve an explicit minus sign, use ASCII digits and at most one decimal point with digits on both sides, and allow no exponent, NaN or infinity. A clear `"0"` or `"0.0"` is a value and is never omitted. Do not infer or convert units; `MPG` does not establish US versus imperial MPG. A required but unreadable unit makes the reading unclear. Omit the whole reading when unavailable. A missing duration unit means no printed unit; a numeric reading still requires its literal displayed unit.

Select independently through the [latest-clear candidate contract](field-selection.md). A later absent or unclear field leaves an earlier clear value eligible. At the equally latest clear instant, exactly parsed decimal values and identical literal units collapse; conflicting values or units stop preflight and are reported. `"0"` and `"0.0"` compare equal, including signed zero. For equal values with different spellings choose the lexically smallest original string, solely for deterministic serialization. Duration equality uses its normalized hours/minutes; never select conflicts by input order or OCR confidence.

Duration hours have at least two digits (left-pad a single digit), with no arbitrary 99-hour ceiling; minutes have exactly two digits from `00` to `59`. Do not emit decimal hours. Report a malformed later duration and exclude it as a clear candidate; an earlier valid duration remains eligible under independent latest-clear selection. Omit duration only when no valid clear duration exists.

## Synthetic example

All timestamps and values below are authored examples, not private sample readings or OCR results. This single trip illustrates the four readings, explicit date, units and unavailable odometer.

```json
{
  "schema_version": 2,
  "month": "2031-06",
  "trips": [
    {
      "trip_date": "2031-06-12",
      "first_capture_times": ["2031-06-12T16:10:00.120-07:00"],
      "last_capture_times": ["2031-06-12T16:11:15.340-07:00"],
      "month_assignment": "latest_capture_local",
      "fields": {
        "trip_distance": {"value": "42.0", "unit": "mi"},
        "trip_duration": {"value": "02:16"},
        "trip_average_mpg": {"value": "41.2", "unit": "MPG"}
      }
    }
  ]
}
```

## Validation and remaining gates

Sparse schema 2 names, omission-as-null semantics, capture arrays, date rules and deterministic equality/spelling are approved. No validator library or schema implementation is added here. Checks cover allowed optional reading keys, excluded-data absence, independent selection, zero/null, malformed-duration exclusion with earlier-valid eligibility, date/month consistency, offset-distinct ties, UTC exception, extreme dates, repeats and unchanged existing entries. Public examples remain synthetic; private photos and labels remain ignored. Artifact, OCR accuracy and batch recovery gates are separate.
