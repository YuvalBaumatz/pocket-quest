import hashlib
import json
import os
import stat
import subprocess
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

import pytest
from PIL import Image

from imagegencam.quest.__main__ import main, parse_options
from imagegencam.quest.device import fixture
from imagegencam.quest.export import export_photos
from imagegencam.quest.filters import Style
from imagegencam.quest.storage import Store, encode


def snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_archive_roundtrip_preserves_images_and_excludes_secrets(tmp_path: Path) -> None:
    root = tmp_path / "library"
    store = Store(root)
    local = store.capture(fixture(0), Style.PIXELS, 1)
    magic = store.capture(fixture(1), Style.CLAY, None)
    (root / "photos" / magic.id / "magic.png").write_bytes(encode(fixture(2)))
    for name in (".env", "generation.sqlite3", "state.json", "debug.log"):
        (root / name).write_text("DO-NOT-EXPORT-SECRET")
    metadata = root / "photos" / local.id / "photo.json"
    data = json.loads(metadata.read_text())
    data["api_key"] = "DO-NOT-EXPORT-SECRET"
    metadata.write_text(json.dumps(data))
    (metadata.parent / "private.txt").write_text("DO-NOT-EXPORT-SECRET")
    before = snapshot(root)
    destination = tmp_path / "backup.zip"
    assert export_photos(root, destination) == 2
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert snapshot(root) == before
    with ZipFile(destination) as archive:
        assert archive.testzip() is None
        manifest = json.loads(archive.read("manifest.json"))
        members = {"manifest.json", "README.txt"}
        assert len(manifest["photos"]) == 2
        for photo in manifest["photos"]:
            for item in photo["files"]:
                members.add(item["path"])
                contents = archive.read(item["path"])
                assert contents == (root / item["path"]).read_bytes()
                assert len(contents) == item["bytes"]
                assert hashlib.sha256(contents).hexdigest() == item["sha256"]
                with Image.open(BytesIO(contents)) as image:
                    image.load()
        assert set(archive.namelist()) == members
        assert all(b"DO-NOT-EXPORT-SECRET" not in archive.read(name) for name in members)


def test_orphan_original_is_exported_without_modifying_library(tmp_path: Path) -> None:
    root = tmp_path / "library"
    photo = Store(root).capture(fixture(0), Style.ORIGINAL, None)
    (root / "photos" / photo.id / "photo.json").unlink()
    before = snapshot(root)
    destination = tmp_path / "backup.zip"
    export_photos(root, destination)
    with ZipFile(destination) as archive:
        photo_entry = json.loads(archive.read("manifest.json"))["photos"][0]
        assert photo_entry["style"] is None
        assert len(photo_entry["files"]) == 1
    assert snapshot(root) == before


@pytest.mark.parametrize("stage", ["copy", "publish"])
def test_failed_export_cleans_partial_output_and_preserves_library(
    tmp_path: Path, stage: str
) -> None:
    root = tmp_path / "library"
    Store(root).capture(fixture(0), Style.ORIGINAL, None)
    before = snapshot(root)
    destination = tmp_path / "backup.zip"
    target = "zipfile.ZipFile.open" if stage == "copy" else "os.link"
    with patch(target, side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            export_photos(root, destination)
    assert not destination.exists()
    assert not list(tmp_path.glob(".quest-export-*"))
    assert snapshot(root) == before


def test_existing_backup_and_library_paths_are_never_overwritten(tmp_path: Path) -> None:
    root = tmp_path / "library"
    Store(root).capture(fixture(0), Style.ORIGINAL, None)
    destination = tmp_path / "backup.zip"
    destination.write_bytes(b"existing-backup")
    with pytest.raises(ValueError, match="already exists"):
        export_photos(root, destination)
    assert destination.read_bytes() == b"existing-backup"
    with pytest.raises(ValueError, match="outside"):
        export_photos(root, root / "backup.zip")


@pytest.mark.parametrize(
    "target", ["original.png", "styled.png", "photo.json", "directory", "photos"]
)
def test_symlinked_sources_are_rejected(tmp_path: Path, target: str) -> None:
    root = tmp_path / "library"
    photo = Store(root).capture(fixture(0), Style.PIXELS, None)
    directory = root / "photos" / photo.id
    source = (
        root / "photos"
        if target == "photos"
        else directory
        if target == "directory"
        else directory / target
    )
    moved = tmp_path / "outside"
    source.rename(moved)
    source.symlink_to(moved, target_is_directory=moved.is_dir())
    with pytest.raises((ValueError, OSError)):
        export_photos(root, tmp_path / "backup.zip")
    assert not (tmp_path / "backup.zip").exists()


@pytest.mark.parametrize("failure", ["missing", "corrupt", "metadata"])
def test_incomplete_library_fails_without_publishing_partial_backup(
    tmp_path: Path, failure: str
) -> None:
    root = tmp_path / "library"
    photo = Store(root).capture(fixture(0), Style.PIXELS, None)
    directory = root / "photos" / photo.id
    if failure == "missing":
        (directory / "original.png").unlink()
    elif failure == "corrupt":
        (directory / "styled.png").write_bytes(b"invalid image")
    else:
        (directory / "photo.json").write_text("not-json")
    before = snapshot(root)
    with pytest.raises((ValueError, OSError)):
        export_photos(root, tmp_path / "backup.zip")
    assert snapshot(root) == before
    assert not (tmp_path / "backup.zip").exists()
    assert not list(tmp_path.glob(".quest-export-*"))


def test_export_launcher_needs_no_key_camera_or_display(tmp_path: Path) -> None:
    root = tmp_path / "library"
    Store(root).capture(fixture(0), Style.ORIGINAL, None)
    environment = dict(os.environ)
    environment.pop("GEMINI_API_KEY", None)
    environment.pop("OPENAI_API_KEY", None)
    destination = tmp_path / "backup.zip"
    launcher = Path(__file__).resolve().parents[2] / "scripts" / "run_quest.sh"
    result = subprocess.run(
        ["bash", str(launcher), "--data-dir", str(root), "--export", str(destination)],
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "Exported 1 photos" in result.stdout
    assert destination.exists()


def test_empty_library_has_no_misleading_success_archive(tmp_path: Path) -> None:
    root = tmp_path / "library"
    (root / "photos").mkdir(parents=True)
    with pytest.raises(ValueError, match="No photos"):
        export_photos(root, tmp_path / "backup.zip")
    assert not (tmp_path / "backup.zip").exists()


def test_export_exits_before_credentials_or_camera_setup(tmp_path: Path) -> None:
    root = tmp_path / "library"
    Store(root).capture(fixture(0), Style.ORIGINAL, None)
    args = parse_options(["--data-dir", str(root), "--export", str(tmp_path / "backup.zip")])
    with (
        patch("imagegencam.quest.__main__.parse_options", return_value=args),
        patch("imagegencam.quest.__main__.load_credentials") as credentials,
        patch("imagegencam.quest.__main__.Quest") as app,
    ):
        main()
    credentials.assert_not_called()
    app.assert_not_called()


def test_destination_created_during_export_is_not_overwritten(tmp_path: Path) -> None:
    root = tmp_path / "library"
    Store(root).capture(fixture(0), Style.ORIGINAL, None)
    destination = tmp_path / "backup.zip"
    link = os.link

    def race(source: Path, target: Path) -> None:
        target.write_bytes(b"another-backup")
        link(source, target)

    with patch("os.link", side_effect=race):
        with pytest.raises(FileExistsError):
            export_photos(root, destination)
    assert destination.read_bytes() == b"another-backup"
    assert not list(tmp_path.glob(".quest-export-*"))
