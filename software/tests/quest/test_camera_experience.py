import time
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from imagegencam.quest.device import FixtureCamera, fixture
from imagegencam.quest.filters import Style, apply_style
from imagegencam.quest.input import Action
from imagegencam.quest.jobs import JobState
from imagegencam.quest.runtime import Quest, Screen
from imagegencam.quest.storage import Store
from imagegencam.quest.workers import CaptureResult


def capture(app: Quest) -> None:
    app.handle(Action.CONFIRM, 0)
    deadline = time.monotonic() + 3
    while app.capturing and time.monotonic() < deadline:
        app.tick(0.1)
        time.sleep(0.005)
    assert not app.capturing


@pytest.mark.parametrize("style", [Style.ORIGINAL, Style.PIXELS, Style.MONO])
def test_local_capture_opens_saved_result_and_preserves_original(
    tmp_path: Path, style: Style
) -> None:
    app = Quest(FixtureCamera(), Store(tmp_path), provider="none", start_generation=False)
    app.screen = Screen.CAMERA
    app.style_index = app.styles.index(style)
    capture(app)
    assert app.screen == Screen.ALBUM
    assert len(app.photos) == 1
    photo = app.photos[0]
    original = app.store.image(photo.id, True)
    assert app.image.tobytes() == apply_style(original, style).tobytes()
    app.handle(Action.CONFIRM, 1)
    assert app.original
    assert app.image.tobytes() == original.tobytes()
    assert app.jobs.all() == []


def test_ai_capture_approval_and_view_open_the_matching_photo(tmp_path: Path) -> None:
    store = Store(tmp_path)
    older = store.capture(fixture(1), Style.ORIGINAL, None)
    app = Quest(FixtureCamera(), store, start_generation=False)
    app.screen = Screen.CAMERA
    app.style_index = app.styles.index(Style.CLAY)
    capture(app)
    photo = app.photos[-1]
    original = store.image(photo.id, True).tobytes()
    assert app.screen == Screen.QUEUE
    assert app.current_job is not None and app.current_job.id == photo.id
    assert app.current_job.state == JobState.AWAITING
    assert not app.generation.process_one()
    app.handle(Action.CONFIRM, 1)
    assert app.screen == Screen.APPROVE
    assert not app.generation.process_one()
    app.handle(Action.CONFIRM, 2)
    assert app.generation.process_one()
    app.tick(3)
    assert app.current_job.state == JobState.SUCCEEDED
    # A later capture must not change which result the queue opens.
    later = store.capture(fixture(2), Style.ORIGINAL, None)
    app.photos.append(later)
    app.handle(Action.CONFIRM, 4)
    assert app.screen == Screen.ALBUM
    assert app.photos[app.album_index].id == photo.id
    assert photo.id not in (older.id, later.id)
    assert not app.original
    assert app.image.tobytes() == store.image(photo.id).tobytes()
    assert store.image(photo.id, True).tobytes() == original
    app.close()
    restarted = Quest(FixtureCamera(), store, start_generation=False)
    assert restarted.jobs.all()[0].state == JobState.SUCCEEDED
    assert store.image(photo.id, True).tobytes() == original


@pytest.mark.parametrize("screen,mission", [(Screen.HOME, None), (Screen.CAMERA, 1)])
def test_capture_completion_does_not_pull_user_away_from_new_activity(
    tmp_path: Path, screen: Screen, mission: int | None
) -> None:
    app = Quest(FixtureCamera(), Store(tmp_path), start_generation=False)
    photo = app.store.capture(fixture(0), Style.MONO, None)
    app.capturing = True
    app.capture_worker.results.put(CaptureResult(photo, "Photo saved!"))
    app.screen, app.active_mission = screen, mission
    app.tick(1)
    assert app.screen == screen
    assert app.active_mission == mission
    assert app.photos[-1].id == photo.id


def test_style_change_updates_preview_without_mutating_camera_frame(tmp_path: Path) -> None:
    app = Quest(FixtureCamera(), Store(tmp_path), start_generation=False)
    app.screen = Screen.CAMERA
    frame = fixture(0)
    original = frame.tobytes()
    with patch.object(app.capture_worker, "preview", return_value=(frame, 1, "")):
        app.tick(0)
        app.handle(Action.RIGHT, 1)
        app.tick(1)
        assert app.style == Style.PIXELS
        assert app.image.tobytes() == apply_style(frame, Style.PIXELS).tobytes()
        app.handle(Action.RIGHT, 2)
        app.tick(2)
        assert app.style == Style.MONO
        assert app.image.tobytes() == apply_style(frame, Style.MONO).tobytes()
        app.handle(Action.RIGHT, 3)
        app.tick(3)
        assert app.style.is_ai
        assert app.image.tobytes() == original
    assert frame.tobytes() == original


@pytest.mark.parametrize("size", [(1, 1), (40, 80), (1280, 720), (720, 1280)])
def test_pixel_filter_handles_portrait_landscape_and_tiny_images(size: tuple[int, int]) -> None:
    source = Image.new("RGB", size, (60, 120, 200))
    before = source.tobytes()
    result = apply_style(source, Style.PIXELS)
    assert result.size == size
    assert result.mode == "RGB"
    assert result is not source
    assert source.tobytes() == before
