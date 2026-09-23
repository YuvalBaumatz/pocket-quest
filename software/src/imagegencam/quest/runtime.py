"""Application navigation and use cases; no GPIO, web server or API keys."""

import sqlite3
from dataclasses import replace
from enum import StrEnum
from pathlib import Path
from queue import Empty
from random import Random

from PIL import Image

from .companion import ParentBridge
from .copy_pip import CopyPip, Phase
from .device import Camera, FixtureCamera, fixture
from .filters import Style, apply_style
from .input import Action
from .jobs import Job, JobQueue, JobState
from .memory import MemoryGame
from .missions import MISSIONS as MISSION_CARDS
from .photo_guess import PhotoGuess
from .preferences import Preferences
from .providers import Provider, provider_for
from .storage import Store
from .workers import CaptureWorker, ExportWorker, GenerationWorker


class Screen(StrEnum):
    HOME = "home"
    CAMERA = "camera"
    ALBUM = "album"
    PLAY = "play"
    MEMORY = "memory"
    COPY_PIP = "copy_pip"
    GUESS = "guess"
    PASSPORT = "passport"
    PARENT = "parent"
    OUTING = "outing"
    ELIGIBILITY = "eligibility"
    PAIR = "pair"
    EXPLORE = "explore"
    REVIEW = "review"
    QUEUE = "queue"
    APPROVE = "approve"
    CANCEL = "cancel"


MISSIONS = tuple(m.title for m in MISSION_CARDS)


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
        self.play_index = 0
        self.parent_index = 0
        self.outing_cursor = 0
        self.eligibility_index = 0
        self.export_busy = False
        self.export_path: Path | None = None
        self.games_paused = False
        self.parent_bridge = ParentBridge()
        preferences_unreadable = False
        try:
            self.preferences = Preferences.load(store.root)
        except (OSError, ValueError):
            self.preferences = Preferences(offline=True)
            preferences_unreadable = True
            store.warnings.append("Parent settings unreadable; online magic paused")
        self.style_index = 0
        self.album_index = 0
        self.mission_index = self.preferences.outing[0] if self.preferences.outing else 0
        self.passport_page = 0
        self.active_mission: int | None = None
        self.original = False
        self.notice = ""
        self.notice_until = 0.0
        self.photos = store.photos()
        if preferences_unreadable:
            self.preferences.excluded_photos = {p.id for p in self.photos}
        self.image = (
            fixture(0)
            if isinstance(camera, FixtureCamera)
            else Image.new("RGB", (320, 240), "#182840")
        )
        self.memory: MemoryGame | None = None
        self.copy_pip: CopyPip | None = None
        self.guess: PhotoGuess | None = None
        self.guess_image = fixture(0)
        self.guess_unavailable: set[str] = set()
        self.cards: dict[str, Image.Image] = {}
        data = store.load_progress()
        for key, restore in (("copy_pip", CopyPip.restore), ("guess", PhotoGuess.restore)):
            if data.get(key) is not None:
                try:
                    setattr(self, key, restore(data[key]))
                except ValueError as error:
                    store.warnings.append(str(error))
        saved_stamps = data.get("stamps", [])
        self.stamps: set[int] = (
            {x for x in saved_stamps if type(x) is int and 0 <= x < len(MISSIONS)}
            if isinstance(saved_stamps, list)
            else set()
        )
        saved = data.get("memory")
        if saved is not None:
            try:
                self.memory = MemoryGame.restore(saved)
            except ValueError as error:
                store.warnings.append(str(error))
        if self.memory and self.preferences.excluded_photos.intersection(self.memory.deck):
            self.memory = None

        self.provider, self.model = provider, model
        self.styles = [style for style in Style if provider != "none" or not style.is_ai]
        resolved_providers = (
            providers
            if providers is not None
            else {}
            if provider == "none"
            else {provider: provider_for(provider)}
        )
        self.jobs = JobQueue(store.root)
        self.job_items = self.jobs.all()
        self.queue_index = 0
        self.capturing = False
        self.preview_version = -1
        self.camera_error = ""
        self.closed = False
        self.capture_worker = CaptureWorker(camera, store, self.jobs, provider, model)
        self.generation = GenerationWorker(
            self.jobs, store, resolved_providers, offline=offline or self.preferences.offline
        )
        self.export_worker = ExportWorker(store.root)
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
            self.export_worker.close()
            self.closed = True

    @property
    def style(self) -> Style:
        return self.styles[self.style_index]

    def persist(self) -> None:
        self.store.save_progress(
            self.memory.snapshot() if self.memory else None,
            self.stamps,
            self.copy_pip.snapshot() if self.copy_pip else None,
            self.guess.snapshot() if self.guess else None,
        )

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
        if not self.parent_bridge.commands.empty():
            self.parent_bridge.process(self.parent_command)
            changed = True
        if self.screen == Screen.CAMERA:
            self.capture_worker.preview_enabled.set()
            frame, version, error = self.capture_worker.preview()
            if version != self.preview_version and frame is not None:
                self.image = apply_style(frame, self.style)
                self.preview_version = version
                changed = True
            if error != self.camera_error:
                if error:
                    self.image = Image.new("RGB", (320, 240), "#182840")
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
            self.refresh_jobs()
            if result.photo:
                self.photos.append(result.photo)
                if (
                    self.screen == Screen.CAMERA
                    and self.active_mission == result.photo.mission
                    and result.photo.mission is not None
                ):
                    self.image = self.store.image(result.photo.id)
                    self.screen = Screen.REVIEW
                elif (
                    self.screen == Screen.CAMERA
                    and self.active_mission is None
                    and result.photo.mission is None
                ):
                    job_index = next(
                        (i for i, job in enumerate(self.job_items) if job.id == result.photo.id),
                        None,
                    )
                    if job_index is not None:
                        self.queue_index = job_index
                        self.screen = Screen.QUEUE
                    else:
                        self.album_index = len(self.photos) - 1
                        self.original = False
                        self.load_album()
                        self.screen = Screen.ALBUM
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
        if self.screen == Screen.COPY_PIP and self.copy_pip and not self.games_paused:
            changed = self.copy_pip.tick(now) or changed
        try:
            path, message = self.export_worker.results.get_nowait()
        except Empty:
            pass
        else:
            self.export_busy, self.export_path = False, path
            self.message(message, now)
            changed = True
        if self.parent_bridge.url:
            self.publish_parent_state()
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
            elif self.screen in (Screen.MEMORY, Screen.COPY_PIP, Screen.GUESS):
                self.screen = Screen.PLAY
            elif self.screen == Screen.PASSPORT:
                self.screen = Screen.EXPLORE
            elif self.screen in (Screen.OUTING, Screen.ELIGIBILITY, Screen.PAIR):
                self.screen = Screen.PARENT
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
            elif action == Action.UP:
                self.screen = Screen.PARENT
        elif self.screen == Screen.PARENT:
            vertical = -1 if action == Action.UP else 1 if action == Action.DOWN else 0
            self.parent_index = (self.parent_index + vertical + step) % 5
            if action == Action.CONFIRM:
                if self.parent_index == 0:
                    self.set_offline(not self.generation.offline)
                elif self.parent_index == 1:
                    self.screen = Screen.OUTING
                elif self.parent_index == 2:
                    self.screen = Screen.ELIGIBILITY
                    self.load_eligibility()
                elif self.parent_index == 3 and not self.export_busy:
                    self.start_export()
                elif self.parent_index == 4:
                    self.screen = Screen.PAIR
        elif self.screen == Screen.PAIR and action == Action.CONFIRM:
            if self.parent_bridge.rotate:
                self.parent_bridge.rotate()
        elif self.screen == Screen.OUTING:
            vertical = -3 if action == Action.UP else 3 if action == Action.DOWN else 0
            self.outing_cursor = (self.outing_cursor + step + vertical) % len(MISSIONS)
            if action == Action.CONFIRM:
                outing = self.preferences.outing.copy()
                if self.outing_cursor in outing:
                    outing.remove(self.outing_cursor)
                elif len(outing) < 3:
                    outing.append(self.outing_cursor)
                else:
                    self.message("Choose up to three", now)
                    return
                self.set_outing(outing)
        elif self.screen == Screen.ELIGIBILITY and self.photos:
            self.eligibility_index = (self.eligibility_index + step) % len(self.photos)
            photo = self.photos[self.eligibility_index]
            if action == Action.CONFIRM:
                self.set_eligible(photo.id, photo.id in self.preferences.excluded_photos)
            self.load_eligibility()
        elif self.screen == Screen.CAMERA:
            self.style_index = (self.style_index + step) % len(self.styles)
            if step:
                self.preview_version = -1
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
                    and self.current_job.state == JobState.SUCCEEDED
                ):
                    index = next(
                        (
                            i
                            for i, photo in enumerate(self.photos)
                            if photo.id == self.current_job.id
                        ),
                        None,
                    )
                    if index is not None:
                        self.album_index, self.original = index, False
                        self.load_album()
                        self.screen = Screen.ALBUM
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
        elif self.screen == Screen.PLAY:
            self.play_index = (self.play_index + step) % 3
            if action != Action.CONFIRM:
                return
            if self.play_index == 1:
                if self.copy_pip is None or self.copy_pip.phase == Phase.COMPLETE:
                    self.copy_pip = CopyPip.create(self.rng, now)
                else:
                    self.copy_pip.replay(now)
                self.screen = Screen.COPY_PIP
                self.persist()
                return
            if self.play_index == 2:
                if self.guess is None:
                    self.guess = PhotoGuess(self.guess_choices()[0])
                self.load_guess()
                self.screen = Screen.GUESS
                self.persist()
                return
            if self.memory is None or self.memory.complete:
                self.memory = MemoryGame.create(
                    [p.id for p in self.photos if p.id not in self.preferences.excluded_photos][
                        -3:
                    ],
                    self.rng,
                )
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
        elif self.screen == Screen.COPY_PIP and self.copy_pip:
            if self.copy_pip.phase == Phase.COMPLETE and action == Action.CONFIRM:
                self.screen = Screen.PLAY
            else:
                self.copy_pip.handle(action, now, self.rng)
                self.persist()
        elif self.screen == Screen.GUESS and self.guess and action == Action.CONFIRM:
            self.guess.advance(self.guess_choices())
            self.load_guess()
            self.persist()
        elif self.screen == Screen.MEMORY and self.memory:
            if self.memory.complete and action == Action.CONFIRM:
                self.screen = Screen.PLAY
            else:
                self.memory.handle(action, now)
                self.persist()
        elif self.screen == Screen.EXPLORE:
            missions = self.preferences.outing or list(range(len(MISSIONS)))
            if self.mission_index not in missions:
                self.mission_index = missions[0]
            self.mission_index = missions[
                (missions.index(self.mission_index) + step) % len(missions)
            ]
            if action == Action.DOWN:
                self.passport_page = self.mission_index // 6
                self.screen = Screen.PASSPORT
                return
            if action == Action.UP:
                evidence = next(
                    (p for p in reversed(self.photos) if p.mission == self.mission_index), None
                )
                if evidence is not None:
                    self.active_mission = self.mission_index
                    self.image = self.store.image(evidence.id, True)
                    self.screen = Screen.REVIEW
                else:
                    self.message("Take a mission photo", now)
                return
            if action == Action.CONFIRM:
                self.active_mission = self.mission_index
                self.capture_worker.preview_enabled.set()
                self.screen = Screen.CAMERA
        elif self.screen == Screen.PASSPORT:
            self.passport_page = (self.passport_page + step) % ((len(MISSIONS) + 5) // 6)
        elif self.screen == Screen.REVIEW and action == Action.CONFIRM:
            if self.active_mission is not None:
                # Idempotent local parent approval; not a security boundary.
                candidate = self.stamps | {self.active_mission}
                self.store.save_progress(
                    self.memory.snapshot() if self.memory else None,
                    candidate,
                    self.copy_pip.snapshot() if self.copy_pip else None,
                    self.guess.snapshot() if self.guess else None,
                )
                self.stamps = candidate
                self.active_mission = None
                self.screen = Screen.EXPLORE
                self.message("Stamp earned!", now)

    def load_album(self) -> None:
        if self.photos:
            self.image = self.store.image(self.photos[self.album_index].id, self.original)

    def guess_choices(self) -> list[str]:
        return [
            p.id
            for p in self.photos
            if p.id not in self.guess_unavailable and p.id not in self.preferences.excluded_photos
        ] or [f"fixture:{i}" for i in range(3)]

    def load_guess(self) -> None:
        if self.guess is None:
            return
        while True:
            self.guess.reconcile(self.guess_choices())
            try:
                self.guess_image = (
                    fixture(int(self.guess.photo_id.split(":")[1]))
                    if self.guess.photo_id.startswith("fixture:")
                    else self.store.image(self.guess.photo_id, True)
                )
                return
            except (OSError, ValueError):
                self.guess_unavailable.add(self.guess.photo_id)

    def set_offline(self, offline: bool) -> None:
        candidate = replace(self.preferences, offline=offline)
        candidate.save(self.store.root)
        self.preferences = candidate
        self.generation.offline = offline

    def set_outing(self, outing: list[int]) -> None:
        if (
            len(outing) > 3
            or any(type(x) is not int or not 0 <= x < len(MISSIONS) for x in outing)
            or len(set(outing)) != len(outing)
        ):
            raise ValueError("Choose up to three valid missions")
        candidate = replace(self.preferences, outing=outing.copy())
        candidate.save(self.store.root)
        self.preferences = candidate
        self.mission_index = outing[0] if outing else 0

    def set_eligible(self, photo_id: str, eligible: bool) -> None:
        if photo_id not in {p.id for p in self.photos}:
            raise ValueError("Unknown photo")
        excluded = self.preferences.excluded_photos.copy()
        excluded.discard(photo_id) if eligible else excluded.add(photo_id)
        candidate = replace(self.preferences, excluded_photos=excluded)
        candidate.save(self.store.root)
        self.preferences = candidate
        if self.memory and excluded.intersection(self.memory.deck):
            self.memory, self.cards = None, {}
            if self.screen == Screen.MEMORY:
                self.screen = Screen.PLAY
        if self.guess:
            self.load_guess()
        self.persist()

    def load_eligibility(self) -> None:
        if self.photos:
            self.image = self.store.image(self.photos[self.eligibility_index].id, True)

    def start_export(self) -> None:
        if not self.export_busy:
            self.export_busy = True
            self.export_worker.start()

    def publish_parent_state(self) -> None:
        self.parent_bridge.publish(
            {
                "offline": self.generation.offline,
                "provider": self.provider,
                "outing": self.preferences.outing.copy(),
                "stamps": sorted(self.stamps),
                "export_busy": self.export_busy,
                "export_ready": self.export_path is not None,
                "jobs": [
                    {
                        "id": j.id,
                        "style": j.style,
                        "provider": j.provider,
                        "state": j.state.value,
                        "error": j.error,
                        "attempts": j.attempts,
                    }
                    for j in self.job_items
                ],
                "missions": [
                    {
                        "id": i,
                        "title": m.title,
                        "hint": m.hint,
                        "evidence": any(p.mission == i for p in self.photos),
                    }
                    for i, m in enumerate(MISSION_CARDS)
                ],
                "photos": [
                    {
                        "id": p.id,
                        "style": p.style.value,
                        "mission": p.mission,
                        "eligible": p.id not in self.preferences.excluded_photos,
                    }
                    for p in self.photos
                ],
            },
            self.export_path,
        )

    def parent_command(self, command: dict[str, object]) -> None:
        action = command.get("action")
        if action in ("approve", "cancel"):
            job_id = command.get("id")
            job = next((j for j in self.jobs.all() if j.id == job_id), None)
            if job is None:
                raise ValueError("Unknown request")
            if action == "approve":
                if command.get("consent") is not True:
                    raise ValueError("Explicit upload consent required")
                if job.state in (JobState.AWAITING, JobState.FAILED, JobState.UNKNOWN):
                    self.jobs.approve(job.id)
            else:
                self.jobs.cancel(job.id)
            self.refresh_jobs()
        elif action == "offline" and type(command.get("value")) is bool:
            self.set_offline(bool(command["value"]))
        elif action == "outing" and isinstance(command.get("missions"), list):
            self.set_outing(command["missions"])  # type: ignore[arg-type]
        elif (
            action == "eligible"
            and isinstance(command.get("id"), str)
            and type(command.get("value")) is bool
        ):
            self.set_eligible(str(command["id"]), bool(command["value"]))
        elif action == "mission":
            mission = command.get("id")
            if (
                type(mission) is not int
                or not 0 <= mission < len(MISSIONS)
                or not any(p.mission == mission for p in self.photos)
            ):
                raise ValueError("Mission has no evidence")
            candidate = self.stamps | {mission}
            self.store.save_progress(
                self.memory.snapshot() if self.memory else None,
                candidate,
                self.copy_pip.snapshot() if self.copy_pip else None,
                self.guess.snapshot() if self.guess else None,
            )
            self.stamps = candidate
        elif action == "export":
            self.start_export()
        else:
            raise ValueError("Unknown parent action")
