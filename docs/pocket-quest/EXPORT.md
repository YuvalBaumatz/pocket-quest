# Photo export and backup

From the Pocket Quest repository root:

```sh
bash software/scripts/run_quest.sh --export "$HOME/Downloads/pocket-quest-photos.zip"
```

This command exports the real library at `~/.pocket-quest` and exits. No API key,
camera, desktop window or internet access is needed. The app can remain open:
only originals/results present when the export scans the library are included.
Export again after any pending transformation completes, using a new filename.

To export explicit demo data, add `--demo`. To select another library, use
`--data-dir /absolute/path/to/library`. `--export` cannot run alongside credential
setup or screenshot generation.

## Archive contents

- `photos/<photo-id>/original.png`: exact saved original bytes.
- `photos/<photo-id>/styled.png`: local filter result, when present.
- `photos/<photo-id>/magic.png`: generated result, when present.
- `manifest.json`: schema version, export time, photo IDs, styles, mission IDs,
  relative file paths, byte sizes, and SHA-256 checksums.
- `README.txt`: how to open the archive and interpret these files.

Open the ZIP using Finder or another archive tool. Originals and versions remain
grouped under the same photo ID. No import UI is implemented: this is a portable
photo backup, not a full application-state restore.

Credentials, environment files, raw photo metadata, job database, game progress,
logs, and unrecognized files are excluded. Only selected metadata fields enter
the manifest. An orphan original without metadata is still included, with unknown
style/mission represented as null. Export never repairs or writes the library.

## Failure behavior

Existing destinations are never overwritten, including a name created by another
process during export. A completed ZIP is published atomically from a private
temporary file in the destination directory. Normal write failures remove that
temporary file; a hard process termination may leave `.quest-export-*` behind,
but never exposes a half-written ZIP at the requested destination.

Missing originals, corrupt image files, malformed metadata and symlinked photo
sources stop the export rather than silently producing an incomplete backup.
An empty or nonexistent library reports an error. The destination must be outside
the library. The output starts with owner-only permissions; copying/sharing it
using another application may change those permissions.

The ZIP uses stored PNG bytes without extra compression. This keeps export CPU and
memory use low, preserves every image byte, and allows streamed large files.
The destination filesystem must support hard links for atomic no-overwrite publish;
standard Mac local filesystems do. If exporting directly to a filesystem without
hard links fails, export locally and then copy the completed ZIP to that drive.

## Acceptance

`bash software/scripts/check_quest.sh` includes export roundtrip/checksum tests,
secret-exclusion tests, source immutability, failure cleanup, symlink rejection,
existing-destination/racing-destination protection, and a real launcher test.
Hands-on acceptance: export, extract through Finder, inspect originals and results,
and copy the completed archive to your chosen backup location. This remains pending
until recorded; automated tests do not prove an external backup exists.
