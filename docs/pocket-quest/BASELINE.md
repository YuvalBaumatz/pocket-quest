# Implemented Pocket Quest software

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
  Without a configured provider key, local filters and games remain available.
- Original/derivative album, local monochrome/pixel filters and three queued AI styles.
- Local filter preview; capture opens its result or unapproved AI queue item;
  completed jobs offer A VIEW to open the matching result.
- Pocket pixels preserves aspect ratio with a 64-pixel short edge and 32 colors;
  visually compared at handheld size. Existing saved derivatives retain their original look.
- OpenAI and Gemini adapters, parent approval/retry/cancel screens, and a free local demo.
- Persistent queue, rolling dispatch cap, restart recovery and late-result cancellation.
- Pi camera API is mock-tested; the actual Pi, LCD and physical controls are not tested.
- Three offline games: six-card Memory, Copy Pip sequences, and five-level Photo Guess.
  Saved progress, fake-clock rules, missing-photo recovery and photo permissions.
- Twelve illustrated missions, optional three-mission outings and a two-page passport.
  Original three IDs preserved; saved evidence is reviewable after restart; stamps are idempotent.
- Local grown-up controls: pause new API dispatches, outing selection, photo eligibility,
  background photo export and phone pairing.
- Opt-in authenticated companion: expiring one-use pairing, session cookies, exact
  Origin/Host checks, UI-thread commands, photo review, approvals, stamps and ZIP download.
- Configurable low-storage capture reserve (200 MiB default); no automatic deletion.
- Atomic file replacement, validation and preserved unreadable progress files.
- Photo ZIP export with originals/results, selected metadata and SHA-256 manifest;
  no credentials, runtime state or overwrite of existing backups.
- Headless screenshots, automated behavior tests and scoped lint/type/format checks.

## Current structure

`software/src/imagegencam/quest/`:

| Module | Owns |
| --- | --- |
| input.py | Semantic actions, press/release/hold normalization |
| device.py | Camera/Display protocols; webcam, fixture, file and Picamera2 adapters |
| configuration.py | Hidden Gemini key prompt and private Git-ignored .env storage |
| export.py | Streamed photo ZIP and checksum manifest; read-only library access |
| filters.py | Pure local image effects |
| storage.py | Original/derivative files, metadata, orphan-original recovery and progress |
| jobs.py | SQLite journal, approval, dispatch reservation, budget and recovery |
| providers.py | Demo, OpenAI SDK and Gemini REST image-edit adapters |
| workers.py | Background capture/preview and generation workers |
| memory.py | Pure six-card game rules and validated save snapshots |
| copy_pip.py / photo_guess.py | Offline game rules, timing, reveal levels and save validation |
| missions.py / preferences.py | Stable mission content and persisted grown-up choices |
| companion.py / web/ | Optional paired local HTTP interface and phone page |
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
- Child usability, actual phone/hotspot reachability, physical QR readability and
  a 60-minute real-device soak remain acceptance work. Local parent controls are a
  usability screen; the optional phone companion separately requires pairing.
- Two user-approved Gemini requests succeeded on the Mac, with original and result
  images present and decodable. OpenAI live generation and the revised camera navigation
  still need hands-on acceptance. The companion has fixture-based HTTP/browser validation.
- Export is available through `--export ZIP`, grown-up controls and the paired phone.
  Full app restore and hardware radio-off controls are not implemented. `--offline`
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

The planned software packets are implemented. Follow [HANDOFF.md](HANDOFF.md) and
[TESTING.md](TESTING.md) for acceptance, deferred by the user until implementation finishes.
Hardware work is blocked on exact board/camera identification, verified module pinout
and access to the physical device. Run the read-only hardware report there; do not
guess GPIO mappings or install upstream hardware services on this different module.

## Recorded verification (2026-09-23)

Python 3.11.15 on macOS: 218 tests passed (30 upstream, 188 Pocket Quest cases).
Two independent reviews identified queued-session revocation and restored-outing
selection issues; both were fixed, regression-tested and confirmed by the reviewers.
Game timing/retry/resume, all twelve mission evidence flows, parent settings, exclusions,
storage reserve and authenticated localhost companion routes have regression coverage.
The check suite binds temporary localhost ports for companion tests, not external networks.
Headless Chrome at 390×844 passed pairing, demo approval, pause, outing selection,
photo exclusion and ZIP download, with no page errors or horizontal overflow.
Native 240×240 screens were visually reviewed; the pairing QR decoded in software.
Export has 17 tests covering roundtrip/checksums, selected metadata, secret exclusion,
orphan originals, symlinks, failures, destination races, and the real shell launcher.
A real library export contained 7 photos / 12 image files; archive integrity,
source-byte equality, checksums and full image decoding were verified locally.
The generated validation ZIP is temporary; no permanent external backup is claimed.
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
