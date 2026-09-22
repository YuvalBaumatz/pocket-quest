"""Local effects return derivatives and never mutate a source image."""

from enum import StrEnum

from PIL import Image, ImageOps


class Style(StrEnum):
    ORIGINAL = "Original"
    PIXELS = "Pocket pixels"
    MONO = "Mono"


def apply_style(source: Image.Image, style: Style) -> Image.Image:
    image = source.convert("RGB")
    if style == Style.MONO:
        return ImageOps.grayscale(image).convert("RGB")
    if style == Style.PIXELS:
        small = image.resize((24, 24), Image.Resampling.BOX)
        return small.quantize(colors=8).convert("RGB").resize(image.size, Image.Resampling.NEAREST)
    return image.copy()
