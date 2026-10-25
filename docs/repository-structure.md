# Solution design and repository structure

## Implemented design

The `flex_photo` package uses a standard-library Python CLI. `cli.py` owns argument parsing, console JSON and sanitized diagnostics; `discovery.py` owns filesystem traversal. `metadata.py` reads original-capture fields through pinned ExifRead; its [contract](capture-metadata.md) defines the library interface, parser guards and acceptance gates. The [discovery contract](heic-discovery.md) is authoritative for its interfaces, selection rules, failure semantics and limitations. `capture_time.py` converts those fields through the [capture-time contract](capture-time.md). Recognition/OCR, trip grouping, photo movement and monthly JSON are not implemented.

Packaging uses a `src/` layout and hash-pinned setuptools to build a wheel. A digest-pinned, multi-stage Linux container installs that wheel and runs as a nonroot user. SHA-pinned GitHub Actions run installed-package tests on Windows/Linux and restricted container smoke checks. See [setup](bootstrap.md), [test coverage](testing-plan.md), and [automation](github-test-automation.md).

## Repository map

| Location | Purpose / status |
| --- | --- |
| `README.md`, `CONTRIBUTING.md` | Purpose, current scope, setup and contribution navigation. |
| `AGENTS.md`, `CLAUDE.md`, `agents/` | Shared instructions and six role contracts; role files do not launch workers. |
| `.agents/skills/project-documentation/SKILL.md` | Repository-local documentation skill loaded before documentation edits and reviews. |
| `docs/` | Business/technical requirements, design, setup instructions, pipeline, testing, automation and persistent review guidance. |
| `pyproject.toml`, `requirements-build.txt`, `requirements-runtime.txt` | Package configuration and hash-pinned build/runtime dependencies. |
| `src/flex_photo/` | Candidate discovery, bounded capture-metadata reader, pure capture-time conversion, CLI, version and module entry point. |
| `tests/unit/` | CLI behavior, discovery traversal/error assertions, capture-metadata/parser-guard checks and capture-time validation. |
| `tests/integration/` | Installed wheel, module/console behavior and no output-file effects outside source root. |
| `tests/performance/` | Separate startup and synthetic discovery measurements; no photo workload. |
| `scripts/` | Repeatable tests, installed-wheel build and restricted-container helpers. |
| `container/Dockerfile`, `.dockerignore` | Multi-stage image, nonroot runtime and allowlisted build context. |
| `.github/workflows/` | Windows/Linux Python tests, reports and Linux container smoke checks. |
| `.github/pull_request_template.md` | Scope, approval, independent review and actual validation evidence. |
| `sample-pictures/` | Ignored local originals and `fixture-manifest.json`; excluded from CI, package and container. |
| `.agent-state/<feature>/` | Ignored laptop-local approval, status, reports, resume instructions and per-agent handoffs. |
| `.venv/`, `build/`, `dist/`, `reports/` | Ignored local environment, package outputs and sanitized validation reports. |

Future recognition/OCR, grouping/selection, move/JSON modules, models and publishable processing fixtures are deliberately absent. Native dependency artifacts and JSON schema require later validation/decisions. Keep generated data, downloaded assets and sensitive photos out of tracked history.

## Future processing design proposals

The implemented [capture metadata reader](capture-metadata.md) separates original-capture EXIF inspection from later timestamp interpretation and image operations. The implemented [capture-time converter](capture-time.md) uses the standard library without adding CLI or grouping behavior.

The following broader design remains proposed. It is not authorization to implement later processing or select native/model artifacts. Open business policies remain in [BRD](BRD.md).

## Stack proposal and alternatives

Propose a small CPU-only Python console application: Python (bootstrap supports 3.13 and 3.14; future native compatibility remains to be verified), Pillow for image preparation/metadata, a libheif-backed HEIC adapter, Tesseract 5 executable with local English `tessdata_fast`, and standard-library CLI/path/date/JSON utilities. Exact supported patches, versions and complete native package matrix must be verified before pinning. No database, service or generative model is needed.

| Area | Proposal | Alternative / tradeoff |
| --- | --- | --- |
| Runtime | Python, for simple image/batch orchestration | C#/.NET offers Windows packaging and cross-platform execution; native HEIC/OCR dependencies still require assessment. Python is selected for bootstrap; .NET is retained as the evaluated alternative. |
| Decode | Pillow plus pillow-heif/libheif behind an adapter | Decoder-only native build may reduce bundled encoders and licensing obligations but is not proven packaged on Windows. Stock wheels require artifact review below. |
| OCR | Tesseract TSV output, local English model | PaddleOCR only if sample evidence shows Tesseract inadequate; larger framework/model provisioning and license/offline audit. Do not ship both without evidence. |
| Container | Linux OCI image with pinned decoder/OCR/model assets | Podman is an open-source local candidate. Docker Desktop is optional and has usage-dependent terms. Native Windows tests remain necessary. |

Primary sources: [Python on Windows](https://docs.python.org/3.13/using/windows.html), [Python license](https://docs.python.org/3.13/license.html), [.NET introduction](https://learn.microsoft.com/en-us/dotnet/core/introduction), [Pillow](https://pillow.readthedocs.io/en/stable/about.html), [pillow-heif](https://github.com/bigcat88/pillow_heif), [installation](https://pillow-heif.readthedocs.io/en/latest/installation.html), [Tesseract installation](https://tesseract-ocr.github.io/tessdoc/Installation), [CLI/TSV](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html), [tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast), [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR), [local-model FAQ](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/FAQ.en.md), [Podman](https://podman.io/), [Docker Desktop terms](https://docs.docker.com/subscription-billing/desktop-license). These establish candidate capabilities, not suitability on the user's dashboards. Bootstrap pins are selected; pin future native/model artifacts only after their own validation.

## Proposed processing components and interfaces

Names below describe responsibilities, not finalized API signatures. Keep pure grouping/selection separate from decoding, OCR and filesystem effects.

1. `Scan(source) → candidate paths`: see the authoritative [HEIC discovery contract](heic-discovery.md). Source/destination overlap remains a later processing decision.
2. `ReadPhoto(path) → image + original metadata`: decode primary image and orient OCR pixels without changing the original. Validate EXIF/sub-IFD/offset/subsecond behavior with original HEIC samples. [Pillow tags](https://pillow.readthedocs.io/en/stable/_modules/PIL/ExifTags.html) include DateTimeOriginal and related offset/subsecond tags. The approved [capture-time converter](capture-time.md) uses only original-capture metadata and requires an explicit offset. Batch handling of missing/invalid values remains unresolved; never silently use file modification time or dashboard clock. With no user preference, propose leaving rejected-timestamp photos untouched and reporting them; this needs approval and does not waive eventual move/group requirements.
3. `Recognize(image) → layout/nonmatch/unresolved`: use title/labels and layout regions for Trip Summary and Drive Info. All matches qualify as Flex. Actual crops, preprocessing and recognition/readability criteria require representative samples.
4. `Extract(layout,image) → field observations`: retain raw text, parsed value/unit when clear, and per-field clarity (`clear`, `unclear`, `absent`), with internal OCR evidence. Confidence alone is not established clarity; do not infer unreadable digits from plausibility. Inventory every displayed field present in samples.
5. `Group(observations,window) → trips`: propose chronological earliest-unassigned anchoring. Apply the confirmed inclusive first-to-last bound in [BRD R07](BRD.md): admit a photo only while its capture time minus the first photo's time is less than or equal to the configured window. Reset anchor for the next group. Never chain consecutive gaps beyond the total bound. Timestamp ties remain unresolved; separate real trips within the window need user clarification.
6. `SelectFields(trip) → values/nulls`: for each field separately, traverse capture times newest first and choose the first clear observation. Newer absent/unclear values never erase earlier clear values; none clear gives JSON null. Equal-time conflicts need an approved tie policy.
7. `PlanOutput(trips) → output/move plan`: one entry per trip, one monthly file. Cross-month ownership/timezone and repeated-run identity/update policy must be decided; splitting a cross-month trip would violate one entry per trip.
8. `ApplyMovesAndWrite(plan)`: move only matching originals and write monthly JSON. User approves sequential collision suffix `-##`. Propose `-01` before extension, increment without overwrite, expanding beyond two digits; exact numbering, existing suffixes and races need confirmation. Propose verified cross-volume copy-before-delete and temporary JSON plus atomic replacement where supported; this does not make an entire run transactional. Move/write order, failures/recovery and repeat runs remain open.

Decode one image at a time and keep compact observations to limit memory; grouping may sort timestamp records. Record workload and resources before proposing performance limits. Pass filenames via argument arrays rather than shell interpolation. Address corrupt/oversized inputs, native decoder errors and safe disposable filesystem tests before implementation; do not assume an error-handling policy.

## Configuration and proposed data format

Propose source folder, matched-photo destination, JSON output folder (location pending), configurable trip window with explicit units/default 180 seconds, and local OCR/model paths. Support Windows spaces/Unicode and Linux mounted paths. Do not expose calibration settings until samples justify them.

Propose monthly `YYYY-MM.json` with `schema_version`, `month`, and `trips`. Candidate trip members: metadata-derived `first_capture_at`, `last_capture_at`; displayed slots `trip_distance`, `trip_duration`, `ev_driving_ratio`, `average_mpg`, `odometer`, `remaining_range`, `dashboard_clock`; additional displayed fields must be inventoried from samples. These names/envelope are unapproved. Never invent timezone offsets or use dashboard clock as capture time.

Propose measurement slots as `{value, unit}` or JSON null; duration as an `hh:mm` string or null; clock as displayed string or null. **Trip duration storage is approved as hours:minutes (`hh:mm`).** Capture timestamps retain their metadata date/time/offset separately. Schema member names/envelope and duration formats beyond the confirmed display remain proposals. Samples visibly show `mi`, `%` and `MPG`; preserve displayed units without assuming US/imperial MPG, ratio-to-fraction conversion or AM/PM. A wholly unreadable field is null, rather than an apparently populated measurement object. Provenance/photo references/trip IDs are optional proposals requiring justification, not new business requirements.

## Licensing, offline execution and cost gates

Existing Apache-2.0 LICENSE stays unchanged. Alternatives under evaluation are Apache-2.0 (permissive, express contributor patent grant, continuity), MIT (short permissive terms without Apache's express patent clause), and GPL-3.0 (copyleft distribution obligations if desired). No replacement license is selected. Confirm ownership/rights before any change. Sources: [Apache text](https://www.apache.org/licenses/LICENSE-2.0), [MIT text](https://choosealicense.com/licenses/mit/), [GPL-3.0 text](https://choosealicense.com/licenses/gpl-3.0/). Choice of project license does not override dependency licenses or establish codec patent clearance.

| Candidate | License evidence / required audit |
| --- | --- |
| CPython | PSF/historical notices; retain applicable notices. |
| Pillow | HPND/PIL-style terms; inspect bundled native libraries too. |
| pillow-heif | Source BSD-3-Clause; upstream [bundled notices](https://github.com/bigcat88/pillow_heif/blob/master/LICENSES_bundled.txt) label binary wheels GPLv2 due to x265 and list LGPLv3 native components. Do not treat source-package license as full wheel license. |
| Native HEIC | Inspect exact [libheif](https://github.com/strukturag/libheif/blob/master/COPYING), [libde265](https://www.libde265.org/faq/) and codec build configuration, notices and corresponding-source obligations. Decoder-only Windows/Linux packaging remains a feasibility gate. |
| Tesseract / tessdata_fast | Apache-2.0 engine/model; also inventory native transitive libraries and retain notices/model hashes. |
| PaddleOCR alternative | Repository Apache-2.0 does not settle each chosen model/framework/binary's terms. |

For Windows pillow-heif artifacts, inventory bundled MinGW runtimes explicitly: upstream bundled notices identify libgcc/libstdc++ as GPL-3.0-with-GCC-exception and libwinpthread as MIT/BSD. Preserve exception qualifiers and verify license texts against the exact selected release artifacts.

Before approving distribution, inventory exact direct/transitive/native artifacts and models, independently assess license compatibility/obligations and any applicable codec distribution questions. GPLv2-only versus “or later” matters; changing project license is not an implicit fix. No proprietary or paid processing dependency is proposed.

Provision/download binaries and models separately from execution. Processing must load local assets, make no external calls and fail clearly if required assets are absent; verify the full path with network blocked. No external API/inference fees are proposed. Laptop compute/storage, development time and GitHub runner/artifact usage still have costs/allowances; do not promise unlimited free hosting. Docker Desktop is optional, not universally free/open source.
