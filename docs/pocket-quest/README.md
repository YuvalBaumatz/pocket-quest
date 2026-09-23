# Pocket Quest — design and implementation handoff

Status: target design with a partial working desktop foundation. Read BASELINE.md first. Hardware is not tested.
Owner: parent/lead developer. Audience: implementing agents, including smaller models.
Prepared 2026-09-21. These files now live in the standalone Pocket Quest fork. BASELINE.md records implemented scope.

## Read in order

1. EXPERIENCE.md — product decisions, screen geometry, controls and behavior.
2. ARCHITECTURE.md — proposed module boundaries, data contracts and failure handling.
3. TASKS.md — dependency-ordered work packets and acceptance criteria.
4. screens.svg — illustrative 240×240 screen designs; not final fonts or assets.

## What is decided

- Name: Pocket Quest (working name). Colorful pixel-art expedition theme.
- Primary player: one child aged 5½, with family turn-taking.
- Screen: user's 1.54-inch 240×240 LCD game module.
- Base: a standalone ImageGenCam fork, Python device runtime, local phone companion.
- Core experience works offline; image generation is an optional queued activity.
- First release: camera, album, three short games, missions and passport stamps.
- Second release: creature collection, then optional cooperative creature activities.
- No Firebase, Makers dependencies, accounts, public backend or Pi-hosted browser UI.

## Open facts; never invent these

Exact Pi model, display manufacturer/controller/pinout/rotation, physical button count,
camera module, battery and power board, audio hardware, OS and travel date are unknown.
The product title does not prove the Pi is a Zero 2 W. Do not assume ST7789 wiring or
reuse the upstream GPIO map. Language preference is unknown: use English for the
design preview, externalize strings, and support a future Hebrew font/layout check.
No audio is required. No GPS, touch input or accelerometer is assumed.

## How to begin

Lead owns foundation packets F0–F3 and approves the shared contracts. Other agents
may then take bounded feature packets. Do not ask feature agents to invent controls,
architecture or visual style. No agent should begin hardware installation without
the actual board details. Simulator, content and pure logic can proceed meanwhile.

## Research and provenance

Reviewed upstream README, software architecture, package metadata, controller source
and job store source. This is a preliminary source review, not a full integration audit.
Upstream main is mutable; F0 must pin an actual commit and verify these observations.

- https://github.com/openai/imagegencam — project and Apache-2.0 license; retain notices.
- https://raw.githubusercontent.com/openai/imagegencam/main/software/ARCHITECTURE.md
  — existing app composition, web companion, persistence and data folders.
- https://raw.githubusercontent.com/openai/imagegencam/main/software/pyproject.toml
  — Python 3.11+, Pillow and pytest configuration.
- https://raw.githubusercontent.com/openai/imagegencam/main/software/src/imagegencam/controller.py
  — current 320×240 constants, Pillow drawing and combined hardware/UI controller.
- https://raw.githubusercontent.com/openai/imagegencam/main/software/src/imagegencam/job_store.py
  — existing persistent jobs; inspect behavior before extending it.
- https://developers.openai.com/api/docs/guides/tools-image-generation
- https://ai.google.dev/gemini-api/docs/image-generation
  — both providers offer image editing. Choose and verify exact model identifiers,
  SDKs, availability and prices at implementation time; none are locked here.

## Definition of complete

A task is complete only with acceptance evidence, relevant automated checks, changed
file list and stated hardware limitations. Simulator success is never hardware proof.
The trip release requires the physical-device checklist in TASKS.md. No estimated
battery duration or delivery date is promised before measurements and departure date.
