# Capture metadata

**Approved and implemented.** This is the authoritative contract for the internal metadata-reading component supporting BRD R05/R14 and TRD T05. The CLI provides bootstrap and [HEIC discovery](heic-discovery.md); metadata extraction is a library interface only.

Capture metadata is needed before later trip timing. Read the original-capture EXIF fields observed in supplied samples without introducing image decoding, timestamp selection or an interim CLI command.

## Scope and acceptance criteria

1. Add an internal library function `read_capture_metadata(path: Path) -> CaptureMetadata`. Its caller supplies one discovery candidate; discovery and existing CLI behavior remain unchanged. Read one file at a time, close it reliably and preserve original bytes/names. Reject a selected symlink/reparse point or nonregular file, recheck before opening and verify the opened descriptor is regular. Detected disappearance or replacement fails. Stable local trees remain the operating assumption; no atomic-snapshot or hostile-tree confinement guarantee is made.
2. Return immutable `CaptureMetadata` with exactly three optional strings: `date_time_original` from `EXIF DateTimeOriginal`, `offset_time_original` from `EXIF OffsetTimeOriginal`, and `subsec_time_original` from `EXIF SubSecTimeOriginal`. Use complete decoded `tag.values`, not shortened printable displays. Retain decoded text without application trimming, date validation, conversion, offset inference or fallback selection. This is not byte-exact metadata preservation.
3. Return Python `None` when a target is not extractable, including absent, unsupported or some damaged metadata: the backend can return no tags for these cases. Do not certify file validity or distinguish every corrupt file from one without EXIF. Raised parser errors, nontext target values, I/O failures and parser-limit failures raise `MetadataError`; an empty parser result must not hide a sticky guard failure.
4. `MetadataError` retains internal path/cause and one safe reason: `file unavailable`, `metadata parsing failed`, `metadata limit exceeded`, or `timestamp tag is not text`. Its string contains no metadata, private paths or raw backend/OS text. The component prints nothing. Suppress only the dedicated ExifRead logger during sequential parsing and restore its prior disabled flag in `finally`; leave root/unrelated loggers unchanged. Concurrent use with other ExifRead callers is not guaranteed.
5. Bound parser stream access per file: at most 1 MiB per requested read, 64 MiB cumulative returned bytes and 100,000 combined read/seek/tell operations. Reject negative/unbounded reads and seeks outside the opened file's initial size before the underlying operation. Preserve a sticky limit failure even if the parser catches its exception. These engineering guards may reject unusual legitimate metadata; they are not measured workload limits or a hard CPU/memory sandbox.
6. No new CLI command, batch orchestration, console inventory schema, arbitrary EXIF output, GPS/camera identifiers, application writes, decoding, recognition, OCR, movement, grouping, duration conversion, monthly JSON or processing network calls. OS-managed access-time effects remain possible. Private metadata stays out of CI artifacts.

The three-field restriction applies only to capture metadata. The requirement to extract all available dashboard fields remains unchanged. This reader returns extraction evidence without selecting a timestamp. The approved [capture-time converter](capture-time.md) defines original-only validation; other date fields, fallback selection, batch handling of missing/invalid values, timezone normalization and ties remain outside this reader. BRD R07's confirmed inclusive first-to-last window, default three minutes, and `hh:mm` duration storage remain unchanged.

## Design and dependency

Use `src/flex_photo/metadata.py` and `ExifRead==3.5.1`, without a custom HEIF parser. ExifRead is pure Python, has no runtime dependencies and uses BSD-3-Clause licensing. Pin its exact wheel and SHA-256 and retain its notice/license in distributed artifacts; preserve the repository's Apache-2.0 license. No native codec, OCR engine or model is introduced. Upstream lists support through Python 3.13; project Python 3.14 compatibility requires validation.

Call `process_file` with `details=False`, `extract_thumbnail=False`, `debug=False`, `strict=True` and `truncate_tags=False`. Strict mode can still return no tags for invalid EXIF. Keep backend details behind the one function and immutable result; no provider framework, optional backend or general metadata API is needed.

A [reported HEIC allocation issue](https://github.com/ianare/exif-py/issues/249) and tagged-source read/seek behavior justify the bounded stream. An uncovered no-I/O loop or ineffective guard requires revised review rather than removing limits or claiming hostile-input safety. ExifTool would add executable/Perl provisioning; Pillow/pillow-heif would add native codec packaging. Subprocess timeouts alone do not contain the known allocation risk. These alternatives are not approved fallbacks.

Runtime provisioning, package/container installation and allowlists must support this component and pinned dependency. Reuse existing CLI checks, native CI jobs, container helper and test framework. Provision dependencies before execution; installed extraction must work with network access blocked.

Costs are local reads, parser work and existing CI/storage use, with no API/model fees. Sequential parsing needs no new worker pool. Guards do not imply universal HEIC coverage or a speed/memory guarantee.

## Validation requirements

- Verify the installed library on Windows/Linux Python 3.13/3.14 outside the checkout: exact original-date/offset/subsecond extraction, missing targets, invalid date text retained and nontext errors. Preserve installed CLI/discovery checks.
- Use generated metadata-only fixtures for corrupt/truncated HEIF, huge reads, nonprogressing traversal, cyclic IFDs, sticky failures, I/O/close errors and detected link/reparse replacement. These fixtures do not prove image decodability. Distinguish real OS evidence from mocks/skips.
- Compare disposable copies of all 16 private samples against the durable manifest's existing original-capture evidence. Preserve hashes/names and exclude raw metadata from public tests/reports. Investigate backend failure instead of silently changing dependencies.
- Exercise installed-library extraction in an actual network-disabled, read-only, nonroot container. Verify final rebuilt/reinstalled wheel/image contents and dependency/license, excluding private data and temporary state.
- Use focused parser/guard cost evidence where needed, with existing automation or an ignored manual measurement. Label workload, environment, repetitions, cache and overhead; introduce no benchmark infrastructure or threshold. Defer batch-throughput measurements until a batch workflow exists, and make no decode/OCR or unmeasured memory claim.

Approval covers this three-field library scope, not-extractable ambiguity, raised-error policy, ExifRead version/validation gates and fixed parser guards. A failed compatibility, sample or security gate requires investigation; a material solution change needs user approval. Independent final review is required before a PR. Actual results and outstanding validation belong in the PR and ignored feature state.

Primary sources: [ExifRead 3.5.1](https://pypi.org/project/ExifRead/3.5.1/), [BSD-3-Clause license](https://github.com/ianare/exif-py/blob/3.5.1/LICENSE), [tagged API](https://github.com/ianare/exif-py/blob/3.5.1/exifread/__init__.py) and [HEIC reader](https://github.com/ianare/exif-py/blob/3.5.1/exifread/core/heic.py). These establish dependency capabilities and limitations, not project validation results.
