# Implemented foundation and camera workflow

Upstream: openai/imagegencam, commit `3475b97a2b631d7735d97f34d58dea47deb17942`.
Personal fork: https://github.com/YuvalBaumatz/pocket-quest

The design documents describe the complete destination. This file describes the
implemented subset and takes precedence for current status and actual file paths.

## Working now

- Separate `python -m imagegencam.quest` entry point, without API keys or Pi imports.
- Native 240×240 Pillow renderer with the same frames shown in the desktop simulator.
- Keyboard input with directional repeat, A repeat suppression and held-B Home.
- Background capture using a real Mac/USB webcam, supplied photo, explicit fixtures, or optional lazy Picamera2 adapter.
- Normal launch selects webcam + Gemini; private local key setup and no demo fallback.
- Original/derivative album, local monochrome/pixel filters and three queued AI styles.
- Local filter preview; capture opens its result or unapproved AI queue item;
  completed jobs offer A VIEW to open the matching result.
- Pocket pixels preserves aspect ratio with a 64-pixel short edge and 32 colors;
  visually compared at handheld size. Existing saved derivatives retain their original look.
- OpenAI and Gemini adapters, parent approval/retry/cancel screens, and a free local demo.
- Persistent queue, rolling dispatch cap, restart recovery and late-result cancellation.
- Pi camera API is mock-tested; the actual Pi, LCD and physical controls are not tested.
- Playable six-card photo memory, deterministic rules and saved matches.
- Three illustrated photo missions; captured evidence is tagged with its mission;
  local grown-up confirmation awards one persistent stamp per mission.
- Atomic file replacement, validation and preserved unreadable progress files.
- Headless screenshots, automated behavior tests and scoped lint/type/format checks.

## Current structure

`software/src/imagegencam/quest/`:

| Module | Owns |
| --- | --- |
| input.py | Semantic actions, press/release/hold normalization |
| device.py | Camera/Display protocols; webcam, fixture, file and Picamera2 adapters |
| configuration.py | Hidden Gemini key prompt and private Git-ignored .env storage |
| filters.py | Pure local image effects |
| storage.py | Original/derivative files, metadata, orphan-original recovery and progress |
| jobs.py | SQLite journal, approval, dispatch reservation, budget and recovery |
| providers.py | Demo, OpenAI SDK and Gemini REST image-edit adapters |
| workers.py | Background capture/preview and generation workers |
| memory.py | Pure six-card game rules and validated save snapshots |
| runtime.py | Navigation, capture/album/mission use cases |
| render.py | Palette, Pip, drawing primitives and screen rendering |
| __main__.py | Desktop composition, Pygame events and screenshot CLI |

Pygame is imported only when opening the desktop window. Tests and screenshot rendering
need no SDL window. Real runtime data defaults to `~/.pocket-quest`; `--demo` uses
`~/.pocket-quest-simulator`, or an explicit `--data-dir`. It does not share an upstream queue or mutate existing
ImageGenCam photos/settings. Photo files are indexed by UUID; album order uses metadata
file modification time in this simulator version.

## Retained upstream behavior

Original app/controller/web/queue/provider modules are unchanged. The original
ImageGenCam entry point and instructions remain below the new README introduction.
Their existing 320×240 hardware integration remains specific to that hardware.
New provider adapters are scoped to Pocket Quest. No upstream queue migration or phone-server networking change was made.
Apache-2.0 LICENSE, NOTICE and third-party notices are retained.

## Explicit remaining work

- Actual board identification, verified display controller/pinout/buttons, Pi camera
  integration, power/battery and performance measurements. No hardware installer ran.
- Memory is the only game. Copy Pip and Photo Guess remain future packets.
- Explore currently has 3 missions and a stamp count, not the planned 12-mission
  library/passport pages. Parent confirmation is a local usability screen, not a lock.
  An unconfirmed mission photo survives restart but the review screen does not resume.
- Two user-approved Gemini requests succeeded on the Mac, with original and result
  images present and decodable. OpenAI live generation and the revised camera navigation
  still need hands-on acceptance. Parent phone controls and authenticated companion are not wired in.
- No export UI, low-space reserve or hardware radio-off controls yet. `--offline`
  blocks application job dispatch only. A crash between photo save and job enqueue can
  retain the original without a magic request; it never invents parent approval.
- English only; no audio dependency. Do not claim Hebrew support or battery runtime.

## Validation commands

Run from `software/`, after installing `requirements-dev.lock.txt`:

```sh
.venv/bin/python -m pytest tests -q
.venv/bin/ruff check src/imagegencam/quest tests/quest
.venv/bin/ruff format --check src/imagegencam/quest tests/quest
.venv/bin/mypy
PYTHONPATH=src .venv/bin/python -m imagegencam.quest --demo --screenshots screenshots
SDL_VIDEODRIVER=dummy PYTHONPATH=src .venv/bin/python -m imagegencam.quest --demo --frames 3 --data-dir /tmp/pocket-quest-smoke
```

The last command tests the desktop event/render loop without opening a GUI; it is not
a physical-device test. Scope Ruff and mypy to new modules to avoid unrelated upstream
formatting changes. Use the full upstream+new pytest suite for regression coverage.

## Next agent task

Follow [TESTING.md](TESTING.md): finish hands-on camera acceptance, then implement
archive export with original/derivative manifest and secret-exclusion tests.
Hardware work needs the fact sheet before Picamera2/LCD/input verification.
Pure game packets may use `Action`, `MemoryGame` as an example,
`render.py` helpers and `Store` without hardware access. The lead owns changes to
runtime.py, storage.py and shared contracts. Update this baseline after each milestone.

## Recorded verification (2026-09-22)

Python 3.11.15 on macOS: 136 tests passed (30 upstream, 106 Pocket Quest cases).
`bash software/scripts/check_quest.sh` runs the complete offline validation and
produces screenshots in an isolated temporary directory. Camera navigation, local
preview, exact result selection, restart, and original preservation are covered.
Key setup covers quoted/assignment pastes, terminal paste markers, retries, cancellation,
private storage, and a Mac clipboard option tested with mocked clipboard reads.
The clipboard setup waits for confirmation before reading. A terminal integration test
runs the real shell launcher, confirms no early clipboard read/save, then saves a fake
key and starts the app with a fixture camera and dummy display. No real key is used.
Credentials accept printable ASCII punctuation; rejection reports character categories
without exposing input. Format/authentication validity remains Gemini's responsibility.
Scoped Ruff lint/format and mypy pass. Headless screenshots and the SDL dummy-driver
loop pass. Reviewed the camera → queue → parent approval → demo result → original
workflow at native resolution. Tested real provider request formats with mocked transport,
background responsiveness, cancellation, crash recovery, queue/budget limits and source
preservation. A real Mac webcam read returned 1280×720 without saving/uploading.
Subsequent user-approved Gemini requests produced two succeeded jobs, each on its
first attempt; both originals and outputs decode. The agent sent no additional live
generation requests. No Pi hardware test or LCD/battery measurement was performed.

[Camera workflow and setup](CAMERA-WORKFLOW.md) records exact controls, providers,
persistence rules, known boundaries and source documentation. The concrete SQLite queue
in that document supersedes the earlier proposed JSON queue in ARCHITECTURE.md.
