# Proposed architecture and contracts

These are design decisions for the fork, not claims that these interfaces already exist.
F0 audits the pinned source and F1 finalizes signatures before delegation.

## Integration strategy

Keep Python and Pillow. Retain upstream camera, companion and storage behavior where
compatible, adding narrow seams rather than rewriting everything. The upstream
controller currently hard-codes 320×240 and mixes hardware, drawing and jobs: changing
two constants is not a sufficient square-screen port. The lead owns this integration.
Preserve source/derivative directories and recognize old jobs through explicit migration.
Never run old and new generation workers simultaneously over the same queue.

Suggested additions below software/src/imagegencam/:

| Path | Responsibility | Owner |
| --- | --- | --- |
| device/interfaces.py | Display, input, camera and optional power protocols | Lead |
| device/simulator.py | Keyboard input, fixture camera, window output | Foundation agent |
| device/game_module.py | Verified display/GPIO mapping only | Hardware agent |
| quest/contracts.py | Shared immutable data types and event definitions | Lead |
| quest/runtime.py | Navigation, scene lifecycle, event dispatch | Lead |
| quest/theme.py | Tokens, layout, fonts and sprite loader | Lead |
| quest/storage.py | Durable game/mission/photo metadata | Storage agent |
| quest/scenes/ | Home, camera, album and passport renderers | UI agents |
| quest/games/ | Pure game state transitions; no hardware imports | Game agents |
| quest/missions.py | Evidence and idempotent stamps | Mission agent |
| providers/base.py | Shared edit request/result/error contract | Lead |
| providers/gemini.py | Google adapter | Provider agent |
| quest/generation.py | Approval, scheduling and recovery policy | Queue agent |

Keep upstream OpenAI adapter behind the same provider seam. app.py remains composition
root; web.py uses service methods, never edits runtime files behind the store's back.
Existing upstream names may change after F0, but the responsibilities remain fixed.

## Runtime boundaries

One UI loop owns scene state and drawing. A camera worker publishes only its latest
preview frame; bounded buffer size 1. A storage/capture worker saves images without
blocking UI. A single generation worker performs network calls; it never mutates
scene state. Worker completions post typed events to the UI thread.
Serialize state mutations through one store owner/lock, including phone requests.
Never hold that lock across camera access, image processing or network requests.
Stop/suspend preview while playing; free unused image buffers. Cache display-sized
thumbnails, cap image cache at 12 entries, and do not preload the entire album.

Device ports, finalized by F1:

- Display.present(frame): accepts exactly a 240×240 RGB Pillow image.
- Input.poll(now_ms): returns ordered semantic press/release/hold events.
- Camera.start_preview(), latest_preview(), capture(), stop_preview().
- Power.read(): optional percent/charging; Power.shutdown(): optional capability.
- Scene.handle(event, now_ms): returns state change plus explicit effects.
- Scene.render(state, theme): returns a 240×240 image, no file/network/GPIO access.

Simulator uses the same renderer and reducers as hardware. A thin desktop-only
window adapter (Tk if available, otherwise an explicitly added optional dependency)
maps keys; headless tests render PNGs without a window. Hardware packages must be
lazy-loaded so importing pure game/render modules works on a laptop.

## Shared records

Use typed dataclasses/enums, JSON serialization at boundaries. All persisted objects
have schema_version=1. UUIDs identify records; timestamps are informational only.
Unknown enum/schema values produce a recoverable diagnostic, never silent deletion.

| Record | Required fields |
| --- | --- |
| Photo | id, relative_original_path, captured_at, style_id, mission_id or null, game_eligible, derivatives[] |
| Derivative | id, photo_id, relative_path, kind(local/ai), style_id, job_id or null |
| Style | id, label_key, icon_id, kind(original/local/ai), prompt_version or null |
| GameSave | game_id, rules_version, state, updated_at |
| Mission | id, template_id, outing_id, evidence_photo_ids[], status(open/evidence/complete), stamp_id or null |
| GenerationJob | id, photo_id, style_id, prompt_snapshot, provider, model, state, attempt_count, last_error_code, retry_after, output_id or null |

Job prompt_snapshot includes exact prompt text, version and generation parameters.
Provider/model is fixed on approval, not silently changed if settings later change.
Derive stable output identity from job ID; two completions for the same job produce
one derivative. Do not infer ordering or uniqueness from wall-clock timestamps.

Paths under data/: keep captures/, generated/ and queue/; add quest/state.json,
quest/photos/<id>.json and thumbnails/. Files store relative paths resolved under the
data root. Reject traversal. Copy fixture art into assets/quest/ with license manifest.
Do not commit runtime photos, saves, credentials or queue data.

Atomic writes: temporary file in same directory → flush/fsync → os.replace; fsync
directory where supported. Write image before metadata. On restart reconcile orphan
images and incomplete metadata; preserve recoverable originals. Keep one last-known-good
state backup and quarantine invalid JSON with a parent diagnostic. Cross-record updates
must be idempotent: stamp ID is derived from mission ID; output ID from job ID.
Single-store writes prevent lost updates from simultaneous companion and device input.

## Generation state machine

AWAITING_APPROVAL → READY → RUNNING → SUCCEEDED
READY → CANCELLED; AWAITING_APPROVAL → CANCELLED
RUNNING → RETRY_WAIT / FAILED / UNKNOWN
RETRY_WAIT → READY when approved policy and delay permit.

- Capture creates AWAITING_APPROVAL; reconnection alone does not approve it.
- Persist RUNNING and increment dispatch count before sending a request.
- Offline/radio-off/cap reached means no dispatch, not a failure popup.
- Explicit 429: honor Retry-After, otherwise 30/120/600 second backoff, maximum 3
  dispatches per job, within daily cap. Permanent credentials/input/moderation errors
  become FAILED with an actionable parent message; original remains intact.
- Ambiguous timeout, dropped response after submission, and interrupted RUNNING jobs
  become UNKNOWN. Do not automatically resubmit a possibly charged request. Retrieve
  by provider request ID if supported; otherwise parent explicitly chooses retry.
- Use provider idempotency only when documented; do not claim exactly-once billing.
- No automatic cross-provider fallback, because that can create unexpected uploads/costs.
- Cancel running jobs marks discard_requested; cancellation may not stop remote work
  or charges. Explain this in parent UI. Never attach a late result to another photo.
- Credentials remain device environment/config outside served directories, never in
  browser JavaScript, logs, export bundles or committed code.

Provider.edit(request) returns image bytes, MIME type, provider request ID if available,
and optional usage. Validate response size/type before decoding and saving. Configure
SDK timeouts; adapters map errors to explicit categories. Network is mocked in tests.
No actual API spend is required for unit tests; lead runs a small authorized smoke test
after configuration. A dispatch cap limits attempts, not an exact monetary budget.

## Companion, power and storage

Companion stays local. Use explicit pairing with a random secret and an authenticated
session for photo access/mutations; validate origin/CSRF for browser writes. Wi-Fi LAN
alone is not authentication. Keep credentials out of QR URLs; pair with a short-lived
code. Do not expose the service to public internet. Audit upstream routes as part of F0.

Hardware-confirmed radio-off disables network traffic; UI-only offline simulation is
not a radio-off implementation. Do not silently change OS networking from game code.
Parent explicitly enables queued work after reconnecting. Clock correction must not
reset usage counters repeatedly; persist budget window and let parent resolve bad time.

Before capture check a configurable free-space reserve (initial 200 MiB, validate on
hardware). If exhausted, stop new capture with parent guidance; retain all existing photos.
Bound queued items to 50. Never auto-delete originals. Export includes originals,
derivatives and a mapping manifest; excludes secrets. Parent verifies export before
any optional deletion tool, which is deferred from v1.

## Performance targets and release measurements

Targets: input-to-feedback p95 ≤150ms; preview ≥5fps; offline games remain responsive
during one generation request. Render static scenes only on change, animation at ≤10fps.
Measure memory/CPU, cold boot, preview FPS, capture latency, case temperature and actual
battery runtime on the real board. A Zero W needs a separate feasibility check; if targets
fail, reduce preview size/rate and animation before adding hardware or changing stacks.
