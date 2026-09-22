"""Run `python -m imagegencam.quest --help` for simulator and screenshot commands."""

import argparse
import os
import time
from pathlib import Path

from .device import Camera, FileCamera, FixtureCamera, PiCamera
from .input import Action, InputMapper
from .render import render
from .runtime import Quest, Screen
from .storage import Store


def main() -> None:
    parser = argparse.ArgumentParser(description="Pocket Quest offline desktop simulator")
    parser.add_argument("--data-dir", type=Path, default=Path.home() / ".pocket-quest-simulator")
    parser.add_argument(
        "--screenshots",
        type=Path,
        help="Render sample screens and exit, without opening a window",
    )
    parser.add_argument("--scale", type=int, choices=range(1, 5), default=3)
    parser.add_argument("--frames", type=int, help="Exit after N desktop frames (smoke testing)")
    parser.add_argument("--provider", choices=("demo", "openai", "gemini"), default="demo")
    parser.add_argument("--model", help="Image model ID; fixed into each captured magic request")
    parser.add_argument(
        "--offline", action="store_true", help="Pause job dispatch; does not control Wi-Fi radios"
    )
    parser.add_argument("--camera", choices=("fixture", "pi"), default="fixture")
    parser.add_argument("--image", type=Path, help="Use your own image in the desktop camera")
    args = parser.parse_args()
    if args.frames is not None and args.frames < 1:
        parser.error("--frames must be positive")
    if args.image and args.camera == "pi":
        parser.error("--image and --camera pi cannot be combined")
    camera: Camera = (
        FileCamera(args.image)
        if args.image
        else PiCamera()
        if args.camera == "pi"
        else FixtureCamera()
    )
    model = (
        args.model
        or {"demo": "demo-v1", "openai": "gpt-image-2", "gemini": "gemini-3.1-flash-image"}[
            args.provider
        ]
    )
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
        pygame.display.set_caption("Pocket Quest | Arrows, Enter=A, Esc=B, H=Home")
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
