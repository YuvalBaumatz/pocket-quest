"""240×240 Pillow renderer shared by the desktop and future LCD adapter."""

from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .jobs import JobState
from .runtime import MISSIONS, Quest, Screen

INK = "#182840"
CREAM = "#FFF2D3"
TEAL = "#19766F"
MINT = "#A8E6BD"
GOLD = "#F5BD4F"
CORAL = "#E77A65"


@lru_cache(maxsize=8)
def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # Pillow's bundled font avoids system-font and download dependencies.
    return ImageFont.load_default(size=size)


def label(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    size: int = 16,
    color: str = INK,
) -> None:
    draw.text((x, y), text, font=font(size), fill=color)


def centered(
    draw: ImageDraw.ImageDraw, y: int, text: str, size: int = 20, color: str = INK
) -> None:
    width = draw.textlength(text, font=font(size))
    label(draw, int((240 - width) / 2), y, text, size, color)


def pip(draw: ImageDraw.ImageDraw, x: int, y: int, scale: int = 5) -> None:
    sprite = (
        "  xx  xx  ",
        "  xxxxxx  ",
        "  xoxxox  ",
        "  xxxxxx  ",
        "    xx    ",
        " xxxxxxxx ",
        "xx xxxx xx",
        "   xxxx   ",
        "  xx  xx  ",
    )
    for row, line in enumerate(sprite):
        for col, pixel in enumerate(line):
            if pixel != " ":
                left, top = x + col * scale, y + row * scale
                draw.rectangle(
                    (left, top, left + scale - 1, top + scale - 1),
                    fill=INK if pixel == "o" else MINT,
                )


def camera_icon(draw: ImageDraw.ImageDraw) -> None:
    draw.rectangle((78, 77, 162, 132), fill=CREAM)
    draw.rectangle((90, 67, 115, 77), fill=GOLD)
    draw.rectangle((104, 89, 137, 121), fill=INK)
    draw.rectangle((112, 97, 129, 114), fill=TEAL)


def render(app: Quest) -> Image.Image:
    image = Image.new("RGB", (240, 240), CREAM)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 239, 23), fill=INK)
    label(draw, 10, 5, "POCKET QUEST", 12, CREAM)
    label(
        draw,
        186,
        5,
        "DEMO"
        if app.provider == "demo"
        else "LOCAL"
        if app.provider == "none"
        else "PAUSE"
        if app.generation.offline
        else "MAGIC",
        12,
        MINT,
    )
    footer = "A OPEN"
    if app.screen == Screen.HOME:
        draw.rectangle((20, 36, 219, 188), fill=TEAL)
        draw.rectangle((24, 40, 215, 184), outline=GOLD, width=2)
        if app.home_index == 0:
            camera_icon(draw)
        elif app.home_index == 1:
            for x, y in ((85, 72), (124, 72), (85, 111), (124, 111)):
                draw.rectangle((x, y, x + 30, y + 30), fill=GOLD)
        else:
            pip(draw, 85, 66, 7)
        centered(draw, 152, ("CAMERA", "PLAY", "EXPLORE")[app.home_index], 24, CREAM)
        label(draw, 32, 99, "<", 22, GOLD)
        label(draw, 194, 99, ">", 22, GOLD)
        for i in range(3):
            draw.rectangle(
                (103 + 14 * i, 197, 109 + 14 * i, 201),
                fill=TEAL if i == app.home_index else GOLD,
            )
    elif app.screen in (Screen.CAMERA, Screen.ALBUM, Screen.REVIEW):
        if app.screen != Screen.ALBUM or app.photos:
            image.paste(ImageOps.fit(app.image, (216, 168)), (12, 32))
            draw.rectangle((12, 32, 228, 56), fill=INK)
            title = (
                ("* " if app.style.is_ai else "") + app.style.value
                if app.screen == Screen.CAMERA
                else "ORIGINAL"
                if app.original
                else "PHOTO"
            )
            if app.screen == Screen.ALBUM:
                album_job = next(
                    (job for job in app.job_items if job.id == app.photos[app.album_index].id), None
                )
                if album_job:
                    if album_job.state != JobState.SUCCEEDED:
                        title = "ORIGINAL"
                    elif not app.original:
                        title = "DEMO RESULT" if album_job.provider == "demo" else "MAGIC"
                    draw.rectangle((12, 175, 228, 200), fill=INK)
                    centered(
                        draw,
                        180,
                        "Magic ready"
                        if album_job.state == JobState.SUCCEEDED
                        else "Magic: check queue",
                        15,
                        CREAM,
                    )
                title += f" {app.album_index + 1}/{len(app.photos)}"
            if app.screen == Screen.REVIEW:
                title = "GROWN-UP CHECK"
            label(draw, 18, 36, title, 16, CREAM)
        else:
            pip(draw, 80, 63, 8)
            centered(draw, 155, "Take your first photo", 18)
        footer = "A SNAP" if app.screen == Screen.CAMERA else "A SWAP"
        if app.screen == Screen.CAMERA:
            draw.rectangle((12, 172, 228, 200), fill=INK)
            label(draw, 20, 174, "< STYLE >   v ALBUM", 12, CREAM)
            label(draw, 20, 188, "^ MAGIC QUEUE", 12, MINT)
            if app.camera_error:
                centered(draw, 100, app.camera_error, 18, CREAM)
            footer = "SAVING" if app.capturing else "A SNAP"
        elif app.screen == Screen.REVIEW:
            draw.rectangle((12, 168, 228, 200), fill=INK)
            centered(draw, 175, "Mission complete?", 17, CREAM)
            footer = "A YES"
    elif app.screen in (Screen.QUEUE, Screen.APPROVE, Screen.CANCEL):
        job = app.current_job
        if not job:
            pip(draw, 85, 60, 7)
            centered(draw, 146, "No magic waiting", 20)
            centered(draw, 176, "Try a * camera style", 16)
            footer = ""
        elif app.screen == Screen.QUEUE:
            centered(draw, 34, "MAGIC QUEUE", 22)
            centered(draw, 64, job.style, 20)
            centered(draw, 92, job.provider.upper(), 16)
            labels = {
                JobState.AWAITING: "Ask a grown-up",
                JobState.READY: "Ready to make",
                JobState.RUNNING: "Making magic...",
                JobState.RETRY: "Waiting to retry",
                JobState.UNKNOWN: "Needs review",
                JobState.FAILED: "Could not make magic",
                JobState.SUCCEEDED: "Ready in your album",
                JobState.CANCELLED: "Cancelled",
            }
            centered(
                draw,
                118,
                "Paused (offline)"
                if app.generation.offline and job.state in (JobState.READY, JobState.RETRY)
                else "Provider not enabled"
                if job.provider not in app.generation.providers
                and job.state in (JobState.READY, JobState.RETRY)
                else "Daily limit reached"
                if app.jobs.budget_blocked and job.state in (JobState.READY, JobState.RETRY)
                else "Retry limit reached"
                if job.attempts >= 3 and job.state in (JobState.FAILED, JobState.UNKNOWN)
                else labels[job.state],
                17,
            )
            if job.error:
                errors = {
                    "credentials": "Check API key",
                    "rate_limit": "Provider is busy",
                    "install_openai": "Install OpenAI package",
                    "request_rejected": "Check model / request",
                    "no_image": "No image returned",
                }
                centered(draw, 143, errors.get(job.error, "Original is still safe"), 15)
            centered(draw, 169, f"< {app.queue_index + 1}/{len(app.job_items)} >", 16)
            if job.state not in (JobState.SUCCEEDED, JobState.CANCELLED):
                centered(draw, 189, "v Cancel request", 12)
            footer = (
                "A VIEW"
                if job.state == JobState.SUCCEEDED
                else "A REVIEW"
                if job.state in (JobState.AWAITING, JobState.FAILED, JobState.UNKNOWN)
                and job.attempts < 3
                else ""
            )
        elif app.screen == Screen.APPROVE:
            centered(draw, 38, "GROWN-UP CHECK", 22)
            centered(draw, 74, "Send photo to", 18)
            centered(draw, 101, job.provider.upper(), 22)
            centered(
                draw,
                135,
                "Local demo, no charge" if job.provider == "demo" else "Uses API credits",
                17,
            )
            centered(
                draw, 165, "Retry may charge again" if job.attempts else "Original stays saved", 16
            )
            footer = "A SEND"
        else:
            centered(draw, 48, "CANCEL MAGIC?", 22)
            centered(draw, 91, "Original stays saved", 18)
            centered(draw, 127, "A running request", 17)
            centered(draw, 151, "may still be charged", 17)
            footer = "A CANCEL"
    elif app.screen == Screen.PLAY:
        centered(draw, 37, "PHOTO MEMORY", 22)
        pip(draw, 85, 79, 7)
        centered(draw, 160, "Find the matching pairs", 17)
        footer = "A PLAY"
    elif app.screen == Screen.MEMORY and app.memory:
        if app.memory.complete:
            pip(draw, 85, 52, 7)
            centered(draw, 133, "YOU FOUND THEM!", 21)
            centered(draw, 169, "Play together again", 17)
            footer = "A DONE"
        else:
            for i, card in enumerate(app.memory.deck):
                x, y = 16 + (i % 3) * 72, 44 + (i // 3) * 72
                draw.rectangle((x, y, x + 63, y + 63), fill=TEAL)
                if i in app.memory.matched or i in app.memory.exposed:
                    image.paste(app.cards[card], (x, y))
                else:
                    label(draw, x + 23, y + 15, "?", 30, CREAM)
                if i == app.memory.cursor:
                    draw.rectangle((x - 3, y - 3, x + 66, y + 66), outline=INK, width=3)
                    draw.rectangle((x, y, x + 63, y + 63), outline=GOLD, width=3)
            footer = "A FLIP"
    elif app.screen == Screen.EXPLORE:
        draw.rectangle((18, 34, 222, 133), fill=TEAL)
        if app.mission_index == 0:
            draw.ellipse((91, 54, 149, 112), fill=GOLD)
        elif app.mission_index == 1:
            draw.ellipse((91, 54, 149, 112), fill=CORAL, outline=CREAM, width=3)
        else:
            pip(draw, 85, 52, 7)
        centered(draw, 143, MISSIONS[app.mission_index], 18)
        centered(
            draw,
            173,
            f"<  {app.mission_index + 1}/3  >    Stamps {len(app.stamps)}/3",
            16,
        )
        footer = "A CAMERA"
    if app.notice:
        draw.rectangle((8, 172, 232, 204), fill=INK)
        centered(draw, 181, app.notice, 16, CREAM)
    draw.rectangle((0, 208, 239, 239), fill=INK)
    label(draw, 12, 218, "B BACK", 12, CREAM)
    label(draw, 153, 218, footer, 12, CREAM)
    return image
