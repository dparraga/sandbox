# Local HEIC sample evaluation

The user authorizes the local `sample-pictures/` collection for evaluation and testing, not publication of photos, previews, metadata or labels. Originals and their durable inventory remain ignored. This document records useful fixture characteristics and limitations; it is not application-processing evidence.

## Evidence obtained

- 16 HEIC files, 18,288,191 bytes total. All decoded on Windows using temporary Python 3.14.4, Pillow 13.0.0 and pillow-heif 1.8.1 installed under ignored local state. These evaluation versions do not select the application's runtime/dependencies or approve wheel redistribution.
- Each decoded image reports 4032 × 3024 pixels and one frame through this adapter. Oriented previews were visually inspected. This does not prove orientation handling for other files or enumerate every auxiliary HEIF item.
- Visual inspection identifies eight Drive Info and eight Trip Summary photos. No labeled nonmatching examples are present. Framing, glare, reflections, dust and perspective vary.
- Every file exposes `DateTimeOriginal`, `SubsecTimeOriginal` and `OffsetTimeOriginal`; the observed offset is `-07:00`. Filename hour differs from local capture hour in this dataset, consistent with the offset. Filenames remain identifiers, not the authoritative timestamp. Do not generalize a filename-time rule or assign an offset to files that lack one.
- The approved [grouping contract](trip-grouping.md) assigns qualifying dashboard photos within the configured first-to-last window to the same trip. Layout qualification remains separate from grouping.
- SHA-256 values were recorded before/after reading and independently rechecked against the local manifest: all 16 original byte contents are unchanged. No original was moved or rewritten.

## Layout and design implications

For the requested readings, Drive Info provides trip distance and Trip Time; Trip Summary also provides Trip Average MPG and odometer. Extract only those four readings. Other content may serve as a necessary recognition anchor but must not become field observations or serialized output.

Requested reading units include `mi` and `MPG`; preserve literal units without inferring US versus imperial MPG. Trip Time means hours:minutes; approved storage is `hh:mm`. Trip date comes from original capture metadata, never the dashboard clock. Different layout coverage and changing values between nearby photos reinforce per-field selection rather than choosing one whole photo.

A bounded Windows engine probe used portable Tesseract 5.5.3.20260724, Leptonica 1.87.0 and the hash-pinned English model on eight manually selected title/requested-reading regions across two existing previews, one of each layout. All eight calls exited successfully and returned nonempty text. A worker visual comparison of the complete requested crop text, normalizing whitespace only, found 6 exact, 2 incorrect (one title anchor and one unit) and 0 uncertain results. This bounded comparison is not user-certified ground truth or an accuracy estimate for all 16 samples. Nonempty text does not establish correct readings, automatic recognition or accuracy. Complete human-verified clarity/value expectations and broader recognition validation remain pending. This probe does not establish actual Linux/Python 3.13 execution, OS-level network-blocked processing, file movement, JSON generation or representative performance. The portable extraction did not install the application OCR dependency or change system PATH/registry.

## Later testing and retention

Preserve original photos and the durable inventory through feature-state cleanup. Regenerate any needed previews from disposable copies. Never point move tests at originals.

A durable ignored inventory is saved at `sample-pictures/fixture-manifest.json`: relative original paths, SHA-256 values, byte sizes, observed dimensions/capture metadata and evaluation tool versions. Human field labels are marked pending; this inventory is not application trip JSON or certified OCR expectations. Preserve it and the originals through feature-state cleanup; save future validated labels alongside it. Do not make later tests depend on an absolute laptop path or retained planning-state folder. Public CI needs separately authorized publishable fixtures or another approved strategy; it cannot assume these ignored local files exist on a runner.

Validation starts with these 16 positive samples and must disclose that they do not establish nonmatch rejection or unseen-layout accuracy. Additional user uploads are not a prerequisite. Focus private labels on the four readings and necessary recognition anchors; exercise absent/unclear values, timestamp failures, boundary/tie/chaining cases, cross-month groups, collisions, interruption/recovery and repeated runs with existing samples or suitable synthetic fixtures. Representative performance remains unmeasured. See [testing plan](testing-plan.md).
