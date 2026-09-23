import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from imagegencam.quest.device import FixtureCamera, fixture
from imagegencam.quest.filters import Style
from imagegencam.quest.input import Action
from imagegencam.quest.preferences import Preferences
from imagegencam.quest.runtime import Quest, Screen
from imagegencam.quest.storage import Store


def test_parent_preferences_outing_and_offline_survive_restart(tmp_path: Path) -> None:
    app = Quest(FixtureCamera(), Store(tmp_path), provider="none")
    app.handle(Action.UP, 0)
    assert app.screen == Screen.PARENT
    app.handle(Action.CONFIRM, 1)
    assert app.generation.offline
    app.set_outing([3, 7, 11])
    app.screen = Screen.EXPLORE
    app.handle(Action.RIGHT, 2)
    assert app.mission_index == 7
    app.handle(Action.RIGHT, 3)
    assert app.mission_index == 11
    app.handle(Action.RIGHT, 4)
    assert app.mission_index == 3
    app.close()
    restored = Quest(FixtureCamera(), Store(tmp_path), provider="none")
    assert restored.generation.offline
    assert restored.preferences.outing == [3, 7, 11]
    assert restored.mission_index == 3
    restored.home_index = 2
    restored.handle(Action.CONFIRM, 5)
    assert restored.screen == Screen.EXPLORE and restored.mission_index == 3
    restored.handle(Action.CONFIRM, 6)
    assert restored.screen == Screen.CAMERA and restored.active_mission == 3


def test_excluded_photo_removed_from_saved_games_but_kept_in_album(tmp_path: Path) -> None:
    store = Store(tmp_path)
    photo = store.capture(fixture(0), Style.ORIGINAL, None)
    app = Quest(FixtureCamera(), store, provider="none")
    app.screen = Screen.PLAY
    app.handle(Action.CONFIRM, 0)
    assert app.memory and photo.id in app.memory.deck
    app.set_eligible(photo.id, False)
    assert app.memory is None and app.screen == Screen.PLAY
    assert photo.id not in app.guess_choices()
    assert app.photos[0].id == photo.id
    app.handle(Action.CONFIRM, 1)
    assert app.memory and photo.id not in app.memory.deck
    app.close()
    restored = Quest(FixtureCamera(), store, provider="none")
    assert photo.id in restored.preferences.excluded_photos
    restored.set_eligible(photo.id, True)
    assert photo.id in restored.guess_choices()


@pytest.mark.parametrize("outing", [[0, 1, 2, 3], [0, 0], [-1], [12], [True]])
def test_invalid_outing_does_not_change_saved_choices(tmp_path: Path, outing: list[int]) -> None:
    app = Quest(FixtureCamera(), Store(tmp_path), provider="none")
    app.set_outing([2])
    with pytest.raises(ValueError):
        app.set_outing(outing)
    assert Preferences.load(tmp_path).outing == [2]


def test_parent_background_export_finishes_while_navigation_works(tmp_path: Path) -> None:
    root = tmp_path / "library"
    Store(root).capture(fixture(0), Style.ORIGINAL, None)
    app = Quest(FixtureCamera(), Store(root), provider="none")
    app.start_export()
    app.handle(Action.HOME, 0)
    deadline = time.monotonic() + 3
    while app.export_busy and time.monotonic() < deadline:
        app.tick(1)
        time.sleep(0.005)
    assert not app.export_busy
    assert app.screen == Screen.HOME
    assert app.export_path and app.export_path.is_file()


def test_low_storage_blocks_capture_before_writing_anything(tmp_path: Path) -> None:
    with patch(
        "imagegencam.quest.storage.shutil.disk_usage", return_value=SimpleNamespace(free=1024)
    ):
        with pytest.raises(OSError, match="Storage nearly full"):
            Store(tmp_path).capture(fixture(0), Style.ORIGINAL, None)
    assert not list(tmp_path.iterdir())


def test_failed_parent_save_does_not_change_live_permissions(tmp_path: Path) -> None:
    app = Quest(FixtureCamera(), Store(tmp_path), provider="none")
    with patch.object(Preferences, "save", side_effect=OSError("full")):
        with pytest.raises(OSError):
            app.set_offline(True)
    assert not app.preferences.offline and not app.generation.offline


def test_unreadable_preferences_pause_magic_and_require_photo_permission_review(
    tmp_path: Path,
) -> None:
    store = Store(tmp_path)
    photo = store.capture(fixture(0), Style.ORIGINAL, None)
    (tmp_path / "preferences.json").write_text("corrupt")
    app = Quest(FixtureCamera(), store, start_generation=False)
    assert app.generation.offline
    assert photo.id in app.preferences.excluded_photos
    assert photo.id not in app.guess_choices()
    assert (tmp_path / "preferences.json").read_text() == "corrupt"
