"""Photo-only, read-only library export. Credentials and runtime state are excluded."""

import hashlib
import json
import os
import re
import stat
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from PIL import Image

from .filters import Style


def export_photos(root: Path, destination: Path) -> int:
    """Publish a complete ZIP without overwriting any existing destination."""
    root = root.expanduser().resolve()
    destination = destination.expanduser().absolute()
    if destination.resolve().is_relative_to(root):
        raise ValueError("Choose an export destination outside the photo library.")
    if destination.exists() or destination.is_symlink():
        raise ValueError("That destination already exists. Choose a new ZIP filename.")
    photos = root / "photos"
    if photos.is_symlink() or not photos.is_dir():
        raise ValueError("The photo library is missing or its photos directory is a symlink.")
    # Snapshot filenames first. A result produced later belongs in the next export.
    entries: list[tuple[Path, list[Path]]] = []
    for directory in sorted(photos.iterdir()):
        if not re.fullmatch(r"[0-9a-f]{32}", directory.name):
            continue
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("The photo library contains an unsafe photo directory.")
        original = directory / "original.png"
        if not original.exists():
            raise ValueError(f"Photo {directory.name} is missing its original.")
        files = [original]
        for name in ("styled.png", "magic.png"):
            path = directory / name
            if path.exists() or path.is_symlink():
                files.append(path)
        entries.append((directory, files))
    if not entries:
        raise ValueError("No photos to export yet.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=".quest-export-", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w+b") as output:
            manifest_photos: list[dict[str, object]] = []
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
                for directory, files in entries:
                    style: str | None = None
                    mission: int | None = None
                    metadata = directory / "photo.json"
                    if metadata.exists() or metadata.is_symlink():
                        with _open_regular(metadata) as stream:
                            data = json.load(stream)
                        if not isinstance(data, dict) or data.get("schema_version") != 1:
                            raise ValueError(f"Photo {directory.name} has invalid metadata.")
                        raw_style = data.get("style")
                        if not isinstance(raw_style, str) or raw_style not in {
                            s.value for s in Style
                        }:
                            raise ValueError(f"Photo {directory.name} has an invalid style.")
                        style = raw_style
                        mission = data.get("mission")
                        if mission is not None and (type(mission) is not int or mission < 0):
                            raise ValueError(f"Photo {directory.name} has an invalid mission.")
                    exported: list[dict[str, object]] = []
                    for path in files:
                        name = f"photos/{directory.name}/{path.name}"
                        digest = hashlib.sha256()
                        size = 0
                        with _open_regular(path) as source:
                            with Image.open(source) as picture:
                                if picture.format != "PNG":
                                    raise ValueError(f"Photo {directory.name} is not a PNG image.")
                                picture.verify()
                            source.seek(0)
                            with archive.open(name, "w", force_zip64=True) as target:
                                while chunk := source.read(1024 * 1024):
                                    target.write(chunk)
                                    digest.update(chunk)
                                    size += len(chunk)
                        exported.append({"path": name, "bytes": size, "sha256": digest.hexdigest()})
                    manifest_photos.append(
                        {
                            "id": directory.name,
                            "style": style,
                            "mission": mission,
                            "files": exported,
                        }
                    )
                archive.writestr(
                    "manifest.json",
                    json.dumps(
                        {
                            "schema_version": 1,
                            "created_at": datetime.now(UTC).isoformat(),
                            "photos": manifest_photos,
                        },
                        indent=2,
                    ),
                )
                archive.writestr(
                    "README.txt",
                    "Pocket Quest photo backup\n\n"
                    "original.png: untouched saved original\n"
                    "styled.png: local filtered version, when present\n"
                    "magic.png: generated version, when present\n"
                    "manifest.json: photo IDs, styles, missions, file sizes and SHA-256 checksums\n\n"
                    "Extract this ZIP with a standard archive tool to view or copy your photos.\n"
                    "Only files present when export began are included. Export again for new results.\n"
                    "This is a photo backup, not an application restore: game progress, request\n"
                    "queues, credentials and settings are deliberately excluded.\n",
                )
            output.flush()
            os.fsync(output.fileno())
        # Same-filesystem hard link publishes atomically and refuses an existing name.
        os.link(temporary, destination)
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)
    return len(entries)


def _open_regular(path: Path) -> BinaryIO:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise ValueError("Photo export refuses symlinks and non-regular files.")
    return os.fdopen(fd, "rb")
