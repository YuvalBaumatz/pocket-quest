# Implementation packets

## Working agreement for all agents

Read README, EXPERIENCE and ARCHITECTURE first. Work only in the standalone pinned
fork. Keep a task branch/worktree when concurrent agents are used. Do not run git
reset or discard another agent's work. One agent owns shared files at a time.
Each packet must receive exact allowed paths from the lead after F0. No interface,
dependency, GPIO, model, navigation or art-direction changes without lead review.
If a contract is missing, report the gap rather than guessing. Mock hardware/network.
Implement one packet; no opportunistic refactors or extra features.

Every handoff includes: changed files, behavior, acceptance evidence, commands/results,
remaining limitations and a screenshot for a visual change. Lead reviews diffs and
integrates shared-file changes. New pure Python is typed; establish Ruff, a scoped
type checker and pytest in F0 without requiring a cleanup of untouched upstream code.
Run formatting/lint/type checks on additions plus relevant upstream regression tests.

## Foundation: lead ownership, before feature delegation

### F0 — baseline and compatibility audit

Dependencies: none. Outputs: pinned fork commit, upstream license/notice retention,
BASELINE.md, chosen check commands, hardware fact sheet and compatibility matrix.
Inspect camera initialization, UI layout, background workers, queue migration,
companion auth/routes, service shutdown and installers. Record what is kept/adapted.
Run upstream tests before changing behavior; isolate environmental failures explicitly.
Collect board model, OS, manufacturer display docs/pinout, camera, power board and
controls. Do not run hardware installer until those facts exist.
Done: lead can name entry points, launch/test commands and each hardware dependency;
unknown hardware blocks physical launch only, not offline design or simulation.

### F1 — shared contracts and durable services

Dependencies: F0. Outputs: interfaces, semantic inputs, records, store, fake clock/RNG,
fixture assets, event/effect conventions and shared test helpers. Lead freezes signatures.
Tests: invalid state recovery; atomic-save interruption; duplicate mission/output
completion; concurrent companion/device writes; old queue migration fixture; path traversal.
Done: pure modules import without Pi libraries or credentials; old originals survive.

### F2 — renderer, simulator and navigation

Dependencies: F1. Outputs: theme, Home, Pip sprite, reusable card/legend primitives,
keyboard simulator and PNG screenshot command. Implement held-B semantics centrally.
Tests: A hold produces one action; B hold never triggers a short-back afterward;
focus and legend correct on every route; frames exactly 240×240; missing glyph fallback.
Done: lead reviews Home, camera shell, memory board and mission card at 1× and 3×;
all paths navigable by keyboard, without network. This is the visual baseline others use.

### F3 — physical display/camera vertical slice

Dependencies: F1–F2 and verified hardware. Outputs: display/input adapter, camera bridge,
safe startup/shutdown integration, original capture and album. Optional power adapter.
Tests: fake capture failure/disk full; real color bars and orientation; every physical
button; captured original and square preview; game navigation while camera unavailable.
Done: one real photo survives restart and appears in album; no ghost/double presses;
lead records FPS and latency. Simulator is not sufficient evidence for this packet.

After F2, pure feature work may proceed while F3 awaits hardware. No hardware-ready
claim and no final release until F3 passes. Lead owns final F3 integration.

## Bounded feature packets for smaller-model agents

| ID | Dependencies | Scope and outputs | Acceptance evidence |
| --- | --- | --- | --- |
| G1 Memory | F2 | games/memory plus its scene/tests; implement exact six-card rules | deterministic shuffle, no double flip, mismatch delay, completion, restart, 0/1/2/3 available photos |
| G2 Copy Pip | F2 | games/copy_pip plus scene/tests | fake-clock demonstration, inputs ignored during demo, retry same sequence, cap 5, replay/resume |
| G3 Photo Guess | F2 | games/photo_guess plus scene/tests | five reveal levels, next photo, no-image fallback, missing-photo recovery, resume |
| E1 Missions | F1–F2 | missions service, 12 content entries, mission/passport scenes | evidence links to photo, one stamp after duplicate confirmation, offline outing selection, pagination |
| C1 Local styles | F3 camera contract | two pure effects and style picker wiring | original bytes unchanged, correct derivative mapping, bad input, portrait/landscape handling |
| Q1 Generation queue | F1, audited upstream queue | approved state machine, caps, restart policy | table tests for every transition; unknown timeout not retried; cancellation/late result; no worker during radio-off |
| P1 OpenAI adapter | F1 provider contract | wrap upstream adapter; preserve existing flow | mocked success/error maps, bounded timeout, no key leaks, output validation |
| P2 Gemini adapter | F1 provider contract | Google edit adapter and config | mocked edit success, quota/auth/timeout/malformed-image errors; verified model supports images |
| W1 Parent companion | E1,Q1 | queue inbox, mission approval, photo eligibility, pairing | unauthenticated access rejected; repeated approvals idempotent; cap feedback; CSRF/origin checks |
| X1 Export | F1, photo contract | download archive plus photo/derivative manifest | archive opens, all references valid, secrets and runtime credentials excluded |
| L1 Language pack | F2; user language answer | externalized child strings and chosen font | every child screen measured; Hebrew shaping/RTL/mixed numbers if chosen; no overflow |

Lead alone integrates app.py/web.py/controller.py changes requested by parallel agents.
P1/P2 share only frozen contracts; agents must not both edit queue/runtime modules.
G1/G2/G3 can run independently. E1 and Q1 can run independently after storage contracts.
W1 follows both services. Task completion is not permission to enable real API requests.

## Integration and release

### R1 — end-to-end offline build

Dependencies: F3,G1–G3,E1,C1. Physically disconnect internet. Boot, take five photos,
play all games, attach mission evidence, restart, confirm retained progress. Verify
outbound flight has sufficient bundled images without any personal photo library.
No API key and camera disconnected must still allow Home/Play/Explore browsing.

### R2 — connected magic and companion

Dependencies: Q1,P1,P2,W1,X1. One approved sample per configured provider; original
stays intact and output appears in correct album entry. Disconnect during submission;
verify unknown outcome and parent recovery, without automatic duplicate requests.
Check pairing on intended phone/hotspot arrangement and actual QR readability at 240px.
Do not assume every hotspot lets a host phone reach its clients. Document working setup
and a fallback pairing path before departure. Test export and reopen several originals.

### R3 — device acceptance

Dependencies: R1,R2,chosen L1. Parent/child trial: after one demonstration, child can
choose Camera, take a photo, start Memory and return Home. Observe without coaching;
lead adjusts ambiguous icons/controls. Check text outdoors and comfortable control grip.
Measure runtime on actual battery in mixed capture/game use, not an estimated spec.
Test low storage, unavailable battery reporting, camera failure, bad credentials,
corrupt save fixture, service restart and radio-off. Simulate crash at persistence
boundaries in tests; avoid destructive power-pull experiments on irreplaceable photos.
Run a 60-minute soak with captures, games and generation; inspect memory growth,
response times and failures. Test controlled shutdown then fresh boot five times.
Release includes install/run/restore notes, pinned dependencies and copied backup.

## Priority and cuts

The departure date is unknown: do not attach invented calendar commitments.
If time is short, ship F0–F3 + G1 + C1 + album/export first; add G2/G3 and missions
next. Queue/provider support follows once persistence is reliable. Never cut original
preservation, offline games, input consistency or the real-device acceptance check.
Creature collection is a separately designed v2 packet after a successful family trial.

## Copy-paste assignment template

Implement packet [ID] from docs/pocket-quest/TASKS.md.
Read EXPERIENCE.md and ARCHITECTURE.md. Base commit: [lead supplies].
Allowed paths: [lead supplies exact paths]. Frozen interfaces: [paths/symbols].
Use fixtures/fake clock; do not call real image APIs or initialize GPIO.
Meet every acceptance item in the packet. Run [baseline check commands].
Return changed files, command results, screenshots if relevant, and limitations.
If completion needs a shared-contract change, stop that dependent portion and report
the exact proposed change; continue independent tests/content within assigned scope.
