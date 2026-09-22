# Camera → saved original → magic → album

## Mac: real webcam and Gemini

Install `software/requirements-mac.txt` into the project environment, then run:

```sh
bash software/scripts/run_quest.sh --setup-gemini
```

Enter the Gemini key only in that terminal prompt. Input is hidden. It is saved to
Git-ignored `software/.env` with owner-only permissions. Subsequent launches use
`bash software/scripts/run_quest.sh`; the normal defaults are webcam and Gemini.
You can obtain a key from [Google AI Studio](https://aistudio.google.com/apikey).

Enter Camera and allow macOS camera access for your terminal application. The preview
is live. Captures use a fresh full webcam frame (1280×720 requested; actual hardware may
negotiate a different size). The camera is released when you leave Camera mode.
Local pixel/mono styles appear in the preview and open their saved result after capture.
Pick a starred style and capture to open its request in Magic Queue. Enter reviews it;
Enter again authorizes sending. Once complete, Enter opens that result in Album;
Enter switches between result and original. Up from Camera still opens the queue.

If access is denied, enable the terminal application under macOS Privacy & Security →
Camera, then relaunch. Use `--camera-index 1` if your intended camera is a different
available device. No camera is opened merely by starting at Home. If the API key is
missing, startup gives setup instructions; it does not enable a demo transformation.
For camera-only testing use `--provider none`; only real local filters are offered.
For an existing photo use `--image /absolute/path/to/photo.jpg`.

Real data lives in `~/.pocket-quest`; explicit demo data has a separate directory.
An actual Mac webcam check received a 1280×720 frame during development without saving
or uploading it. A real Gemini call still requires your locally entered key and approval.

## Explicit demo without a key or a charge

```sh
bash software/scripts/run_quest.sh --demo
```

1. Enter Camera. Press Right three times to choose `* Clay crew` (or select another starred style).
2. Press Enter to capture. The original saves in the background. The screen says “Saved for magic”.
3. Magic Queue opens automatically. Press Enter to review, then Enter to approve.
4. The local **demo** provider creates a clearly labelled demo result. This is a color effect, not AI.
5. Press Enter on the completed request to view it. Enter swaps result and original.

While a transformation runs, Home and games remain usable. Captures are single-flight:
a repeated shutter press during saving is ignored. Closing the desktop window waits
for the current capture to finish; generation requests are recovered on the next launch.

To use your own picture with real Gemini generation (after local key setup):

```sh
bash software/scripts/run_quest.sh --image /absolute/path/to/photo.jpg
```

The source file is never changed. Pocket Quest stores a full-resolution RGB PNG copy
and separate derivatives; it does not preserve the imported file's EXIF metadata.

## Real providers

Install the optional SDK dependency into the existing environment:

```sh
software/.venv/bin/python -m pip install -r software/requirements-ai.txt
```

Use `--setup-gemini` or set `OPENAI_API_KEY` / `GEMINI_API_KEY` in your local shell environment, then launch:

```sh
bash software/scripts/run_quest.sh --provider openai --image /absolute/path/to/photo.jpg
# or
bash software/scripts/run_quest.sh --provider gemini --image /absolute/path/to/photo.jpg
```

Do not paste keys into chat or commit them. This entry point reads `software/.env` and environment variables; explicit environment values take precedence. OpenAI defaults to `gpt-image-2`; Gemini defaults
to `gemini-3.1-flash-image`. Override with `--model IMAGE_MODEL_ID` if your account
requires a different image-editing model. Account access, output quality and live
provider behavior require an actual account smoke test; a live camera check was performed, but no provider request was sent in development.

Captures do not immediately upload. The parent review screen identifies the provider
and asks before approving dispatch. An approved job can resume on later launches with
that provider enabled. Provider, model and prompt are snapshotted when the capture
is queued. Changing launch settings does not reroute existing jobs; jobs for disabled
providers remain paused. Parent confirmation is a usability step, not authentication.

Use `--offline` to prevent all new dispatches, even approved ones. This is application
behavior, not a Wi-Fi/radio setting. Exiting and relaunching without it resumes approved
work for the selected provider. There is no network connectivity probe that pretends
to distinguish a pre-send outage from a lost response: ambiguous network errors require
review instead of automatic retry.

## Queue controls and reliability

- Camera Up → Magic Queue. Left/right selects a request.
- A → parent review for approval/retry. B backs out without approving.
- Down → cancel confirmation. Cancellation cannot undo a provider charge already incurred.
- A failed request never removes its original. Completed results appear in Album.
- Only explicit 429 responses auto-retry, honoring Retry-After (30 seconds if absent).
  Three dispatch attempts maximum per job; retries also count against the budget.
- Timeout, interrupted running job or uncertain server response becomes “Needs review”.
  No automatic provider fallback or resubmission. Retry warns that another charge is possible.
- Default cap: 10 dispatch attempts in a rolling 24-hour window, across providers.
  This is an attempt cap, not an exact money budget. Demo dispatches count too.
- Default pending capacity: 50 unfinished jobs. Additional captures still save their
  originals but display “Saved; magic not queued”. They must be captured/queued again later.
- A backwards clock cannot reset the budget. A badly wrong future clock can delay dispatch;
  correct device time before travel. Jobs do not use time as their identity.
- One instance owns each data directory. Use a different `--data-dir` for independent demos.

## Current implementation boundaries

`workers.py` owns background capture and generation. `jobs.py` owns the transactionally
persisted journal in `generation.sqlite3`; this replaces the proposed JSON job files for
**new Pocket Quest jobs only**. SQLite ships with Python and commits dispatch state and
budget accounting together. Original ImageGenCam queues are untouched and not migrated.

Originals, local derivatives and AI results are stored separately under `photos/<id>/`.
A saved original lacking metadata is recovered into the album on startup with no AI
request. A completed image written immediately before a crash is validated and recovered
without another generation call. Queue cancellation wins against late responses.

An abrupt crash after photo metadata is durable but before its generation job is queued
preserves the photo but may omit the magic request. Recovery never invents approval.
No automatic uploads, deletion or attempt to reconstruct missing API credentials occurs.

`providers.py` contains independent OpenAI SDK and Gemini REST adapters; both validate
returned image payloads, use bounded request timeouts, and expose safe error categories.
The provider adapters do not own retries. `DemoProvider` is an explicit offline test mode.
API image input is resized to at most 1280×1280; the locally saved original stays full size.

`--camera pi` selects a lazy Picamera2 adapter. It requests a 320×240 preview and switches
into the camera's still configuration for capture, then back through Picamera2's API.
Picamera2 must already be installed in the Pi's Python environment. This adapter is
contract-tested with a fake Picamera2 object, **not tested on actual hardware**.
The renderer still uses the desktop window: LCD output, GPIO controls, battery and
hardware-specific performance remain separate integration tasks. No Pi services were installed.

## Sources used to verify adapter contracts

- OpenAI image edits: https://developers.openai.com/api/docs/guides/image-generation
- Gemini image edits: https://ai.google.dev/gemini-api/docs/generate-content/image-generation
- Gemini REST fields: https://ai.google.dev/api/generate-content
- Picamera2 capture/switch-back API: https://github.com/raspberrypi/picamera2/blob/main/picamera2/picamera2.py

## Regression checks

Use the commands in BASELINE.md. All network tests replace SDK clients or HTTP transport;
no real requests or credentials are needed. Important scenarios include crash recovery,
late cancellation, a full queue, missing camera, bad image output, failed disk replacement,
clock rollback, provider changes and navigation during a slow transformation.
