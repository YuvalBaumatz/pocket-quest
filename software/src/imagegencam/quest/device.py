"""Small ports. Importing this module never initializes GPIO or a camera."""

from pathlib import Path
from typing import Any, Protocol

from PIL import Image, ImageDraw


class Camera(Protocol):
    def preview(self) -> Image.Image: ...

    def capture(self) -> Image.Image: ...

    def close(self) -> None: ...


class Display(Protocol):
    def present(self, frame: Image.Image) -> None: ...


def fixture(index: int) -> Image.Image:
    """Original procedural travel illustrations: no downloads or private photos."""
    image = Image.new("RGB", (320, 240), "#A8E6BD")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 145, 320, 240), fill="#19766F")
    draw.ellipse((236, 22, 278, 64), fill="#F5BD4F")
    if index % 3 == 0:
        draw.polygon([(40, 160), (130, 55), (220, 160)], fill="#FFF2D3")
        draw.polygon([(132, 160), (205, 85), (280, 160)], fill="#E77A65")
    elif index % 3 == 1:
        draw.rectangle((149, 72, 165, 190), fill="#182840")
        for points in (
            [(157, 83), (80, 50), (50, 95)],
            [(157, 83), (195, 28), (254, 68)],
            [(157, 83), (231, 100), (260, 132)],
        ):
            draw.polygon(points, fill="#19766F")
        draw.ellipse((131, 83, 159, 109), fill="#F5BD4F")
    else:
        draw.polygon([(75, 155), (245, 155), (211, 192), (106, 192)], fill="#E77A65")
        draw.rectangle((157, 40, 163, 155), fill="#182840")
        draw.polygon([(168, 46), (168, 140), (231, 140)], fill="#FFF2D3")
    return image


class FixtureCamera:
    def __init__(self) -> None:
        self.index = 0

    def preview(self) -> Image.Image:
        return fixture(self.index)

    def capture(self) -> Image.Image:
        image = self.preview()
        self.index += 1
        return image

    def close(self) -> None:
        pass


class FileCamera:
    """Use a supplied photo for the desktop workflow; never overwrite its source."""

    def __init__(self, path: "Path") -> None:
        with Image.open(path) as image:
            self.image = image.convert("RGB")

    def preview(self) -> Image.Image:
        return self.image.copy()

    def capture(self) -> Image.Image:
        return self.image.copy()

    def close(self) -> None:
        pass


class PiCamera:
    """Lazy Picamera2 adapter; all methods are called on the capture worker thread."""

    def __init__(self) -> None:
        self.camera: Any = None
        self.still_config: Any = None

    def _start(self) -> None:
        if self.camera is not None:
            return
        from picamera2 import Picamera2

        camera = Picamera2()
        try:
            preview = camera.create_preview_configuration(main={"size": (320, 240)})
            self.still_config = camera.create_still_configuration()
            camera.configure(preview)
            camera.start()
        except Exception:
            camera.close()
            raise
        self.camera = camera

    def preview(self) -> Image.Image:
        self._start()
        return self.camera.capture_image("main").convert("RGB")

    def capture(self) -> Image.Image:
        self._start()
        return self.camera.switch_mode_and_capture_image(self.still_config, "main").convert("RGB")

    def close(self) -> None:
        if self.camera is not None:
            try:
                self.camera.stop()
            finally:
                self.camera.close()
                self.camera = None
