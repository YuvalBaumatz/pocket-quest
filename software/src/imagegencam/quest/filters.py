"""Local effects return derivatives and never mutate a source image."""

from enum import StrEnum

from PIL import Image, ImageEnhance, ImageOps


class Style(StrEnum):
    ORIGINAL = "Original"
    PIXELS = "Pocket pixels"
    MONO = "Mono"
    CLAY = "Clay crew"
    OCEAN = "Ocean explorers"
    ROBOT = "Friendly robot"

    @property
    def is_ai(self) -> bool:
        return self in (Style.CLAY, Style.OCEAN, Style.ROBOT)

    @property
    def prompt(self) -> str:
        prompts = {
            Style.CLAY: "Turn this photo into a cheerful handmade clay scene.",
            Style.OCEAN: "Turn the people in this photo into friendly underwater explorers in a colorful coral world.",
            Style.ROBOT: "Turn the main subjects into friendly toy robots in a playful illustrated world.",
        }
        if self not in prompts:
            return ""
        return (
            prompts[self]
            + " Keep the subjects recognizable and the composition similar. Family-friendly, no text or frightening details."
        )


def apply_style(source: Image.Image, style: Style) -> Image.Image:
    image = source.convert("RGB")
    if style == Style.MONO:
        return ImageOps.grayscale(image).convert("RGB")
    if style == Style.PIXELS:
        # Keep faces legible on the handheld and pixels square on wide photos.
        scale = min(1.0, 64 / min(image.size))
        size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
        small = image.resize(size, Image.Resampling.BOX)
        small = ImageEnhance.Color(small).enhance(1.1)
        small = ImageEnhance.Contrast(small).enhance(1.06)
        return (
            small.quantize(colors=32, dither=Image.Dither.NONE)
            .convert("RGB")
            .resize(image.size, Image.Resampling.NEAREST)
        )
    return image.copy()
