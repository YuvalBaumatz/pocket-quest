"""Run `python -m imagegencam.quest --help` for simulator and screenshot commands."""

import argparse
import importlib.util
import os
import sys
import time
from pathlib import Path

from .configuration import load_credentials, setup_gemini
from .device import Camera, FileCamera, FixtureCamera, PiCamera, WebcamCamera
from .export import export_photos
from .input import Action, InputMapper
from .render import render
from .runtime import Quest, Screen
from .storage import Store


def parse_options(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pocket Quest: real camera and image transformations"
    )
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument(
        "--export", type=Path, metavar="ZIP", help="Export photos to a new ZIP and exit"
    )
    parser.add_argument(
        "--screenshots",
        type=Path,
        help="Render sample screens and exit, without opening a window",
    )
    parser.add_argument("--scale", type=int, choices=range(1, 5), default=3)
    parser.add_argument("--frames", type=int, help="Exit after N desktop frames (smoke testing)")
    parser.add_argument("--provider", choices=("none", "demo", "openai", "gemini"))
    parser.add_argument(
        "--demo", action="store_true", help="Explicit sample-camera and local-effect mode"
    )
    setup = parser.add_mutually_exclusive_group()
    setup.add_argument(
        "--setup-gemini",
        action="store_true",
        help="Enter the Gemini key privately in your terminal",
    )
    setup.add_argument(
        "--setup-gemini-clipboard",
        action="store_true",
        help="Save the Gemini key from the Mac clipboard without a terminal paste prompt",
    )
    parser.add_argument("--model", help="Image model ID; fixed into each captured magic request")
    parser.add_argument(
        "--offline", action="store_true", help="Pause job dispatch; does not control Wi-Fi radios"
    )
    parser.add_argument("--camera", choices=("fixture", "pi", "webcam"))
    parser.add_argument(
        "--camera-index", type=int, default=0, help="Webcam device index, usually 0"
    )
    parser.add_argument("--image", type=Path, help="Use your own image in the desktop camera")
    args = parser.parse_args(argv)
    if args.export and (args.setup_gemini or args.setup_gemini_clipboard or args.screenshots):
        parser.error("Use --export separately from key setup or screenshots")
    if args.frames is not None and args.frames < 1:
        parser.error("--frames must be positive")
    if args.camera_index < 0:
        parser.error("--camera-index must be non-negative")
    if args.image and args.camera:
        parser.error("Use --image or --camera, not both")
    if args.demo and args.provider not in (None, "demo"):
        parser.error("--demo cannot be combined with a real provider")
    args.provider = args.provider or ("demo" if args.demo else "gemini")
    if args.screenshots and not args.demo:
        parser.error("Sample screenshots require --demo")
    args.camera = args.camera or ("fixture" if args.demo else "webcam")
    if (args.setup_gemini or args.setup_gemini_clipboard) and args.provider != "gemini":
        parser.error("--setup-gemini requires the Gemini provider")
    args.model = (
        args.model
        or {
            "none": "",
            "demo": "demo-v1",
            "openai": "gpt-image-2",
            "gemini": "gemini-3.1-flash-image",
        }[args.provider]
    )
    args.data_dir = args.data_dir or Path.home() / (
        ".pocket-quest-simulator" if args.demo else ".pocket-quest"
    )
    return args


def main() -> None:
    args = parse_options()
    if args.export:
        try:
            count = export_photos(args.data_dir, args.export)
        except (OSError, ValueError) as error:
            raise SystemExit(f"Export failed; photo library unchanged. {error}") from None
        print(f"Exported {count} photos to {args.export.expanduser().absolute()}")
        return
    load_credentials()
    if args.setup_gemini or args.setup_gemini_clipboard:
        if not sys.stdin.isatty():
            raise SystemExit(
                "Run --setup-gemini in your visible Terminal; never paste a key into chat."
            )
        try:
            if args.setup_gemini_clipboard:
                print("Now copy your Gemini API key from AI Studio.")
                print("Return here and press Enter. Do not paste the key or copy another command.")
                try:
                    input("Press Enter when the key is copied (Ctrl+C cancels): ")
                except (EOFError, KeyboardInterrupt):
                    raise ValueError(
                        "Key setup cancelled. Your saved settings were not changed."
                    ) from None
            setup_gemini(clipboard=args.setup_gemini_clipboard)
        except ValueError as error:
            raise SystemExit(str(error)) from None
    key_name = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}.get(args.provider)
    if key_name and not os.environ.get(key_name, "").strip():
        raise SystemExit(
            f"{key_name} is not configured. Run with --setup-gemini for Gemini, or set the provider key locally. Use --provider none for camera-only testing. No demo fallback was used."
        )
    if args.camera == "webcam" and not args.image and importlib.util.find_spec("cv2") is None:
        raise SystemExit(
            "Install software/requirements-mac.txt in the project environment to use the webcam."
        )
    camera: Camera = (
        FileCamera(args.image)
        if args.image
        else PiCamera()
        if args.camera == "pi"
        else WebcamCamera(args.camera_index)
        if args.camera == "webcam"
        else FixtureCamera()
    )
    input_label = "photo file" if args.image else args.camera
    print(
        f"Input: {input_label}. Provider: {args.provider}. Model: {args.model or 'local filters only'}."
    )
    if args.camera == "webcam" and not args.image:
        print(
            "Allow camera access for your Terminal when macOS asks. Camera access begins when you open Camera."
        )
    model = args.model
    app = Quest(
        camera,
        Store(args.data_dir),
        provider=args.provider,
        model=model,
        offline=args.offline,
        start_generation=not bool(args.screenshots),
    )
    try:
        for warning in app.store.warnings:
            print(f"Recovery: {warning}")
        if args.screenshots:
            args.screenshots.mkdir(parents=True, exist_ok=True)
            for screen in (Screen.HOME, Screen.CAMERA, Screen.PLAY, Screen.EXPLORE):
                app.screen = screen
                render(app).save(args.screenshots / f"{screen.value}.png")
            app.screen = Screen.PLAY
            app.handle(Action.CONFIRM, 0)
            render(app).save(args.screenshots / "memory.png")
            return
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        try:
            import pygame
        except ImportError as error:
            raise SystemExit("Install requirements-quest.txt to run the desktop window.") from error
        pygame.display.init()  # No audio device required, including on the plane.
        window = pygame.display.set_mode((240 * args.scale, 240 * args.scale))
        pygame.display.set_caption(
            f"Pocket Quest | {input_label} + {args.provider} | Arrows, Enter=A, Esc=B, H=Home"
        )
        clock = pygame.time.Clock()
        inputs = InputMapper()
        mapping = {
            pygame.K_UP: Action.UP,
            pygame.K_DOWN: Action.DOWN,
            pygame.K_LEFT: Action.LEFT,
            pygame.K_RIGHT: Action.RIGHT,
            pygame.K_RETURN: Action.CONFIRM,
            pygame.K_ESCAPE: Action.BACK,
            pygame.K_h: Action.HOME,
        }
        running, dirty, frames = True, True, 0
        quit_requested = False
        try:
            while running:
                now = time.monotonic()
                actions: list[Action] = []
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        quit_requested = True
                    elif event.type == pygame.WINDOWFOCUSLOST:
                        inputs.clear()
                    elif event.type == pygame.WINDOWEXPOSED:
                        dirty = True
                    elif event.type in (pygame.KEYDOWN, pygame.KEYUP) and event.key in mapping:
                        handler = inputs.press if event.type == pygame.KEYDOWN else inputs.release
                        actions.extend(handler(mapping[event.key], now))
                actions.extend(inputs.tick(now))
                for action in actions:
                    app.handle(action, now)
                dirty = app.tick(now) or bool(actions) or dirty
                if dirty:
                    image = render(app)
                    surface = pygame.image.frombuffer(image.tobytes(), image.size, "RGB")
                    window.blit(pygame.transform.scale(surface, window.get_size()), (0, 0))
                    pygame.display.flip()
                    dirty = False
                if quit_requested and not app.capturing:
                    running = False
                frames += 1
                if args.frames is not None and frames >= args.frames:
                    running = False
                clock.tick(30)
        finally:
            try:
                app.persist()
            finally:
                pygame.quit()
    finally:
        app.close()


if __name__ == "__main__":
    main()
