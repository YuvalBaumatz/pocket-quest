"""240×240 Pillow renderer shared by the desktop and future LCD adapter."""

from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .copy_pip import DIRECTIONS, Phase
from .jobs import JobState
from .missions import MISSIONS as MISSION_CARDS
from .photo_guess import LEVELS
from .runtime import MISSIONS, Quest, Screen

INK = "#182840"
CREAM = "#FFF2D3"
TEAL = "#19766F"
MINT = "#A8E6BD"
GOLD = "#F5BD4F"
CORAL = "#E77A65"


@lru_cache(maxsize=8)
def pairing_qr(url: str) -> Image.Image:
    import qrcode

    return qrcode.make(url, box_size=3, border=4).convert("RGB")


def mission_icon(symbol: str) -> Image.Image:
    icon = Image.new("RGB", (64, 64), TEAL)
    pen = ImageDraw.Draw(icon)
    if symbol in ("sun", "circle", "tiny"):
        inset = 25 if symbol == "tiny" else 12
        pen.ellipse((inset, inset, 64 - inset, 64 - inset), fill=GOLD, outline=CREAM, width=2)
    elif symbol == "leaf":
        pen.polygon(((12, 49), (15, 22), (47, 10), (52, 37), (32, 52)), fill=MINT)
        pen.line((12, 55, 44, 20), fill=INK, width=3)
    elif symbol == "cloud":
        for box in ((7, 25, 34, 49), (20, 14, 49, 46), (36, 27, 58, 49)):
            pen.ellipse(box, fill=CREAM)
        pen.rectangle((18, 33, 47, 49), fill=CREAM)
    elif symbol == "shadow":
        pen.ellipse((25, 40, 59, 53), fill=INK)
        pen.ellipse((14, 9, 30, 25), fill=GOLD)
        pen.rectangle((18, 25, 27, 49), fill=GOLD)
    elif symbol == "reflection":
        pen.polygon(((10, 27), (28, 8), (43, 27)), fill=GOLD)
        pen.polygon(((10, 37), (28, 56), (43, 37)), fill=MINT)
        pen.line((5, 32, 58, 32), fill=CREAM, width=3)
    elif symbol == "colors":
        pen.rectangle((8, 11, 31, 36), fill=CORAL)
        pen.rectangle((34, 28, 57, 53), fill=CORAL)
    elif symbol == "wheels":
        pen.rectangle((7, 24, 57, 43), fill=GOLD)
        pen.rectangle((18, 13, 46, 32), fill=GOLD)
        for x in (12, 40):
            pen.ellipse((x, 36, x + 13, 50), fill=INK, outline=CREAM, width=2)
    elif symbol == "snack":
        pen.polygon(((12, 12), (55, 20), (26, 55)), fill=GOLD, outline=CREAM)
        for x, y in ((22, 20), (37, 25), (27, 37)):
            pen.ellipse((x, y, x + 6, y + 6), fill=CORAL)
    elif symbol == "place":
        pen.rectangle((15, 29, 49, 54), fill=CREAM)
        pen.polygon(((7, 29), (32, 7), (57, 29)), fill=CORAL)
        pen.rectangle((27, 37, 37, 54), fill=INK)
    else:
        pip(pen, 17, 14, 3)
    return icon


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
        centered(draw, 175, "^ Grown-ups", 12)
    elif app.screen == Screen.PARENT:
        centered(draw, 30, "GROWN-UPS", 22)
        options = (
            "Magic: not configured"
            if app.provider == "none"
            else "Online magic: " + ("paused" if app.generation.offline else "on"),
            "Choose outing missions",
            "Photos in games",
            "Exporting..." if app.export_busy else "Export all photos",
            "Pair phone",
        )
        for index, title in enumerate(options):
            y = 58 + 25 * index
            if index == app.parent_index:
                draw.rectangle((8, y - 3, 232, y + 23), fill=TEAL)
            centered(draw, y, title, 16, CREAM if index == app.parent_index else INK)
        centered(draw, 188, "Pause stops new API sends", 12)
        footer = "A SELECT"
    elif app.screen == Screen.PAIR:
        centered(draw, 28, "PAIR PHONE", 21)
        if app.parent_bridge.url:
            qr = pairing_qr(app.parent_bridge.url)
            # Keep QR modules intact; real LCD readability still needs a device test.
            qr.thumbnail((126, 126), Image.Resampling.NEAREST)
            image.paste(qr, ((240 - qr.width) // 2, 52))
            centered(draw, 180, app.parent_bridge.code or "Paired", 19)
            footer = "A NEW CODE"
        else:
            centered(draw, 85, "Companion is off", 20)
            centered(draw, 122, "Start with --companion", 15)
            footer = ""
    elif app.screen == Screen.OUTING:
        centered(draw, 28, "PICK UP TO THREE", 19)
        for index, mission in enumerate(MISSION_CARDS):
            x, y = 39 + index % 3 * 76, 55 + index // 3 * 33
            image.paste(
                mission_icon(mission.symbol).resize((28, 28), Image.Resampling.NEAREST), (x, y)
            )
            if index in app.preferences.outing:
                label(draw, x + 28, y + 5, "*", 18, TEAL)
            if index == app.outing_cursor:
                draw.rectangle((x - 3, y - 2, x + 31, y + 30), outline=GOLD, width=3)
        centered(draw, 189, MISSIONS[app.outing_cursor], 14)
        footer = "A TOGGLE"
    elif app.screen == Screen.ELIGIBILITY:
        centered(draw, 29, "PHOTOS IN GAMES", 19)
        if app.photos:
            image.paste(ImageOps.fit(app.image, (216, 112)), (12, 57))
            photo = app.photos[app.eligibility_index]
            included = photo.id not in app.preferences.excluded_photos
            centered(
                draw,
                180,
                f"< {app.eligibility_index + 1}/{len(app.photos)} >  "
                + ("Included" if included else "Excluded"),
                16,
            )
            footer = "A EXCLUDE" if included else "A INCLUDE"
        else:
            centered(draw, 110, "No photos yet", 20)
            footer = ""
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
        centered(draw, 37, ("PHOTO MEMORY", "COPY PIP", "PHOTO GUESS")[app.play_index], 22)
        pip(draw, 85, 79, 7)
        centered(
            draw,
            160,
            ("Find the matching pairs", "Watch, then copy", "Guess the picture")[app.play_index],
            17,
        )
        centered(draw, 185, f"<   {app.play_index + 1} / 3   >", 16)
        footer = "A PLAY"
    elif app.screen == Screen.COPY_PIP and app.copy_pip:
        game = app.copy_pip
        if game.phase == Phase.COMPLETE:
            pip(draw, 85, 55, 7)
            centered(draw, 140, "YOU DID IT!", 24)
            centered(draw, 174, "Five in a row", 18)
            footer = "A DONE"
        else:
            heading = {
                Phase.WATCH: "WATCH PIP",
                Phase.INPUT: "YOUR TURN",
                Phase.AGAIN: "LET'S TRY AGAIN",
                Phase.SUCCESS: "NICE COPYING!",
            }[game.phase]
            centered(draw, 30, heading, 20)
            centers = ((120, 82), (178, 130), (120, 178), (62, 130))
            colors = (TEAL, CORAL, GOLD, MINT)
            points = ((0, -16), (16, 0), (7, 0), (7, 15), (-7, 15), (-7, 0), (-16, 0))
            for i, (direction, (cx, cy), color) in enumerate(
                zip(DIRECTIONS, centers, colors, strict=True)
            ):
                selected = direction == game.lit
                draw.rectangle(
                    (cx - 23, cy - 22, cx + 23, cy + 22),
                    fill=color if selected else INK,
                    outline=INK if selected else color,
                    width=3,
                )
                rotated = []
                for x, y in points:
                    for _ in range(i):
                        x, y = -y, x
                    rotated.append((cx + x, cy + y))
                draw.polygon(rotated, fill=INK if selected else CREAM)
            centered(draw, 119, str(len(game.sequence)), 20)
            footer = "A REPLAY" if game.phase == Phase.INPUT else "WATCH"
    elif app.screen == Screen.GUESS and app.guess:
        centered(draw, 29, "WHO KNOWS?", 21)
        level = LEVELS[app.guess.level]
        picture = ImageOps.fit(app.guess_image, (216, 140))
        if level < 240:
            picture = picture.resize(
                (level, max(1, round(level * 140 / 216))), Image.Resampling.BOX
            )
            picture = picture.resize((216, 140), Image.Resampling.NEAREST)
        image.paste(picture, (12, 55))
        footer = "A NEXT" if app.guess.level == 4 else "A REVEAL"
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
        image.paste(
            mission_icon(MISSION_CARDS[app.mission_index].symbol).resize(
                (88, 88), Image.Resampling.NEAREST
            ),
            (76, 39),
        )
        centered(draw, 138, MISSIONS[app.mission_index], 18)
        centered(
            draw,
            164,
            f"< {app.mission_index + 1}/{len(MISSIONS)} >   Stamps {len(app.stamps)}/{len(MISSIONS)}",
            16,
        )
        centered(draw, 187, "v Passport    ^ Review", 12)
        footer = "A CAMERA"
    elif app.screen == Screen.PASSPORT:
        footer = ""
        centered(draw, 29, "MY PASSPORT", 22)
        for slot in range(6):
            index = app.passport_page * 6 + slot
            if index >= len(MISSIONS):
                break
            x, y = 17 + slot % 3 * 74, 62 + slot // 3 * 67
            icon = mission_icon(MISSION_CARDS[index].symbol).resize(
                (48, 48), Image.Resampling.NEAREST
            )
            if index not in app.stamps:
                icon = ImageOps.grayscale(icon).convert("RGB")
            image.paste(icon, (x, y))
            draw.rectangle(
                (x - 2, y - 2, x + 49, y + 49),
                outline=GOLD if index in app.stamps else INK,
                width=2,
            )
            label(draw, x + 16, y + 48, str(index + 1), 12)
            if index in app.stamps:
                label(draw, x + 35, y + 1, "*", 18, GOLD)
        centered(draw, 190, f"<  Page {app.passport_page + 1}/2  >", 14)
    if app.notice:
        draw.rectangle((8, 172, 232, 204), fill=INK)
        centered(draw, 181, app.notice, 16, CREAM)
    draw.rectangle((0, 208, 239, 239), fill=INK)
    label(draw, 12, 218, "B BACK", 12, CREAM)
    label(draw, 153, 218, footer, 12, CREAM)
    return image
