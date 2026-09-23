from pathlib import Path
from random import Random

import pytest

from imagegencam.quest.copy_pip import DIRECTIONS, CopyPip, Phase
from imagegencam.quest.device import FixtureCamera, fixture
from imagegencam.quest.filters import Style
from imagegencam.quest.input import Action, InputMapper
from imagegencam.quest.photo_guess import PhotoGuess
from imagegencam.quest.render import render
from imagegencam.quest.runtime import Quest, Screen
from imagegencam.quest.storage import Store


def finish_demo(game: CopyPip) -> float:
    for _ in range(12):
        if game.phase == Phase.INPUT:
            return game.due
        game.tick(game.due)
    raise AssertionError("Demo did not finish")


def test_copy_pip_flash_gap_and_ignored_demo_input() -> None:
    rng = Random(1)
    game = CopyPip.create(rng, 0)
    expected = game.sequence.copy()
    game.handle(expected[0], 0.1, rng)
    assert game.position == 0 and game.sequence == expected
    assert not game.tick(0.599)
    assert game.lit == expected[0]
    assert game.tick(0.6) and game.lit is None
    assert not game.tick(0.849)
    assert game.tick(0.85) and game.phase == Phase.INPUT


def test_copy_pip_mistake_retries_same_sequence_and_replay_is_free() -> None:
    rng = Random(3)
    game = CopyPip.create(rng, 0)
    sequence = game.sequence.copy()
    finish_demo(game)
    wrong = next(x for x in DIRECTIONS if x != sequence[0])
    game.handle(wrong, 1, rng)
    assert game.phase == Phase.AGAIN
    game.tick(1.8)
    assert game.phase == Phase.WATCH and game.sequence == sequence
    finish_demo(game)
    game.handle(Action.CONFIRM, 3, rng)
    assert game.phase == Phase.WATCH and game.sequence == sequence


def test_copy_pip_five_rounds_complete_and_resume_validates() -> None:
    rng = Random(9)
    game = CopyPip.create(rng, 0)
    for length in range(1, 6):
        now = finish_demo(game)
        assert len(game.sequence) == length
        for action in game.sequence.copy():
            now += 0.1
            game.handle(action, now, rng)
        assert game.phase == (Phase.COMPLETE if length == 5 else Phase.SUCCESS)
    restored = CopyPip.restore(game.snapshot())
    assert restored.phase == Phase.COMPLETE
    assert len(restored.sequence) == 5


def test_copy_pip_stalled_frame_does_not_skip_demonstration() -> None:
    game = CopyPip([Action.UP, Action.LEFT])
    game.replay(0)
    game.tick(100)
    assert game.phase == Phase.WATCH and game.lit is None
    game.tick(100.25)
    assert game.lit == Action.LEFT


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        {"sequence": [], "complete": False},
        {"sequence": ["home"], "complete": False},
        {"sequence": ["up"], "complete": True},
        {"sequence": ["up"] * 6, "complete": False},
    ],
)
def test_bad_copy_pip_save_rejected(data: object) -> None:
    with pytest.raises(ValueError):
        CopyPip.restore(data)


def test_copy_pip_held_direction_needs_release_before_next_guess() -> None:
    inputs = InputMapper()
    assert inputs.press(Action.UP, 0) == [Action.UP]
    assert inputs.tick(1, repeat_directions=False) == []
    assert inputs.press(Action.UP, 2) == []
    inputs.release(Action.UP, 3)
    assert inputs.press(Action.UP, 4) == [Action.UP]
    inputs.press(Action.BACK, 5)
    assert inputs.tick(6, repeat_directions=False) == [Action.HOME]


def test_photo_guess_five_levels_next_and_resume() -> None:
    choices = ["fixture:0", "fixture:1"]
    game = PhotoGuess(choices[0])
    for level in range(1, 5):
        game.advance(choices)
        assert game.level == level and game.photo_id == choices[0]
    assert PhotoGuess.restore(game.snapshot()).level == 4
    game.advance(choices)
    assert game.photo_id == choices[1] and game.level == 0


@pytest.mark.parametrize(
    "data",
    [
        {"photo_id": "../../.env", "level": 0},
        {"photo_id": "fixture:0", "level": True},
        {"photo_id": "fixture:0", "level": 5},
    ],
)
def test_photo_guess_rejects_invalid_save(data: object) -> None:
    with pytest.raises(ValueError):
        PhotoGuess.restore(data)


def test_all_games_navigation_and_restart_preserve_progress(tmp_path: Path) -> None:
    app = Quest(FixtureCamera(), Store(tmp_path), provider="none")
    app.screen = Screen.PLAY
    app.handle(Action.RIGHT, 0)
    app.handle(Action.CONFIRM, 1)
    assert app.screen == Screen.COPY_PIP and app.copy_pip
    sequence = app.copy_pip.sequence.copy()
    app.handle(Action.BACK, 2)
    assert app.screen == Screen.PLAY
    app.handle(Action.RIGHT, 3)
    app.handle(Action.CONFIRM, 4)
    assert app.screen == Screen.GUESS
    app.handle(Action.CONFIRM, 5)
    app.handle(Action.BACK, 6)
    app.close()
    restored = Quest(FixtureCamera(), Store(tmp_path), provider="none")
    assert restored.copy_pip and restored.copy_pip.sequence == sequence
    assert restored.guess and restored.guess.level == 1
    restored.screen, restored.play_index = Screen.PLAY, 1
    restored.handle(Action.CONFIRM, 50)
    assert restored.copy_pip.lit == sequence[0]
    assert restored.copy_pip.due == 50.6
    assert render(restored).size == (240, 240)


def test_photo_guess_skips_missing_and_corrupt_originals(tmp_path: Path) -> None:
    store = Store(tmp_path)
    first = store.capture(fixture(0), Style.ORIGINAL, None)
    second = store.capture(fixture(1), Style.ORIGINAL, None)
    app = Quest(FixtureCamera(), store, provider="none")
    (tmp_path / "photos" / first.id / "original.png").unlink()
    (tmp_path / "photos" / second.id / "original.png").write_bytes(b"bad")
    app.screen, app.play_index = Screen.PLAY, 2
    app.handle(Action.CONFIRM, 0)
    assert app.guess and app.guess.photo_id == "fixture:0"
    for i in range(5):
        app.handle(Action.CONFIRM, i + 1)
    assert app.guess.photo_id == "fixture:1"
    assert render(app).size == (240, 240)


def test_copy_pip_clock_pauses_when_window_loses_focus(tmp_path: Path) -> None:
    app = Quest(FixtureCamera(), Store(tmp_path), provider="none")
    app.screen, app.play_index = Screen.PLAY, 1
    app.handle(Action.CONFIRM, 0)
    assert app.copy_pip
    lit = app.copy_pip.lit
    app.games_paused = True
    app.tick(20)
    assert app.copy_pip.lit == lit
    app.copy_pip.replay(21)
    app.games_paused = False
    app.tick(21.59)
    assert app.copy_pip.lit == lit
