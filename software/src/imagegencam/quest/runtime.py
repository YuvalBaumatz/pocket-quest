"""Application navigation and use cases; no GPIO, web server or API keys."""

from enum import StrEnum
from random import Random

from PIL import Image

from .device import Camera, fixture
from .filters import Style
from .input import Action
from .memory import MemoryGame
from .storage import Store


class Screen(StrEnum):
    HOME = "home"
    CAMERA = "camera"
    ALBUM = "album"
    PLAY = "play"
    MEMORY = "memory"
    EXPLORE = "explore"
    REVIEW = "review"


MISSIONS = ("Something yellow", "Something round", "A funny family pose")


class Quest:
    def __init__(self, camera: Camera, store: Store, rng: Random | None = None) -> None:
        self.camera, self.store = camera, store
        self.rng = rng or Random()
        self.screen = Screen.HOME
        self.home_index = 0
        self.style_index = 0
        self.album_index = 0
        self.mission_index = 0
        self.active_mission: int | None = None
        self.original = False
        self.notice = ""
        self.notice_until = 0.0
        self.photos = store.photos()
        self.image = camera.preview()
        self.memory: MemoryGame | None = None
        self.cards: dict[str, Image.Image] = {}
        data = store.load_progress()
        saved_stamps = data.get("stamps", [])
        self.stamps: set[int] = (
            {x for x in saved_stamps if isinstance(x, int)}
            if isinstance(saved_stamps, list)
            else set()
        )
        saved = data.get("memory")
        if saved is not None:
            try:
                self.memory = MemoryGame.restore(saved)
            except ValueError as error:
                store.warnings.append(str(error))

    @property
    def style(self) -> Style:
        return list(Style)[self.style_index]

    def persist(self) -> None:
        self.store.save_progress(self.memory.snapshot() if self.memory else None, self.stamps)

    def message(self, text: str, now: float) -> None:
        self.notice, self.notice_until = text, now + 2.0

    def tick(self, now: float) -> bool:
        changed = False
        if self.notice and now >= self.notice_until:
            self.notice = ""
            changed = True
        if self.memory and self.memory.hide_at is not None and now >= self.memory.hide_at:
            self.memory.tick(now)
            changed = True
        return changed

    def handle(self, action: Action, now: float) -> None:
        try:
            self._handle(action, now)
        except (OSError, ValueError):
            self.message("Could not save / load", now)

    def _handle(self, action: Action, now: float) -> None:
        if action == Action.HOME:
            self.persist()
            self.screen = Screen.HOME
            self.active_mission = None
            return
        if action == Action.BACK:
            self.persist()
            if self.screen == Screen.ALBUM:
                self.screen = Screen.CAMERA
                self.image = self.camera.preview()
            elif self.screen == Screen.MEMORY:
                self.screen = Screen.PLAY
            elif self.screen in (Screen.REVIEW, Screen.CAMERA) and self.active_mission is not None:
                self.screen = Screen.EXPLORE
                self.active_mission = None
            else:
                self.screen = Screen.HOME
            return
        step = -1 if action == Action.LEFT else 1 if action == Action.RIGHT else 0
        if self.screen == Screen.HOME:
            self.home_index = (self.home_index + step) % 3
            if action == Action.CONFIRM:
                self.screen = (Screen.CAMERA, Screen.PLAY, Screen.EXPLORE)[self.home_index]
                if self.screen == Screen.CAMERA:
                    self.image = self.camera.preview()
        elif self.screen == Screen.CAMERA:
            self.style_index = (self.style_index + step) % len(Style)
            if action == Action.CONFIRM:
                photo = self.store.capture(self.camera.capture(), self.style, self.active_mission)
                self.photos.append(photo)
                if self.active_mission is not None:
                    self.image = self.store.image(photo.id)
                    self.screen = Screen.REVIEW
                else:
                    self.image = self.camera.preview()
                    self.message("Photo saved!", now)
            elif action == Action.DOWN:
                self.screen, self.album_index, self.original = (
                    Screen.ALBUM,
                    max(0, len(self.photos) - 1),
                    False,
                )
                self.load_album()
        elif self.screen == Screen.ALBUM and self.photos:
            self.album_index = (self.album_index + step) % len(self.photos)
            if action == Action.CONFIRM:
                self.original = not self.original
            self.load_album()
        elif self.screen == Screen.PLAY and action == Action.CONFIRM:
            if self.memory is None or self.memory.complete:
                self.memory = MemoryGame.create([p.id for p in self.photos[-3:]], self.rng)
            self.cards = {}
            for card in set(self.memory.deck):
                try:
                    picture = (
                        fixture(int(card.split(":")[1]))
                        if card.startswith("fixture:")
                        else self.store.image(card, True)
                    )
                except (OSError, ValueError, IndexError):
                    picture = fixture(0)
                self.cards[card] = picture.resize((64, 64))
            self.screen = Screen.MEMORY
        elif self.screen == Screen.MEMORY and self.memory:
            if self.memory.complete and action == Action.CONFIRM:
                self.screen = Screen.PLAY
            else:
                self.memory.handle(action, now)
                self.persist()
        elif self.screen == Screen.EXPLORE:
            self.mission_index = (self.mission_index + step) % len(MISSIONS)
            if action == Action.CONFIRM:
                self.active_mission = self.mission_index
                self.image = self.camera.preview()
                self.screen = Screen.CAMERA
        elif self.screen == Screen.REVIEW and action == Action.CONFIRM:
            if self.active_mission is not None:
                # Idempotent local parent approval; not a security boundary.
                candidate = self.stamps | {self.active_mission}
                self.store.save_progress(self.memory.snapshot() if self.memory else None, candidate)
                self.stamps = candidate
                self.active_mission = None
                self.screen = Screen.EXPLORE
                self.message("Stamp earned!", now)

    def load_album(self) -> None:
        if self.photos:
            self.image = self.store.image(self.photos[self.album_index].id, self.original)
