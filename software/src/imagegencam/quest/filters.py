"""Local effects return derivatives and never mutate a source image."""

from enum import StrEnum

from PIL import Image, ImageOps


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
        small = image.resize((24, 24), Image.Resampling.BOX)
        return small.quantize(colors=8).convert("RGB").resize(image.size, Image.Resampling.NEAREST)
    return image.copy()
