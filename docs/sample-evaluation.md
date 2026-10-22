# Local HEIC sample evaluation

Evaluated 2026-10-22 during Planning foundation. The user authorized `sample-pictures/` for evaluation and later testing. This is local sample analysis, not application implementation approval or consent to publish photos, previews, metadata or expected-reading labels. Originals are ignored and remain unchanged.

## Evidence obtained

- 16 HEIC files, 18,288,191 bytes total. All decoded on Windows using temporary Python 3.14.4, Pillow 13.0.0 and pillow-heif 1.8.1 installed under ignored local state. These evaluation versions do not select the application's runtime/dependencies or approve wheel redistribution.
- Each decoded image reports 4032 × 3024 pixels and one frame through this adapter. Oriented previews were visually inspected. This does not prove orientation handling for other files or enumerate every auxiliary HEIF item.
- Visual inspection identifies eight Drive Info and eight Trip Summary photos. No labeled nonmatching examples are present. Framing, glare, reflections, dust and perspective vary.
- Every file exposes `DateTimeOriginal`, `SubsecTimeOriginal` and `OffsetTimeOriginal`; the observed offset is `-07:00`. Filename hour differs from local capture hour in this dataset, consistent with the offset. Filenames remain identifiers, not the authoritative timestamp. Do not generalize a filename-time rule or assign an offset to files that lack one.
- An arithmetic check using the proposed 180-second first-anchor grouping gives eight candidate groups of two photos each, with first-to-last spans from 7.275 to 15.321 seconds. This is not application output or confirmation of real trip identity; the proposed grouping policy remains subject to approval.
- SHA-256 values were recorded before/after reading and independently rechecked against the local manifest: all 16 original byte contents are unchanged. No original was moved or rewritten.

## Layout and design implications

Drive Info shows trip distance, Trip Time and remaining range. Trip Summary shows trip distance, Trip Time, EV Driving Ratio, Trip Average in MPG and odometer. Dashboard clocks appear in both layouts; photos also include other dashboard content such as ambient temperature, speed, gear and indicators. Inventory all visible fields and agree representation where needed; the seven originally named metrics must not become an exhaustive field list by assumption.

Displayed units include `mi`, `%` and `MPG`. Preserve these without inferring US versus imperial MPG or AM/PM. At evaluation time the user confirmed Trip Time is hours:minutes and requested numeric minutes. That output decision was later superseded on 2026-10-22: store trip duration as `hh:mm`. The sample observations are unchanged. Dashboard clock is a separate observation from metadata capture time. Different layout coverage and changing values between nearby photos reinforce per-field selection rather than choosing one whole photo.

Actual crops, recognition thresholds, clarity decisions and complete human-verified per-field expectations still require validation. A successful HEIC decode and human visual inspection do not establish Tesseract accuracy. No OCR engine, Linux container, network-blocked processing, file movement, JSON generation or performance benchmark was exercised.

## Later testing and retention

The planning evaluation used a temporary per-file hash/metadata manifest, JPEG previews and contact sheet under ignored planning state. These temporary tools/previews were removed after Planning PR #1 was verified merged. Later evaluation must regenerate disposable previews if needed. `sample-pictures/` is the durable local source input and must survive feature-state cleanup. Later tests must use disposable copies and verify original hashes; never point move tests at the originals.

A durable ignored inventory is saved at `sample-pictures/fixture-manifest.json`: relative original paths, SHA-256 values, byte sizes, observed dimensions/capture metadata and evaluation tool versions. Human field labels are marked pending; this inventory is not application trip JSON or certified OCR expectations. Preserve it and the originals through feature-state cleanup; save future validated labels alongside it. Do not make later tests depend on an absolute laptop path or retained planning-state folder. Public CI needs separately authorized publishable fixtures or another approved strategy; it cannot assume these ignored local files exist on a runner.

Coverage still needed includes labeled nonmatches, human clarity labels, deliberate absent/unclear values, missing/invalid timestamps, boundary/tie/chaining cases, cross-month groups, collisions, interruption/recovery, repeated runs and representative performance workloads. Additional fixtures and expected policies must be agreed rather than inferred from these 16 positive examples. See [testing plan](testing-plan.md).
