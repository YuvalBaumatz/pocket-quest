"""Application navigation and use cases; no GPIO, web server or API keys."""

import sqlite3
from enum import StrEnum
from queue import Empty
from random import Random

from PIL import Image

from .device import Camera, fixture
from .filters import Style
from .input import Action
from .jobs import Job, JobQueue, JobState
from .memory import MemoryGame
from .providers import Provider, provider_for
from .storage import Store
from .workers import CaptureWorker, GenerationWorker


class Screen(StrEnum):
    HOME = "home"
    CAMERA = "camera"
    ALBUM = "album"
    PLAY = "play"
    MEMORY = "memory"
    EXPLORE = "explore"
    REVIEW = "review"
    QUEUE = "queue"
    APPROVE = "approve"
    CANCEL = "cancel"


MISSIONS = ("Something yellow", "Something round", "A funny family pose")


class Quest:
    def __init__(
        self,
        camera: Camera,
        store: Store,
        rng: Random | None = None,
        *,
        provider: str = "demo",
        model: str = "demo-v1",
        offline: bool = False,
        providers: dict[str, Provider] | None = None,
        start_generation: bool = True,
    ) -> None:
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
        self.image = fixture(0)
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

        self.provider, self.model = provider, model
        resolved_providers = (
            providers if providers is not None else {provider: provider_for(provider)}
        )
        self.jobs = JobQueue(store.root)
        self.job_items = self.jobs.all()
        self.queue_index = 0
        self.capturing = False
        self.preview_version = -1
        self.camera_error = ""
        self.closed = False
        self.capture_worker = CaptureWorker(camera, store, self.jobs, provider, model)
        self.generation = GenerationWorker(self.jobs, store, resolved_providers, offline=offline)
        if start_generation:
            self.generation.start()

    @property
    def current_job(self) -> Job | None:
        return self.job_items[self.queue_index % len(self.job_items)] if self.job_items else None

    def refresh_jobs(self) -> None:
        selected = self.current_job.id if self.current_job else None
        self.job_items = self.jobs.all()
        self.queue_index = next(
            (i for i, item in enumerate(self.job_items) if item.id == selected), 0
        )

    def close(self) -> None:
        if not self.closed:
            self.capture_worker.close()
            self.generation.close()
            self.closed = True

    @property
    def style(self) -> Style:
        return list(Style)[self.style_index]

    def persist(self) -> None:
        self.store.save_progress(self.memory.snapshot() if self.memory else None, self.stamps)

    def message(self, text: str, now: float) -> None:
        self.notice, self.notice_until = text, now + 2.0

    def tick(self, now: float) -> bool:
        try:
            return self._tick(now)
        except (OSError, ValueError, sqlite3.Error):
            self.message("Could not save / load", now)
            return True

    def _tick(self, now: float) -> bool:
        changed = False
        if self.screen == Screen.CAMERA:
            self.capture_worker.preview_enabled.set()
            frame, version, error = self.capture_worker.preview()
            if version != self.preview_version and frame is not None:
                self.image, self.preview_version = frame, version
                changed = True
            if error != self.camera_error:
                self.camera_error = error
                changed = True
        else:
            self.capture_worker.preview_enabled.clear()
        try:
            result = self.capture_worker.results.get_nowait()
        except Empty:
            pass
        else:
            self.capturing = False
            if result.photo:
                self.photos.append(result.photo)
                if (
                    self.screen == Screen.CAMERA
                    and self.active_mission == result.photo.mission
                    and result.photo.mission is not None
                ):
                    self.image = self.store.image(result.photo.id)
                    self.screen = Screen.REVIEW
            self.refresh_jobs()
            self.message(result.message, now)
            changed = True
        if self.generation.changed.is_set():
            self.generation.changed.clear()
            self.refresh_jobs()
            if self.screen == Screen.ALBUM:
                self.load_album()
            if self.generation.error:
                self.message(self.generation.error, now)
            changed = True
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
        except (OSError, ValueError, sqlite3.Error):
            self.message("Could not save / load", now)

    def _handle(self, action: Action, now: float) -> None:
        if action == Action.HOME:
            self.persist()
            self.screen = Screen.HOME
            self.active_mission = None
            return
        if action == Action.BACK:
            self.persist()
            if self.screen in (Screen.APPROVE, Screen.CANCEL):
                self.screen = Screen.QUEUE
            elif self.screen == Screen.QUEUE:
                self.screen = Screen.CAMERA
            elif self.screen == Screen.ALBUM:
                self.screen = Screen.CAMERA
                self.capture_worker.preview_enabled.set()
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
                    self.capture_worker.preview_enabled.set()
        elif self.screen == Screen.CAMERA:
            self.style_index = (self.style_index + step) % len(Style)
            if action == Action.CONFIRM:
                if not self.capturing:
                    self.capture_worker.requests.put_nowait((self.style, self.active_mission))
                    self.capturing = True
                    self.message("Saving photo...", now)
            elif action == Action.UP:
                self.refresh_jobs()
                self.screen = Screen.QUEUE
            elif action == Action.DOWN:
                self.screen, self.album_index, self.original = (
                    Screen.ALBUM,
                    max(0, len(self.photos) - 1),
                    False,
                )
                self.load_album()
        elif self.screen == Screen.QUEUE:
            if self.job_items:
                self.queue_index = (self.queue_index + step) % len(self.job_items)
                if (
                    action == Action.CONFIRM
                    and self.current_job
                    and self.current_job.state
                    in (JobState.AWAITING, JobState.UNKNOWN, JobState.FAILED)
                    and self.current_job.attempts < 3
                ):
                    self.screen = Screen.APPROVE
                elif (
                    action == Action.DOWN
                    and self.current_job
                    and self.current_job.state not in (JobState.SUCCEEDED, JobState.CANCELLED)
                ):
                    self.screen = Screen.CANCEL
        elif self.screen == Screen.APPROVE and action == Action.CONFIRM:
            if self.current_job:
                self.jobs.approve(self.current_job.id)
                self.refresh_jobs()
            self.screen = Screen.QUEUE
        elif self.screen == Screen.CANCEL and action == Action.CONFIRM:
            if self.current_job:
                self.jobs.cancel(self.current_job.id)
                self.refresh_jobs()
            self.screen = Screen.QUEUE
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
                self.capture_worker.preview_enabled.set()
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
