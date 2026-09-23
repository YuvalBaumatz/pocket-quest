import base64
import json
import threading
import time
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from imagegencam.quest.device import FileCamera, FixtureCamera, PiCamera, fixture
from imagegencam.quest.filters import Style
from imagegencam.quest.input import Action
from imagegencam.quest.jobs import JobQueue, JobState
from imagegencam.quest.providers import (
    DemoProvider,
    EditError,
    EditRequest,
    GeminiProvider,
    OpenAIProvider,
    http_error,
    validated_png,
)
from imagegencam.quest.runtime import Quest, Screen
from imagegencam.quest.storage import Store, encode
from imagegencam.quest.workers import GenerationWorker


@pytest.fixture
def queue(tmp_path: Path) -> Iterator[JobQueue]:
    value = JobQueue(tmp_path)
    yield value
    value.close()


def enqueue(queue: JobQueue, style: Style = Style.CLAY) -> str:
    photo = Store(queue.root).capture(fixture(0), style, None)
    queue.enqueue(photo.id, style, "demo", "demo-v1")
    return photo.id


def wait_for(condition, tick=lambda: None) -> None:
    deadline = time.monotonic() + 3
    while not condition() and time.monotonic() < deadline:
        tick()
        time.sleep(0.005)
    assert condition()


def test_approval_survives_restart_and_original_is_unchanged(tmp_path: Path) -> None:
    queue = JobQueue(tmp_path)
    photo_id = enqueue(queue)
    original = Store(tmp_path).image(photo_id, True).tobytes()
    queue.close()
    queue = JobQueue(tmp_path)
    try:
        worker = GenerationWorker(queue, Store(tmp_path), {"demo": DemoProvider()})
        assert not worker.process_one()
        queue.approve(photo_id)
        assert worker.process_one()
        assert queue.all()[0].state == JobState.SUCCEEDED
        assert Store(tmp_path).image(photo_id, True).tobytes() == original
        assert Store(tmp_path).image(photo_id).tobytes() != original
        assert not worker.process_one()
    finally:
        queue.close()


def test_unapproved_and_offline_jobs_never_call_provider(queue: JobQueue) -> None:
    provider = MagicMock()
    job_id = enqueue(queue)
    worker = GenerationWorker(queue, Store(queue.root), {"demo": provider}, offline=True)
    assert not worker.process_one()
    queue.approve(job_id)
    assert not worker.process_one()
    provider.edit.assert_not_called()
    assert queue.all()[0].attempts == 0


def test_cancelled_running_job_discards_late_image(queue: JobQueue) -> None:
    job_id = enqueue(queue)
    queue.approve(job_id)
    job = queue.claim()
    assert job is not None
    queue.cancel(job_id)
    assert not queue.complete(job, encode(fixture(1)))
    assert queue.all()[0].state == JobState.CANCELLED
    assert not (queue.root / "photos" / job_id / "magic.png").exists()


def test_interrupted_dispatch_requires_explicit_retry(tmp_path: Path) -> None:
    queue = JobQueue(tmp_path)
    job_id = enqueue(queue)
    queue.approve(job_id)
    assert queue.claim() is not None
    queue.close()
    queue = JobQueue(tmp_path)
    try:
        assert queue.all()[0].state == JobState.UNKNOWN
        assert queue.claim() is None
        queue.approve(job_id)
        assert queue.claim().attempts == 2
    finally:
        queue.close()


def test_unknown_timeout_does_not_retry_automatically(queue: JobQueue) -> None:
    job_id = enqueue(queue)
    queue.approve(job_id)
    provider = MagicMock()
    provider.edit.side_effect = EditError("timeout", unknown=True)
    worker = GenerationWorker(queue, Store(queue.root), {"demo": provider})
    assert worker.process_one()
    assert queue.all()[0].state == JobState.UNKNOWN
    assert not worker.process_one()
    assert provider.edit.call_count == 1


def test_rate_limit_retries_only_when_due_and_stops_at_three(queue: JobQueue) -> None:
    job_id = enqueue(queue)
    queue.approve(job_id)
    for attempt in range(1, 4):
        job = queue.claim(now=1000 + attempt * 60)
        assert job is not None
        assert job.attempts == attempt
        with patch("imagegencam.quest.jobs.time.time", return_value=1000 + attempt * 60):
            queue.fail(job, "rate_limit", retry_after=30)
        if attempt < 3:
            assert queue.claim(now=1000 + attempt * 60 + 10) is None
    assert queue.all()[0].state == JobState.FAILED
    queue.approve(job_id)
    assert queue.claim(now=9999) is None


def test_budget_and_queue_capacity_survive_restart(tmp_path: Path) -> None:
    queue = JobQueue(tmp_path, daily_limit=1, pending_limit=1)
    first = enqueue(queue)
    with pytest.raises(ValueError, match="full"):
        enqueue(queue)
    queue.approve(first)
    queue.claim(now=100000)
    queue.cancel(first)
    second = enqueue(queue)
    queue.approve(second)
    queue.close()
    queue = JobQueue(tmp_path, daily_limit=1)
    try:
        assert queue.claim(now=100001) is None
        assert queue.claim(now=0) is None  # Clock rollback cannot reset the cap.
        assert queue.claim(now=200000) is not None
    finally:
        queue.close()


def test_single_data_directory_owner_and_idempotent_approval(queue: JobQueue) -> None:
    with pytest.raises(ValueError, match="already"):
        JobQueue(queue.root)
    job_id = enqueue(queue)
    queue.enqueue(job_id, Style.CLAY, "demo", "different-model")
    queue.approve(job_id)
    queue.approve(job_id)
    assert len(queue.all()) == 1
    assert queue.all()[0].model == "demo-v1"
    claimed = []
    threads = [threading.Thread(target=lambda: claimed.append(queue.claim())) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(value is not None for value in claimed) == 1


def test_original_survives_full_queue_during_capture(tmp_path: Path) -> None:
    app = Quest(FixtureCamera(), Store(tmp_path), start_generation=False)
    app.jobs.pending_limit = 1
    enqueue(app.jobs)
    app.screen = Screen.CAMERA
    app.style_index = list(Style).index(Style.CLAY)
    app.handle(Action.CONFIRM, 0)
    wait_for(lambda: not app.capturing, lambda: app.tick(0.1))
    assert len(app.photos) == 1
    assert "not queued" in app.notice
    assert Store(tmp_path).image(app.photos[0].id, True).size == (320, 240)


def test_background_work_keeps_navigation_live_and_updates_album(tmp_path: Path) -> None:
    entered, release = threading.Event(), threading.Event()

    class SlowProvider:
        def edit(self, request: EditRequest) -> bytes:
            entered.set()
            assert release.wait(3)
            return encode(fixture(2))

    app = Quest(FixtureCamera(), Store(tmp_path), providers={"demo": SlowProvider()})
    try:
        app.screen = Screen.CAMERA
        app.style_index = list(Style).index(Style.CLAY)
        app.handle(Action.CONFIRM, 0)
        app.handle(Action.CONFIRM, 0.01)  # Ignore duplicate shutter while saving.
        wait_for(lambda: not app.capturing, lambda: app.tick(0.1))
        assert len(app.photos) == 1
        app.handle(Action.UP, 1)
        assert app.screen == Screen.QUEUE
        app.handle(Action.CONFIRM, 2)
        assert app.screen == Screen.APPROVE
        app.handle(Action.CONFIRM, 3)
        assert entered.wait(2)
        app.handle(Action.HOME, 4)
        assert app.screen == Screen.HOME
        release.set()
        wait_for(lambda: app.jobs.all()[0].state == JobState.SUCCEEDED)
        app.screen = Screen.ALBUM
        app.tick(5)
        assert app.image.tobytes() == fixture(2).tobytes()
        app.handle(Action.CONFIRM, 6)
        assert app.image.tobytes() == fixture(0).tobytes()
    finally:
        release.set()


def test_file_camera_leaves_input_untouched(tmp_path: Path) -> None:
    path = tmp_path / "source.png"
    path.write_bytes(encode(fixture(1)))
    before = path.read_bytes()
    camera = FileCamera(path)
    camera.capture().putpixel((0, 0), (0, 0, 0))
    assert path.read_bytes() == before
    assert camera.preview().tobytes() == fixture(1).tobytes()


def test_pi_adapter_is_lazy_switches_back_via_api_and_closes() -> None:
    hardware = MagicMock()
    hardware.capture_image.return_value = fixture(0)
    hardware.switch_mode_and_capture_image.return_value = fixture(1)
    module = SimpleNamespace(Picamera2=MagicMock(return_value=hardware))
    with patch.dict("sys.modules", {"picamera2": module}):
        camera = PiCamera()
        module.Picamera2.assert_not_called()
        assert camera.preview().size == (320, 240)
        assert camera.capture().tobytes() == fixture(1).tobytes()
        hardware.switch_mode_and_capture_image.assert_called_once_with(camera.still_config, "main")
        camera.close()
        hardware.stop.assert_called_once()
        hardware.close.assert_called_once()


def test_openai_adapter_uses_source_and_disables_sdk_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    client = MagicMock()
    client.images.edit.return_value = SimpleNamespace(
        data=[SimpleNamespace(b64_json=base64.b64encode(encode(fixture(1))).decode())]
    )
    with patch("openai.OpenAI", return_value=client) as factory:
        result = OpenAIProvider().edit(EditRequest(encode(fixture(0)), "clay", "gpt-image-2"))
        assert result == encode(fixture(1))
        assert factory.call_args.kwargs["max_retries"] == 0
        assert client.images.edit.call_args.kwargs["image"][1] == encode(fixture(0))
        assert client.images.edit.call_args.kwargs["model"] == "gpt-image-2"


def test_gemini_wire_format_and_image_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-only")
    data = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "done"},
                        {
                            "inlineData": {
                                "mimeType": "image/png",
                                "data": base64.b64encode(encode(fixture(2))).decode(),
                            }
                        },
                    ]
                }
            }
        ]
    }
    with patch("urllib.request.urlopen", return_value=BytesIO(json.dumps(data).encode())) as send:
        assert GeminiProvider().edit(
            EditRequest(encode(fixture(0)), "clay", "gemini-3.1-flash-image")
        ) == encode(fixture(2))
        request = send.call_args.args[0]
        body = json.loads(request.data)
        assert body["contents"][0]["parts"][0]["text"] == "clay"
        assert body["generationConfig"]["responseModalities"] == ["TEXT", "IMAGE"]
        assert "test-only" not in request.full_url
        assert send.call_count == 1


@pytest.mark.parametrize("payload", [b"", b"not an image", b"<html>oops</html>"])
def test_malformed_output_is_rejected(payload: bytes) -> None:
    with pytest.raises(EditError):
        validated_png(payload)


@pytest.mark.parametrize(
    "status,code,unknown",
    [
        (401, "credentials", False),
        (400, "request_rejected", False),
        (503, "provider_uncertain", True),
    ],
)
def test_http_failures_are_safe_codes(status: int, code: str, unknown: bool) -> None:
    error = http_error(status)
    assert error.code == code and error.unknown == unknown


def test_gemini_timeout_is_uncertain_and_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-only")
    with patch("urllib.request.urlopen", side_effect=TimeoutError) as send:
        with pytest.raises(EditError) as error:
            GeminiProvider().edit(EditRequest(encode(fixture(0)), "clay", "gemini-3.1-flash-image"))
        assert error.value.unknown
        assert send.call_count == 1


def test_completed_file_recovers_without_second_request(tmp_path: Path) -> None:
    queue = JobQueue(tmp_path)
    job_id = enqueue(queue)
    queue.approve(job_id)
    assert queue.claim() is not None
    # Simulate power loss between durable output write and the DB completion commit.
    (tmp_path / "photos" / job_id / "magic.png").write_bytes(encode(fixture(1)))
    queue.close()
    queue = JobQueue(tmp_path)
    try:
        assert queue.all()[0].state == JobState.SUCCEEDED
        assert queue.claim() is None
    finally:
        queue.close()


def test_other_provider_jobs_are_not_spent_or_retargeted(queue: JobQueue) -> None:
    photo = Store(queue.root).capture(fixture(0), Style.CLAY, None)
    queue.enqueue(photo.id, Style.CLAY, "openai", "gpt-image-2")
    queue.approve(photo.id)
    worker = GenerationWorker(queue, Store(queue.root), {"demo": DemoProvider()})
    assert not worker.process_one()
    assert queue.all()[0].state == JobState.READY
    assert queue.all()[0].attempts == 0


def test_bad_queue_version_preserves_database_and_releases_lock(tmp_path: Path) -> None:
    import sqlite3

    queue = JobQueue(tmp_path)
    queue.db.execute("PRAGMA user_version=999")
    queue.close()
    with pytest.raises(ValueError, match="Unsupported"):
        JobQueue(tmp_path)
    with sqlite3.connect(tmp_path / "generation.sqlite3") as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 999
        db.execute("PRAGMA user_version=1")
    JobQueue(tmp_path).close()


def test_orphan_original_returns_to_album_without_upload(tmp_path: Path) -> None:
    directory = tmp_path / "photos" / ("a" * 32)
    directory.mkdir(parents=True)
    (directory / "original.png").write_bytes(encode(fixture(1)))
    photos = Store(tmp_path).photos()
    assert len(photos) == 1
    assert photos[0].style == Style.ORIGINAL
    assert not (tmp_path / "generation.sqlite3").exists()


def test_local_filter_failure_does_not_lose_original(tmp_path: Path) -> None:
    store = Store(tmp_path)
    with patch("imagegencam.quest.storage.apply_style", side_effect=ValueError("bad filter")):
        photo = store.capture(fixture(0), Style.PIXELS, None)
    assert store.photos() == [photo]
    assert store.image(photo.id, True).tobytes() == fixture(0).tobytes()
    assert store.warnings


def test_invalid_image_failure_never_overwrites_original(queue: JobQueue) -> None:
    job_id = enqueue(queue)
    queue.approve(job_id)
    provider = MagicMock()
    provider.edit.return_value = b"html error"
    worker = GenerationWorker(queue, Store(queue.root), {"demo": provider})
    worker.process_one()
    assert queue.all()[0].state == JobState.FAILED
    assert not (queue.root / "photos" / job_id / "magic.png").exists()
    assert Store(queue.root).image(job_id, True).tobytes() == fixture(0).tobytes()


def test_missing_camera_does_not_block_games(tmp_path: Path) -> None:
    camera = MagicMock()
    camera.preview.side_effect = RuntimeError("no camera")
    camera.capture.side_effect = RuntimeError("no camera")
    app = Quest(camera, Store(tmp_path))
    app.screen = Screen.CAMERA
    app.handle(Action.CONFIRM, 0)
    wait_for(lambda: not app.capturing, lambda: app.tick(0.1))
    assert "Could not" in app.notice
    app.handle(Action.HOME, 1)
    app.handle(Action.RIGHT, 2)
    app.handle(Action.CONFIRM, 3)
    app.handle(Action.CONFIRM, 4)
    assert app.screen == Screen.MEMORY


def test_openai_connection_error_is_uncertain_and_only_sent_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import openai

    client = MagicMock()
    client.images.edit.side_effect = openai.APIConnectionError(request=MagicMock())
    with pytest.raises(EditError) as error:
        OpenAIProvider(client).edit(EditRequest(encode(fixture(0)), "clay", "gpt-image-2"))
    assert error.value.unknown
    assert client.images.edit.call_count == 1


def test_provider_keys_not_needed_until_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    request = EditRequest(encode(fixture(0)), "clay", "model")
    for provider in (OpenAIProvider(), GeminiProvider()):
        with pytest.raises(EditError, match="credentials"):
            provider.edit(request)


def test_invalid_job_id_cannot_escape_data_root(queue: JobQueue) -> None:
    with pytest.raises(ValueError, match="Invalid"):
        queue.enqueue("../../elsewhere", Style.CLAY, "demo", "demo-v1")
