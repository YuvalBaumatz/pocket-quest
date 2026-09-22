from pathlib import Path
from random import Random
from unittest.mock import patch

import pytest

from imagegencam.quest.device import FixtureCamera, fixture
from imagegencam.quest.filters import Style, apply_style
from imagegencam.quest.input import Action, InputMapper
from imagegencam.quest.memory import MemoryGame
from imagegencam.quest.render import render
from imagegencam.quest.runtime import Quest, Screen
from imagegencam.quest.storage import Store, atomic_write


def test_input_hold_does_not_capture_twice_or_go_back_after_home() -> None:
    mapper = InputMapper()
    assert mapper.press(Action.CONFIRM, 0) == [Action.CONFIRM]
    assert mapper.press(Action.CONFIRM, 0.1) == []
    assert mapper.tick(1) == []
    mapper.release(Action.CONFIRM, 1)
    assert mapper.press(Action.BACK, 2) == []
    assert mapper.tick(2.9) == [Action.HOME]
    assert mapper.release(Action.BACK, 3) == []
    mapper.press(Action.BACK, 4)
    assert mapper.release(Action.BACK, 4.2) == [Action.BACK]


def test_direction_repeat_and_focus_reset() -> None:
    mapper = InputMapper()
    mapper.press(Action.RIGHT, 0)
    assert mapper.tick(0.3) == []
    assert mapper.tick(0.4) == [Action.RIGHT]
    assert mapper.tick(0.45) == []
    mapper.clear()
    assert mapper.tick(10) == []


@pytest.mark.parametrize("count", range(4))
def test_memory_fills_missing_photos_with_distinct_pairs(count: int) -> None:
    game = MemoryGame.create([str(i) for i in range(count)], Random(0))
    assert len(game.deck) == 6
    assert len(set(game.deck)) == 3
    assert all(game.deck.count(card) == 2 for card in game.deck)


def test_memory_mismatch_delay_match_and_restart() -> None:
    game = MemoryGame(["a", "b", "c", "a", "b", "c"])
    game.handle(Action.CONFIRM, 0)
    game.handle(Action.CONFIRM, 0.1)  # Re-selecting does not create a pair.
    assert game.exposed == [0]
    game.handle(Action.RIGHT, 0.2)
    game.handle(Action.CONFIRM, 0.3)
    game.handle(Action.RIGHT, 0.4)
    game.handle(Action.CONFIRM, 0.5)
    assert game.exposed == [0, 1]
    game.tick(1.31)
    assert game.exposed == []
    for index in (0, 3):
        game.cursor = index
        game.handle(Action.CONFIRM, 2)
    restored = MemoryGame.restore(game.snapshot())
    assert restored.matched == {0, 3}
    assert restored.exposed == []
    assert restored.hide_at is None


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        {"deck": ["a"] * 6},
        {"deck": ["a", "b", "c"] * 2, "cursor": -1, "matched": []},
    ],
)
def test_memory_rejects_invalid_saves(data: object) -> None:
    with pytest.raises(ValueError):
        MemoryGame.restore(data)


@pytest.mark.parametrize("style", list(Style))
def test_capture_keeps_full_original_and_separate_derivative(tmp_path: Path, style: Style) -> None:
    store = Store(tmp_path)
    source = fixture(0)
    before = source.tobytes()
    photo = store.capture(source, style, None)
    assert source.tobytes() == before
    assert store.image(photo.id, True).tobytes() == before
    assert store.image(photo.id, True).size == (320, 240)
    assert Store(tmp_path).photos() == [photo]
    assert store.image(photo.id).tobytes() == apply_style(source, style).tobytes()


def test_atomic_replace_failure_preserves_old_state(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    atomic_write(path, b"old")
    with patch("imagegencam.quest.storage.os.replace", side_effect=OSError("full")):
        with pytest.raises(OSError):
            atomic_write(path, b"new")
    assert path.read_bytes() == b"old"
    assert not list(tmp_path.glob(".pending-*"))


def test_corrupt_progress_is_preserved_and_games_still_start(tmp_path: Path) -> None:
    (tmp_path / "state.json").write_text("broken json")
    app = Quest(FixtureCamera(), Store(tmp_path))
    assert app.stamps == set()
    assert app.store.warnings
    assert next(tmp_path.glob("state-unreadable-*.json")).read_text() == "broken json"
    app.persist()
    assert Store(tmp_path).load_progress()["schema_version"] == 1


def test_photo_path_traversal_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        Store(tmp_path).image("../../private")


def test_offline_capture_album_memory_and_mission_roundtrip(tmp_path: Path) -> None:
    app = Quest(FixtureCamera(), Store(tmp_path), Random(1))
    app.handle(Action.CONFIRM, 0)  # Home → camera
    app.handle(Action.RIGHT, 1)  # Pixels
    app.handle(Action.CONFIRM, 2)
    assert len(app.photos) == 1
    app.handle(Action.DOWN, 3)
    assert app.screen == Screen.ALBUM
    app.handle(Action.CONFIRM, 4)
    assert app.original
    app.handle(Action.HOME, 5)
    app.handle(Action.RIGHT, 6)
    app.handle(Action.CONFIRM, 7)
    app.handle(Action.CONFIRM, 8)
    assert app.screen == Screen.MEMORY
    assert app.memory is not None
    for value in set(app.memory.deck):
        for index, card in enumerate(app.memory.deck):
            if card == value:
                app.memory.cursor = index
                app.handle(Action.CONFIRM, 9)
    assert app.memory.complete
    app.handle(Action.HOME, 10)
    app.handle(Action.RIGHT, 11)
    app.handle(Action.CONFIRM, 12)
    app.handle(Action.CONFIRM, 13)
    app.handle(Action.CONFIRM, 14)
    assert app.screen == Screen.REVIEW
    assert not app.stamps  # Photo alone never awards a stamp.
    app.handle(Action.CONFIRM, 15)
    restored = Quest(FixtureCamera(), Store(tmp_path))
    assert restored.stamps == {0}
    assert restored.memory is not None and restored.memory.complete
    assert len(restored.photos) == 2


def test_save_failure_shows_error_without_claiming_photo_saved(tmp_path: Path) -> None:
    app = Quest(FixtureCamera(), Store(tmp_path))
    app.handle(Action.CONFIRM, 0)
    with patch.object(app.store, "capture", side_effect=OSError("disk full")):
        app.handle(Action.CONFIRM, 1)
    assert not app.photos
    assert "Could not" in app.notice
    assert app.screen == Screen.CAMERA


def test_missing_game_photo_uses_fallback(tmp_path: Path) -> None:
    app = Quest(FixtureCamera(), Store(tmp_path))
    app.memory = MemoryGame.create(["f" * 32], Random(0))
    app.screen = Screen.PLAY
    app.handle(Action.CONFIRM, 0)
    assert render(app).size == (240, 240)


@pytest.mark.parametrize("screen", list(Screen))
def test_screens_render_without_hardware_or_credentials(tmp_path: Path, screen: Screen) -> None:
    app = Quest(FixtureCamera(), Store(tmp_path))
    app.screen = Screen.PLAY
    app.handle(Action.CONFIRM, 0)
    app.screen = screen
    output = render(app)
    assert output.size == (240, 240)
    assert output.mode == "RGB"
