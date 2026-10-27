# Local HEIC sample evaluation

The user authorizes the local `sample-pictures/` collection for evaluation and testing, not publication of photos, previews, metadata or labels. Originals and their durable inventory remain ignored. This document records useful fixture characteristics and limitations; it is not application-processing evidence.

## Evidence obtained

- 16 HEIC files, 18,288,191 bytes total. All decoded on Windows using temporary Python 3.14.4, Pillow 13.0.0 and pillow-heif 1.8.1 installed under ignored local state. The selected artifact versions passed a separate scoped implementation-entry review; this sample decode alone does not establish application acceptance or binary-redistribution clearance.
- Each decoded image reports 4032 × 3024 pixels and one frame through this adapter. Oriented previews were visually inspected. This does not prove orientation handling for other files or enumerate every auxiliary HEIF item.
- Visual inspection identifies eight Drive Info and eight Trip Summary photos. No labeled nonmatching examples are present. Framing, glare, reflections, dust and perspective vary.
- Every file exposes `DateTimeOriginal`, `SubsecTimeOriginal` and `OffsetTimeOriginal`; the observed offset is `-07:00`. Filename hour differs from local capture hour in this dataset, consistent with the offset. Filenames remain identifiers, not the authoritative timestamp. Do not generalize a filename-time rule or assign an offset to files that lack one.
- The approved [grouping contract](trip-grouping.md) assigns qualifying dashboard photos within the configured first-to-last window to the same trip. Layout qualification remains separate from grouping.
- SHA-256 values were recorded before/after reading and independently rechecked against the local manifest: all 16 original byte contents are unchanged. No original was moved or rewritten.

## Layout and design implications

For the requested readings, Drive Info provides trip distance and Trip Time; Trip Summary also provides Trip Average MPG and odometer. Extract only those four readings. Other content may serve as a necessary recognition anchor but must not become field observations or serialized output.

Requested reading units include `mi` and `MPG`; preserve literal units without inferring US versus imperial MPG. Trip Time means hours:minutes; approved storage is `hh:mm`. Trip date comes from original capture metadata, never the dashboard clock. Different layout coverage and changing values between nearby photos reinforce per-field selection rather than choosing one whole photo.

Worker-human expectations now cover all 16 previews: 48 clear requested-reading observations, 16 absent readings and 16 layout title anchors. Values, literal units, statuses and manual region coordinates remain private. No requested value was unresolved in that visual pass, but these labels are not user-certified. Labels and ROIs are acceptance evidence only: runtime recognition must not read them or identify photos by fixture name/hash.

A Windows Tesseract 5.5.3.20260724/Leptonica 1.87.0 probe with the pinned English model returned nonempty text for eight manually selected regions across two previews. Full-region worker comparison, normalizing whitespace only, found six exact results and two errors (one title and one unit). For those same two error regions at native resolution, RGB yielded one exact result; grayscale with 2x scaling yielded two exact results. No token replacement was applied. These bounded observations support further evaluation, not an adopted readability threshold, automatic recognition or an accuracy estimate for the collection.

Separate public candidate checks exercise exact Windows/Linux CPython 3.13/3.14 artifacts, synthetic HEVC decode and selected OCR execution under the [testing plan](testing-plan.md). Neither those synthetic checks nor private crop probes establish the complete application path, real nonmatch rejection, file movement, monthly output or representative performance. Original/copy/manifest hashes remained unchanged through private labeling and native crop evaluation.

## Later testing and retention

Preserve original photos and the durable inventory through feature-state cleanup. Regenerate any needed previews from disposable copies. Never point move tests at originals.

A durable ignored inventory is saved at `sample-pictures/fixture-manifest.json`: relative original paths, SHA-256 values, byte sizes, observed dimensions/capture metadata and evaluation tool versions. The original inventory is not application trip JSON or certified OCR expectations; focused worker labels are retained separately under ignored feature state for acceptance evaluation. Preserve it and the originals through feature-state cleanup; retain focused labels in a durable ignored location before cleaning their feature state. Do not make later tests depend on an absolute laptop path or retained planning-state folder. Public CI needs separately authorized publishable fixtures or another approved strategy; it cannot assume these ignored local files exist on a runner.

Validation starts with these 16 positive samples and must disclose that they do not establish nonmatch rejection or unseen-layout accuracy. Additional user uploads are not a prerequisite. Focus private labels on the four readings and necessary recognition anchors; exercise absent/unclear values, timestamp failures, boundary/tie/chaining cases, cross-month groups, collisions, interruption/recovery and repeated runs with existing samples or suitable synthetic fixtures. Representative performance remains unmeasured. See [testing plan](testing-plan.md).
