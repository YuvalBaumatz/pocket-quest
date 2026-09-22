"""Bounded background capture and generation, publishing results to the UI thread."""

import threading
from dataclasses import dataclass
from queue import Empty, Queue

from PIL import Image

from .device import Camera
from .filters import Style
from .jobs import JobQueue
from .providers import EditError, EditRequest, Provider, validated_png
from .storage import Photo, Store, encode


@dataclass(frozen=True)
class CaptureResult:
    photo: Photo | None
    message: str


class CaptureWorker:
    def __init__(self, camera: Camera, store: Store, jobs: JobQueue, provider: str, model: str):
        self.camera, self.store, self.jobs = camera, store, jobs
        self.provider, self.model = provider, model
        self.requests: Queue[tuple[Style, int | None]] = Queue(maxsize=1)
        self.results: Queue[CaptureResult] = Queue()
        self.stop = threading.Event()
        self.preview_enabled = threading.Event()
        self.lock = threading.Lock()
        self.latest: Image.Image | None = None
        self.version = 0
        self.error = ""
        self.thread = threading.Thread(target=self._run, name="quest-capture", daemon=True)
        self.thread.start()

    def preview(self) -> tuple[Image.Image | None, int, str]:
        with self.lock:
            return self.latest, self.version, self.error

    def _run(self) -> None:
        try:
            while not self.stop.is_set() or not self.requests.empty():
                try:
                    style, mission = self.requests.get(timeout=0.1)
                except Empty:
                    if self.preview_enabled.is_set():
                        try:
                            frame = self.camera.preview()
                            with self.lock:
                                self.latest, self.error = frame, ""
                                self.version += 1
                        except Exception:
                            with self.lock:
                                self.error = "Camera unavailable"
                            self.stop.wait(0.5)
                    continue
                photo = None
                try:
                    source = self.camera.capture()
                    photo = self.store.capture(source, style, mission)
                    if style.is_ai:
                        self.jobs.enqueue(photo.id, style, self.provider, self.model)
                    message = "Saved for magic" if style.is_ai else "Photo saved!"
                except Exception:
                    message = "Saved; magic not queued" if photo else "Could not save photo"
                self.results.put(CaptureResult(photo, message))
                self.requests.task_done()
        finally:
            self.camera.close()

    def close(self) -> None:
        self.stop.set()
        self.thread.join(timeout=3)


class GenerationWorker:
    def __init__(
        self, jobs: JobQueue, store: Store, providers: dict[str, Provider], *, offline: bool = False
    ):
        self.jobs, self.store, self.providers = jobs, store, providers
        self.offline = offline
        self.stop = threading.Event()
        self.changed = threading.Event()
        self.thread: threading.Thread | None = None
        self.error = ""

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, name="quest-generation", daemon=True)
        self.thread.start()

    def process_one(self) -> bool:
        if self.offline or self.stop.is_set():
            return False
        was_blocked = self.jobs.budget_blocked
        job = self.jobs.claim(providers=tuple(self.providers))
        if was_blocked != self.jobs.budget_blocked:
            self.changed.set()
        if job is None:
            return False
        self.changed.set()
        try:
            provider = self.providers.get(job.provider)
            if provider is None:
                raise EditError("provider_unavailable")
            source = self.store.image(job.id, original=True)
            source.thumbnail((1280, 1280))
            result = provider.edit(EditRequest(encode(source), job.prompt, job.model))
            self.jobs.complete(job, validated_png(result))
        except EditError as error:
            self.jobs.fail(job, error.code, unknown=error.unknown, retry_after=error.retry_after)
        except Exception:
            # Unexpected errors may happen after a charged response; never auto-resubmit.
            self.jobs.fail(job, "processing_uncertain", unknown=True)
        self.changed.set()
        return True

    def _run(self) -> None:
        try:
            while not self.stop.is_set():
                try:
                    self.process_one()
                except Exception:
                    self.error = "Magic paused: storage error"
                    self.changed.set()
                    break
                self.stop.wait(0.25)
        finally:
            if self.stop.is_set():
                self.jobs.close()

    def close(self) -> None:
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=2)
            if not self.thread.is_alive():
                self.jobs.close()
        else:
            self.jobs.close()
