# Monthly trip JSON

**Approved design; not implemented.** This is the serialization contract for [BRD R05 and R08-R14](BRD.md), including the four readings, field names, representations, structural metadata, date and duration rules. Artifact validation remains a gate before dependent implementation. No current command emits this format.

## File, captures and trip date

Write one `YYYY-MM.json` per assigned month, with exactly `schema_version` (integer `1`), `month` (`YYYY-MM`) and `trips` (array). Each trip appears once in one month. Existing entries remain unchanged; append new disjoint trips, skip exact repeats and report overlaps according to the BRD. Identity and recovery mechanisms remain [separate design gates](delivery-plan.md#incremental-output-and-recovery).

Each trip has exactly `trip_date`, `first_capture_times`, `last_capture_times`, `month_assignment` and `fields`. Public JSON contains no photo paths, hashes, per-field provenance or generated trip ID.

The capture arrays keep the distinct original timestamp spellings at the earliest and latest instant, sorted lexically. An array allows two photos taken at the same instant with different offsets to retain both original representations without arbitrarily choosing a photo. These are bounds, not every photo's metadata. Preserve original date, time, fractional precision when present and signed offset (`YYYY-MM-DDTHH:MM:SS[.fraction]+HH:MM` or negative offset); preserve supplied `-00:00`. Do not invent fractional digits or rewrite these timestamps as UTC. Both arrays describe the same instant for a one-instant trip.

Month ownership follows BRD R08: use the common metadata-local month of the latest captures. Only when equally latest captures have different local months, use their shared instant's UTC month, set `month_assignment` to `latest_instant_utc` and report the exception; otherwise use `latest_capture_local`. Different offsets alone do not trigger UTC assignment.

**Trip-date derivation:** `trip_date` is a `YYYY-MM-DD` string from the last capture's original local date when equally latest captures agree on that date. For the approved differing-local-month exception, use their shared instant's UTC date so date and owning month agree. Never derive it from a dashboard clock, filename or file modification time. Preserve the converter's supported date/offset range without overflowing during UTC calculations; an out-of-range UTC date needs a reported preflight failure rather than truncation or wraparound.

When equally latest captures have different local days within the same month, use the greatest local calendar date among those captures and report the ambiguity. This keeps the date within the owning month. Do not silently use a UTC date that could move the date into a previous month.

Order newly appended trips by earliest capture instant, preserving input order on equal earliest instants; append after existing entries. This is not a durable identity or global chronological ordering across runs.

## Four readings

Every key below is present. A reading is JSON `null` when no clear reading exists anywhere in the trip. Otherwise it has exactly `value` (string) and `unit` (string or JSON `null`). Missing odometer does not block the other readings. No other dashboard observations are retained or serialized; necessary layout anchors are recognition context only.

| Key | Value | Unit |
| --- | --- | --- |
| `trip_distance` | Exact decimal text; miles driven | Literal displayed unit, such as `mi` |
| `trip_duration` | Elapsed hours and minutes as `hh:mm` | `null` when no unit is printed |
| `trip_average_mpg` | Exact decimal text; Trip Average | Literal displayed `MPG` |
| `odometer` | Exact decimal text when present | Literal displayed unit, such as `mi` |

Decimal strings keep the displayed precision without floating-point rounding: `"42.0"` remains `"42.0"`. Preserve an explicit minus sign, use ASCII digits and at most one decimal point with digits on both sides, and allow no exponent, NaN or infinity. A clear `"0"` or `"0.0"` is a value, never null. Do not infer or convert units; `MPG` does not establish US versus imperial MPG. A required but unreadable unit makes the reading unclear. The whole reading is null when unavailable; `unit: null` instead means a clear reading has no printed unit.

Select independently through the [latest-clear candidate contract](field-selection.md). A later absent or unclear field leaves an earlier clear value eligible. At the equally latest clear instant, exactly parsed decimal values and identical literal units collapse; conflicting values or units stop preflight and are reported. `"0"` and `"0.0"` compare equal, including signed zero. For equal values with different spellings choose the lexically smallest original string, solely for deterministic serialization. Duration equality uses its normalized hours/minutes; never select conflicts by input order or OCR confidence.

Duration hours have at least two digits (left-pad a single digit), with no arbitrary 99-hour ceiling; minutes have exactly two digits from `00` to `59`. Do not emit decimal hours. Report a malformed later duration and exclude it as a clear candidate; an earlier valid duration remains eligible under independent latest-clear selection. Emit null only when no valid clear duration exists.

## Synthetic example

All timestamps and values below are authored examples, not private sample readings or OCR results. This single trip illustrates the four readings, explicit date, units and unavailable odometer.

```json
{
  "schema_version": 1,
  "month": "2031-06",
  "trips": [
    {
      "trip_date": "2031-06-12",
      "first_capture_times": ["2031-06-12T16:10:00.120-07:00"],
      "last_capture_times": ["2031-06-12T16:11:15.340-07:00"],
      "month_assignment": "latest_capture_local",
      "fields": {
        "trip_distance": {"value": "42.0", "unit": "mi"},
        "trip_duration": {"value": "02:16", "unit": null},
        "trip_average_mpg": {"value": "41.2", "unit": "MPG"},
        "odometer": null
      }
    }
  ]
}
```

## Validation and remaining gates

Names, value/unit/null representation, capture arrays, date rules and deterministic equality/spelling are approved. No validator library or schema implementation is added here. Planned checks cover exactly these four keys, excluded-data absence, independent selection, zero/null, malformed-duration exclusion with earlier-valid eligibility, date/month consistency, offset-distinct ties, UTC exception, extreme dates, repeats and unchanged existing entries. Public examples remain synthetic; private photos and labels remain ignored. Artifact, OCR accuracy and batch recovery gates are separate.
