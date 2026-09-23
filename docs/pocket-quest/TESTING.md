# Pocket Quest acceptance and next milestones

Run from `/Users/yuvalbau/dev_cursor/pocket-quest`:

```sh
bash software/scripts/check_quest.sh
```

This runs Ruff lint/format, mypy, all upstream and Quest tests, screenshot generation,
and a desktop event-loop smoke test. Install `software/requirements-dev.lock.txt`
in `software/.venv` first. The command reports a temporary screenshot directory.
It uses demo data and mocked API/clipboard boundaries; it does not open the real
webcam, read a real key from the clipboard, or send photos to a provider.

Passing this command is required for each milestone, but is not a substitute for
the manual checks below. Record date, code revision, environment, expected/actual
result, and screenshot or sanitized error for any failure. Never include keys.

## Milestone 1: camera experience

Implemented: live local-filter preview; automatic local-result/AI-queue navigation
after capture; parent approval; A VIEW on completed requests. A completed background
capture does not navigate away from Home. Mission evidence retains its confirmation
screen. AI styles show the original preview, not a fabricated transformed preview.

Automated coverage includes:

- Real shell launcher and terminal confirmation with a fake clipboard; private key
  storage, cancellation, rejection diagnostics, and absence of keys in output.
- Original/pixel/mono capture opens the matching result; A swaps to intact original.
- AI capture opens its unapproved request; reviewing alone does not dispatch it;
  explicit approval processes a demo result; A VIEW selects its exact album entry
  even when older/newer photos exist; successful state and originals survive restart.
- Preview style changes use the current camera frame without mutating it; AI style
  returns to the original preview; tiny, portrait, and landscape filter inputs work.
- Save/camera failures, queue limits, interrupted requests, retries, cancellation,
  late results, offline dispatch suppression, and upstream regressions.

### Mac hands-on acceptance (pending for this revision)

Start with `bash software/scripts/run_quest.sh --provider none`:

| Check | Steps | Expected |
| --- | --- | --- |
| Preview | Camera; left/right through Original, Pocket pixels, Mono | Live scene visibly changes; face remains recognizable |
| Local result | Capture each style with Enter | Saved result opens immediately; Enter toggles original/result |
| Navigation | Escape to Camera; down for Album; left/right | Correct photos; no frozen camera or unexpected navigation |
| Restart | Close/relaunch and browse Album | Originals and saved derivatives remain available |
| Memory | Home → Play → Memory; finish pairs; restart | Inputs work; completed progress persists |
| Missions | Home → Explore; capture evidence; confirm; restart | Exactly one stamp awarded; evidence remains saved |

Then launch normally for a parent-approved live Gemini check:

1. Choose a starred style and capture an appropriate test photo.
2. Confirm the app opens its Magic Queue item and has not sent it yet.
3. Enter opens GROWN-UP CHECK; Enter again authorizes upload/API credits.
4. Observe Making magic → Ready in your album, or a useful failure message.
5. Enter opens that result; Enter swaps to its original. Restart and verify both.

Do not auto-retry real requests just to exercise tests. Network errors, timeouts,
and cancellation have mocked regression coverage; live fault testing must account
for ambiguous requests and charges. OpenAI requires its own configured live test.

## Next milestones

Software implementation now includes Copy Pip, Photo Guess, all twelve missions,
passport pages, outing choices, photo permissions, low-storage protection and the
paired phone companion. The suite includes game clocks/retries/resume, mission evidence
for every ID, duplicate stamps, preference persistence, exclusion from saved games,
storage failure, pairing/CSRF/Host checks and UI-thread commands. Companion HTTP tests
bind ephemeral localhost ports and need an environment that permits local sockets.

The mobile browser flow was tested at 390×844 with fixture photos: pairing, demo
generation approval, pause, outing changes, photo exclusion and ZIP download all passed.
Native QR decoding passed in software. Actual phone/hotspot and LCD scans remain pending.

Additional hands-on checks when testing begins:

| Area | Check |
| --- | --- |
| Copy Pip | Complete five rounds; make a mistake; replay; leave/resume; hold a direction; switch window focus |
| Photo Guess | Reveal all five levels; next image; restart mid-reveal; try an empty library |
| Explore | Browse twelve cards; choose three outing missions; confirm evidence after restart; see both passport pages |
| Parent controls | Exclude a photo and check both photo games; pause magic; build a ZIP while navigating |
| Companion | Pair actual phone; inspect evidence; approve one intended job; export/download; revoke session with a new code |

Milestone 2 photo export is implemented through `--export ZIP`; see [EXPORT.md](EXPORT.md).
Its 17 automated cases cover archive integrity, image/source equality, secret exclusion,
no overwrites, symlink rejection and failure cleanup. A real 7-photo / 12-image export
also passed checksum and image-decoding checks. Finder/external-backup acceptance is
deferred at the user's request, along with the revised camera hands-on check.

| Order | Deliverable | Required evidence before calling it done |
| --- | --- | --- |
| 2 | Export/backup originals and derivatives with manifest | Reopen archive; every reference resolves; no keys/config included; interrupted export preserves library |
| 3 | Copy Pip and Photo Guess: implemented | Automated/visual checks passed; actual child trial pending |
| 4 | Twelve missions and passport: implemented | Automated/visual checks passed; family outing trial pending |
| 5 | Verified Pi display/input/camera adapters | Exact board/pinout documented; orientation/color bars; every button; capture/restart on real device |
| 6 | Trip acceptance | Physical offline run, phone/export route, low-storage handling, measured battery life, child trial, 60-minute soak |

Hardware work can proceed alongside software only after identification. No guessed
GPIO mappings, battery claims, or hardware-ready claim based on Mac tests.

## Evidence boundaries

The automated suite uses real persistence and application logic with fake external
boundaries. Screenshots prove rendering, not usability. The Mac webcam has previously
returned a real 1280×720 frame. The user has exercised camera/key setup and local
filters, but this revised flow still needs a hands-on check. Pi/LCD/buttons/battery,
OpenAI live generation, manual export acceptance, the new games and expanded missions
still need hands-on acceptance. Two user-approved Gemini requests succeeded on their first attempts and
their originals/results decode successfully; the revised navigation still needs a
hands-on pass. See BASELINE.md for the current implemented scope.
