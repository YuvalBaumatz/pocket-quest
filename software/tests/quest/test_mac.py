import os
import stat
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from imagegencam.quest.__main__ import parse_options
from imagegencam.quest.configuration import setup_gemini
from imagegencam.quest.device import CameraUnavailable, FixtureCamera, WebcamCamera
from imagegencam.quest.filters import Style
from imagegencam.quest.input import Action
from imagegencam.quest.runtime import Quest, Screen
from imagegencam.quest.storage import Store


def test_normal_launch_uses_real_webcam_and_gemini() -> None:
    options = parse_options([])
    assert options.camera == "webcam"
    assert options.provider == "gemini"
    assert options.data_dir.name == ".pocket-quest"
    demo = parse_options(["--demo"])
    assert demo.camera == "fixture" and demo.provider == "demo"
    assert demo.data_dir != options.data_dir


@pytest.mark.parametrize(
    "args",
    [
        ["--demo", "--provider", "gemini"],
        ["--screenshots", "/tmp/screens"],
        ["--camera-index", "-1"],
        ["--image", "x.png", "--camera", "webcam"],
    ],
)
def test_incompatible_modes_fail_explicitly(args: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse_options(args)


def test_local_only_mode_has_no_ai_styles_or_provider(tmp_path: Path) -> None:
    app = Quest(FixtureCamera(), Store(tmp_path), provider="none", model="")
    assert app.styles == [Style.ORIGINAL, Style.PIXELS, Style.MONO]
    assert app.generation.providers == {}
    app.screen = Screen.CAMERA
    for _ in range(5):
        app.handle(Action.RIGHT, 0)
        assert not app.style.is_ai


def test_key_setup_is_private_preserves_other_settings_and_never_prints_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / ".env"
    path.write_text("# keep this\nOTHER_SETTING=yes\nGEMINI_API_KEY=old\n")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with patch("getpass.getpass", return_value="new-test-key"):
        setup_gemini(path)
    assert path.read_text() == "# keep this\nOTHER_SETTING=yes\nGEMINI_API_KEY=new-test-key\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert os.environ["GEMINI_API_KEY"] == "new-test-key"
    assert "new-test-key" not in capsys.readouterr().out


def test_invalid_key_does_not_modify_file(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("OTHER_SETTING=yes\n")
    with patch("getpass.getpass", return_value="bad\nkey"):
        with pytest.raises(ValueError):
            setup_gemini(path)
    assert path.read_text() == "OTHER_SETTING=yes\n"


@pytest.mark.parametrize(
    "pasted",
    [
        "  test-key  ",
        '"test-key"',
        "'test-key'",
        'GEMINI_API_KEY="test-key"',
        "export GEMINI_API_KEY='test-key'",
    ],
)
def test_key_setup_accepts_common_paste_formats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pasted: str
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    path = tmp_path / ".env"
    with patch("getpass.getpass", return_value=pasted):
        setup_gemini(path)
    assert path.read_text() == "GEMINI_API_KEY=test-key\n"


def test_key_setup_retries_without_echoing_rejected_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with patch("getpass.getpass", side_effect=["", "secret with spaces", "valid-key"]):
        setup_gemini(tmp_path / ".env")
    output = capsys.readouterr().out
    assert "No key was received" in output
    assert "unsupported characters" in output
    assert "secret with spaces" not in output and "valid-key" not in output
    assert os.environ["GEMINI_API_KEY"] == "valid-key"


@pytest.mark.parametrize("interruption", [EOFError, KeyboardInterrupt])
def test_key_setup_cancellation_preserves_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interruption: type[BaseException]
) -> None:
    path = tmp_path / ".env"
    path.write_text("GEMINI_API_KEY=previous-key\n")
    monkeypatch.setenv("GEMINI_API_KEY", "previous-key")
    with patch("getpass.getpass", side_effect=interruption):
        with pytest.raises(ValueError, match="cancelled"):
            setup_gemini(path)
    assert path.read_text() == "GEMINI_API_KEY=previous-key\n"
    assert os.environ["GEMINI_API_KEY"] == "previous-key"


def webcam_backend(frame: np.ndarray) -> MagicMock:
    camera = MagicMock()
    camera.isOpened.return_value = True
    camera.read.return_value = (True, frame)
    return camera


def test_webcam_uses_avfoundation_and_converts_bgr_to_rgb_without_opening_early() -> None:
    pixels = np.zeros((720, 1280, 3), dtype=np.uint8)
    pixels[:, :] = (11, 22, 33)
    backend = webcam_backend(pixels)
    with patch("cv2.VideoCapture", return_value=backend) as create, patch("sys.platform", "darwin"):
        import cv2

        camera = WebcamCamera(1)
        create.assert_not_called()
        preview = camera.preview()
        assert preview.size == (320, 180)
        assert preview.getpixel((0, 0)) == (33, 22, 11)
        captured = camera.capture()
        assert captured.size == (1280, 720)
        create.assert_called_once_with(1, cv2.CAP_AVFOUNDATION)
        assert backend.read.call_count == 2
        camera.close()
        backend.release.assert_called_once()


def test_denied_webcam_never_returns_a_fixture() -> None:
    backend = MagicMock()
    backend.isOpened.return_value = False
    with patch("cv2.VideoCapture", return_value=backend):
        camera = WebcamCamera()
        with pytest.raises(CameraUnavailable, match="access"):
            camera.capture()
        backend.release.assert_called_once()
        assert camera.camera is None


def test_empty_camera_frames_are_bounded_and_release_device() -> None:
    backend = webcam_backend(np.zeros((1, 1, 3), dtype=np.uint8))
    backend.read.return_value = (False, None)
    with patch("cv2.VideoCapture", return_value=backend):
        camera = WebcamCamera()
        with pytest.raises(CameraUnavailable, match="No camera image"):
            camera.preview()
        assert backend.read.call_count == 5
        backend.release.assert_called_once()
