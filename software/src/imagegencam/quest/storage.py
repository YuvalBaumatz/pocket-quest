"""Independent simulator data; never rewrites ImageGenCam's existing queues."""

import json
import os
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image

from .filters import Style, apply_style


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".pending-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def encode(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@dataclass(frozen=True)
class Photo:
    id: str
    style: Style
    mission: int | None = None


class Store:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.warnings: list[str] = []

    def capture(self, source: Image.Image, style: Style, mission: int | None) -> Photo:
        photo = Photo(uuid4().hex, style, mission)
        directory = self.root / "photos" / photo.id
        atomic_write(directory / "original.png", encode(source))
        metadata = {"schema_version": 1, "style": style.value, "mission": mission}
        atomic_write(directory / "photo.json", json.dumps(metadata).encode())
        if style != Style.ORIGINAL and not style.is_ai:
            try:
                atomic_write(directory / "styled.png", encode(apply_style(source, style)))
            except (OSError, ValueError):
                self.warnings.append(f"Original saved without local filter: {photo.id}")
        return photo

    def photos(self) -> list[Photo]:
        photos: list[Photo] = []
        # A crash between saving an original and its metadata must not hide the photo.
        # Recovered originals never create an AI job or an automatic upload.
        for original in (self.root / "photos").glob("*/original.png"):
            metadata = original.parent / "photo.json"
            if not metadata.exists():
                try:
                    atomic_write(
                        metadata,
                        json.dumps(
                            {"schema_version": 1, "style": Style.ORIGINAL.value, "mission": None}
                        ).encode(),
                    )
                except OSError:
                    self.warnings.append(f"Original recovery pending: {original.parent.name}")
        paths = (self.root / "photos").glob("*/photo.json")
        for path in sorted(paths, key=lambda path: path.stat().st_mtime_ns):
            try:
                data = json.loads(path.read_text())
                if not isinstance(data, dict) or data.get("schema_version") != 1:
                    raise ValueError("Unknown photo schema")
                mission = data.get("mission")
                if mission is not None and (type(mission) is not int or not 0 <= mission < 3):
                    raise ValueError("Invalid mission")
                if not (path.parent / "original.png").is_file():
                    raise ValueError("Original unavailable")
                photos.append(Photo(path.parent.name, Style(data["style"]), mission))
            except (OSError, ValueError, KeyError, TypeError) as error:
                self.warnings.append(f"Cannot load photo {path.parent.name}: {error}")
        return photos

    def image(self, photo_id: str, original: bool = False) -> Image.Image:
        if len(photo_id) != 32 or any(c not in "0123456789abcdef" for c in photo_id):
            raise ValueError("Invalid photo ID")
        directory = self.root / "photos" / photo_id
        path = directory / "magic.png"
        if not path.exists():
            path = directory / "styled.png"
        if original or not path.exists():
            path = directory / "original.png"
        with Image.open(path) as image:
            return image.convert("RGB")

    def save_progress(self, memory: dict[str, object] | None, stamps: set[int]) -> None:
        value = {"schema_version": 1, "memory": memory, "stamps": sorted(stamps)}
        atomic_write(self.root / "state.json", json.dumps(value).encode())

    def load_progress(self) -> dict[str, object]:
        path = self.root / "state.json"
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text())
            if not isinstance(value, dict) or value.get("schema_version") != 1:
                raise ValueError("Unsupported save schema")
            stamps = value.get("stamps")
            if not isinstance(stamps, list) or any(
                type(x) is not int or not 0 <= x < 3 for x in stamps
            ):
                raise ValueError("Invalid stamps")
            return value
        except (OSError, ValueError) as error:
            # Preserve the unreadable state for inspection before allowing fresh saves.
            backup = self.root / f"state-unreadable-{uuid4().hex}.json"
            atomic_write(backup, path.read_bytes())
            self.warnings.append(f"Progress recovered to defaults: {error}")
            return {}
