import os
import pty
import select
import shlex
import stat
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from imagegencam.config import load_env_file
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
        "\x1b[200~test-key\x1b[201~",
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


def test_clipboard_setup_bypasses_prompt_and_keeps_key_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    path = tmp_path / ".env"
    with (
        patch("sys.platform", "darwin"),
        patch("getpass.getpass") as prompt,
        patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(
                ["/usr/bin/pbpaste"], 0, stdout="clipboard-test-key\n"
            ),
        ) as read_clipboard,
    ):
        setup_gemini(path, clipboard=True)
    prompt.assert_not_called()
    read_clipboard.assert_called_once_with(
        ["/usr/bin/pbpaste"], capture_output=True, text=True, check=True, timeout=5
    )
    assert path.read_text() == "GEMINI_API_KEY=clipboard-test-key\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert "clipboard-test-key" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "failure",
    [
        subprocess.TimeoutExpired("pbpaste", 5, output="private-test-content"),
        subprocess.CalledProcessError(1, "pbpaste", output="private-test-content"),
    ],
)
def test_clipboard_read_failure_is_safe(tmp_path: Path, failure: Exception) -> None:
    path = tmp_path / ".env"
    path.write_text("OTHER=yes\n")
    with patch("sys.platform", "darwin"), patch("subprocess.run", side_effect=failure):
        with pytest.raises(ValueError, match="Could not read clipboard") as error:
            setup_gemini(path, clipboard=True)
    assert "private-test-content" not in str(error.value)
    assert path.read_text() == "OTHER=yes\n"


def test_clipboard_option_selects_gemini() -> None:
    args = parse_options(["--setup-gemini-clipboard"])
    assert args.setup_gemini_clipboard and args.provider == "gemini"
    with pytest.raises(SystemExit):
        parse_options(["--setup-gemini-clipboard", "--setup-gemini"])
    with pytest.raises(SystemExit):
        parse_options(["--setup-gemini-clipboard", "--provider", "none"])


def test_launcher_waits_for_copy_then_saves_and_starts_app(tmp_path: Path) -> None:
    """Run the real shell launcher/CLI through a terminal with a fake clipboard.

    No real clipboard, key, webcam, or network request is needed.
    """
    bootstrap = tmp_path / "bootstrap.py"
    bootstrap.write_text(
        "import os, runpy, subprocess, sys\n"
        "from pathlib import Path\n"
        "from unittest.mock import patch\n"
        "from imagegencam.quest import configuration\n"
        "root = Path(os.environ['QUEST_TEST_ROOT'])\n"
        "configuration.env_path = lambda: root / '.env'\n"
        "original_run = subprocess.run\n"
        "def clipboard(command, **kwargs):\n"
        "    if command != ['/usr/bin/pbpaste']:\n"
        "        return original_run(command, **kwargs)\n"
        "    assert (root / 'copied').exists(), 'Clipboard read before confirmation'\n"
        "    return subprocess.CompletedProcess(command, 0, stdout='test-clipboard-key')\n"
        "sys.argv = [sys.argv[2], *sys.argv[3:]]\n"
        "with patch('sys.platform', 'darwin'), patch('subprocess.run', side_effect=clipboard):\n"
        "    runpy.run_module('imagegencam.quest', run_name='__main__')\n"
    )
    wrapper = tmp_path / "python"
    wrapper.write_text(
        f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(bootstrap))} "$@"\n'
    )
    wrapper.chmod(0o700)
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in ("GEMINI_API_KEY", "OPENAI_API_KEY")
    }
    environment.update(
        QUEST_PYTHON=str(wrapper),
        QUEST_TEST_ROOT=str(tmp_path),
        SDL_VIDEODRIVER="dummy",
        PYTHONUNBUFFERED="1",
    )
    master, slave = pty.openpty()
    launcher = Path(__file__).resolve().parents[2] / "scripts" / "run_quest.sh"
    process = subprocess.Popen(
        [
            "bash",
            str(launcher),
            "--setup-gemini-clipboard",
            "--camera",
            "fixture",
            "--frames",
            "1",
            "--data-dir",
            str(tmp_path / "data"),
        ],
        stdin=slave,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=environment,
    )
    os.close(slave)
    try:
        assert process.stdout is not None
        output = b""
        deadline = time.monotonic() + 15
        while b"Press Enter when the key is copied" not in output:
            assert time.monotonic() < deadline, output.decode()
            ready, _, _ = select.select([process.stdout], [], [], 0.2)
            if ready:
                chunk = os.read(process.stdout.fileno(), 4096)
                assert chunk, output.decode()
                output += chunk
        assert not (tmp_path / ".env").exists()
        (tmp_path / "copied").touch()
        os.write(master, b"\n")
        remainder, _ = process.communicate(timeout=15)
        output += remainder
        assert process.returncode == 0, output.decode()
        assert b"Gemini key saved locally" in output
        assert b"Provider: gemini" in output
        assert b"test-clipboard-key" not in output
        assert (tmp_path / ".env").read_text() == "GEMINI_API_KEY=test-clipboard-key\n"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)


def test_key_punctuation_is_preserved_on_save_and_reload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = "test.token+with/punctuation=:value"
    path = tmp_path / ".env"
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with patch("getpass.getpass", return_value=key):
        setup_gemini(path)
    monkeypatch.delenv("GEMINI_API_KEY")
    load_env_file(path)
    assert os.environ["GEMINI_API_KEY"] == key


def test_copied_command_explains_copy_order_without_saving(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    with patch("getpass.getpass", return_value="bash software/scripts/run_quest.sh"):
        with pytest.raises(ValueError, match="clipboard contains a command"):
            setup_gemini(path)
    assert not path.exists()


@pytest.mark.parametrize(
    ("copied", "reason"),
    [
        ("private…value", "masked or shortened"),
        ("private\u200bvalue", "invisible Unicode"),
        ("private\nvalue", "line breaks"),
        ("private\x00value", "control characters"),
    ],
)
def test_clipboard_rejection_explains_category_without_exposing_content(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], copied: str, reason: str
) -> None:
    path = tmp_path / ".env"
    path.write_text("OTHER=yes\n")
    with (
        patch("sys.platform", "darwin"),
        patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(["/usr/bin/pbpaste"], 0, stdout=copied),
        ),
    ):
        with pytest.raises(ValueError):
            setup_gemini(path, clipboard=True)
    output = capsys.readouterr().out
    assert reason in output
    assert "private" not in output
    assert path.read_text() == "OTHER=yes\n"


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
