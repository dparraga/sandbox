# HEIC discovery

Approved and implemented read-only candidate discovery for BRD R02. This is the authoritative feature contract. Discovery provides paths for later decoding without imaging dependencies; it does not validate images or identify Flex photos. Verification evidence and outstanding checks belong in the feature PR and ignored local state.

## Scope and acceptance criteria

The user confirmed source folders are local and outside OneDrive. This is the usage context, not a new programmatic location/provider check. Cloud folders are outside the supported input context. The approval covers these discovery policies:

1. Add `flex-photo discover SOURCE` and equivalent `python -m flex_photo discover SOURCE`. Require an explicit directory; preserve readiness/help/version. No destination or configuration file is added.
2. Recursively enumerate ordinary directories, including hidden names. Include regular files with a case-insensitive final `.heic` suffix; preserve their spelling. Exclude `.heif`, `.heic.bak`, directories and special files. Hardlinked names remain distinct. Do not open contents: empty/corrupt `.heic` files are candidates, not validated images or Flex matches.
3. Reject a selected root that is a symlink or Windows reparse point; skip such entries below it. In practice, a junction's entire subtree and reparse-marked files are omitted. This blanket rule can omit cloud-managed photos even when locally available; cloud folders are outside this feature's intended input. Linked ancestors are allowed. Non-reparse mount points are traversed; Windows mounted-folder reparse points are skipped. Validate the absolute lexical root before resolving links. Use a stable tree; traversal is neither an atomic snapshot nor hostile-tree confinement.
4. Print one JSON array of root-relative strings using `/`, original case, exact string/code-point sort order, ASCII escaping and a final newline. Empty success prints `[]`; success exits 0 with empty stderr. Example: `["day 1/IMG_001.HEIC", "trip.heic"]`. This is console inventory, not an output file or monthly trip JSON.
5. Invalid/linked roots, scan/metadata failures and detected disappearance exit 1 with no partial stdout. If a queued ordinary directory is detected becoming a link/reparse point/non-directory, fail rather than skip it. Emit a concise, single-line category/reason without traceback or raw OS text: omit source/absolute paths for root errors; below-root errors may include JSON-escaped relative paths. Argument misuse exits 2; handle output failures cleanly.
6. No application writes, moves, content reads, metadata extraction, decoding, OCR, grouping, duration conversion, monthly JSON or network calls. Preserve source bytes/names; OS-managed access-time effects are possible.

## Usage

After rebuilding and reinstalling the wheel using [setup instructions](bootstrap.md), use an ordinary local source folder outside OneDrive:

```powershell
.\.venv\Scripts\flex-photo.exe discover "C:\Photos"
.\.venv\Scripts\python.exe -m flex_photo discover "C:\Photos"
```

Schematic output for a folder containing two candidate filenames:

```json
["day 1/IMG_001.HEIC", "trip.heic"]
```

This example is not an actual sample scan or trip result. The command writes inventory to stdout; it creates no output file. Use [bootstrap instructions](bootstrap.md) for installation and the shared test runner.

## Design and interface

Use standard-library `os.scandir`, `stat` and `Path`: iterative traversal, closed directory handles, no-follow metadata checks, Windows reparse attributes and wrapped `OSError`, including iterator failures. Collect and sort before printing. No new dependency, service or worker pool.

Library interface: `discover_heic(source: Path) -> tuple[Path, ...]`, returning sorted relative paths. `DiscoveryError` carries category (`invalid-source` or `scan-failed`), internal path, sanitized reason and optional cause. The library performs no printing; CLI handles arguments, JSON and diagnostics.

## Checks and limits

- Unit: nested/empty/hidden/mixed suffixes, ordering/case, spaces/Unicode/control characters, hardlinks/special files, invalid roots, links/junctions/reparse entries, and injected metadata/enumeration/disappearance failures. Distinguish real OS evidence from mocks/skips.
- Installed integration: console/module outside checkout; exact inventory and exit/diagnostic behavior, no partial output/content reads/writes, bootstrap regressions and final wheel contents. Windows/Linux Python 3.13/3.14 plus actual network-disabled, read-only, nonroot container execution.
- Local samples: verify durable manifest and hashes; scan disposable copies of the 16 originals. Keep originals/private paths outside CI, artifacts, package, image and history. This supplies no OCR or dashboard-reading evidence.
- Performance: separately measure repeated discovery on a validated synthetic tree, excluding construction time. Record tree size/depth, environment, repetitions and cache conditions. Existing startup measurements remain startup-only. Discovery timing includes installed-process spawn, traversal and JSON serialization on a synthetic tree; there is no speed threshold or photo-processing measurement.

Expected time is O(E + C log C) for entries E and candidates C, plus filesystem costs; memory holds candidates and queued directories. Very large/deep or changing trees remain limitations. Costs are local I/O/memory/test storage and existing CI usage; no API/model fee or new licensing dependency is introduced. Future trip policies and licensing decisions remain deferred.

See [review guidance](review-guidance.md) for package, container-context and Windows instruction checks. API basis: [scandir](https://docs.python.org/3.13/library/os.html#os.scandir) and [Windows reparse attributes](https://docs.python.org/3.13/library/stat.html#stat.FILE_ATTRIBUTE_REPARSE_POINT).
