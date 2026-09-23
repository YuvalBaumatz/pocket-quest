from pathlib import Path

import pytest

from imagegencam.quest.device import FixtureCamera, fixture
from imagegencam.quest.filters import Style
from imagegencam.quest.input import Action
from imagegencam.quest.missions import MISSIONS
from imagegencam.quest.render import render
from imagegencam.quest.runtime import Quest, Screen
from imagegencam.quest.storage import Store


@pytest.mark.parametrize("mission", range(12))
def test_mission_evidence_review_after_restart_awards_once(tmp_path: Path, mission: int) -> None:
    store = Store(tmp_path)
    photo = store.capture(fixture(0), Style.ORIGINAL, mission)
    app = Quest(FixtureCamera(), store, provider="none")
    app.screen, app.mission_index = Screen.EXPLORE, mission
    assert photo.id in [p.id for p in app.photos]
    app.handle(Action.UP, 0)
    assert app.screen == Screen.REVIEW and app.active_mission == mission
    app.handle(Action.CONFIRM, 1)
    assert app.stamps == {mission}
    app.handle(Action.UP, 2)
    app.handle(Action.CONFIRM, 3)
    assert app.stamps == {mission}
    app.close()
    restored = Quest(FixtureCamera(), store, provider="none")
    assert restored.stamps == {mission}
    assert restored.photos[0].mission == mission


def test_passport_pages_and_mission_wrap(tmp_path: Path) -> None:
    app = Quest(FixtureCamera(), Store(tmp_path), provider="none")
    assert len(MISSIONS) == 12
    app.screen = Screen.EXPLORE
    app.handle(Action.LEFT, 0)
    assert app.mission_index == 11
    app.handle(Action.DOWN, 1)
    assert app.screen == Screen.PASSPORT and app.passport_page == 1
    assert render(app).size == (240, 240)
    app.handle(Action.RIGHT, 2)
    assert app.passport_page == 0
    app.handle(Action.BACK, 3)
    assert app.screen == Screen.EXPLORE


def test_mission_cannot_be_confirmed_without_evidence(tmp_path: Path) -> None:
    app = Quest(FixtureCamera(), Store(tmp_path), provider="none")
    app.screen = Screen.EXPLORE
    app.handle(Action.UP, 0)
    assert app.screen == Screen.EXPLORE
    assert app.stamps == set()
