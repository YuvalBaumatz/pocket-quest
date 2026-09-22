# Experience specification

## Concept

A tiny expedition console that turns family experiences into things to play with.
The loop is: notice something → photograph it → play with it → keep a memory.
Pixel gecko Pip is the guide, appearing on empty states, stamps and completion screens.
Pip is cheerful without demanding attention. No streaks, punishments, purchases,
competitive rankings or loss of earned items. One shared family passport in v1.

## Art direction

Think a colorful handheld adventure cartridge with a travel-journal personality.
Original art only; do not use existing game characters or copied sprites.

| Token | Value | Use |
| --- | --- | --- |
| ink | #182840 | Text, outlines, dark backgrounds |
| cream | #FFF2D3 | Main background, text on dark |
| teal | #19766F | Primary buttons and panels |
| mint | #A8E6BD | Gecko and positive feedback |
| gold | #F5BD4F | Selected borders, stamps |
| coral | #E77A65 | Secondary accents, not small text |

Use 2px outlines, 4px spacing increments, flat fills, square corners with optional
stepped corners. Draw sprite assets on a 24×24 or 32×32 grid, scale by integers using
nearest-neighbor. Draw photos at native display resolution with good resampling;
do not pixelate the actual camera view unless the chosen filter requests it.
No scanlines, CRT blur, tiny terminal fonts, gradients, continuous particles or
screen shake. Indicate selection with both a border and arrow, never color alone.

Text: body 16px minimum, titles 20–24px, incidental parent/status text 12px minimum.
Use a bundled licensed font with clear letter shapes; pixel treatment belongs mainly
in illustrations and headings. Verify glyph coverage and readability on hardware.
Hebrew requires shaping, directionality and mixed-number tests, not reversing strings.
Do not claim Hebrew supported until those tests pass. Child gameplay must be usable
through icons and one parent demonstration without reading instructions.

## Shared 240×240 geometry

Coordinates are device pixels; origin top left. Safe horizontal margin 12px.

- Status strip y=0..23: small Pip badge/mode icon, optional offline badge and battery.
  If battery is unavailable, omit it; never fabricate a percentage.
- Content y=24..207, width 216px between x=12 and x=227.
- Button legend y=208..239: back and primary-action icons, short labels.
- Full-screen image views may hide status; controls reappear on input.
- Cards contain one large illustration and at most two short text lines.
- No required interaction relies on animation, sound or precise timing.
- Feedback: selection ≤150ms target; simple 300–600ms celebrations, skippable with A.
  Targets require measurement, not assumptions about the SPI display.

The attached board illustrates layout and palette. It is not pixel-perfect typography
or a final sprite sheet. Production screens must be reviewed at actual 240×240 size.

## Inputs

Logical inputs: UP, DOWN, LEFT, RIGHT, CONFIRM, BACK. Optional SHUTTER and HOME.
Map only after physical controls are confirmed. If there are insufficient controls,
the lead revises mapping once; feature agents must not invent per-screen workarounds.
Desktop: arrows, Enter=A, Escape=B, H=Home, Space=optional shutter.

- A confirms or performs the displayed primary action; B returns one level.
- Hold B 800ms returns home, with progress feedback. Short B fires on release only
  if hold was not consumed. Home does not delete work or trigger power-off.
- Directions repeat after 350ms, then every 150ms. A/B/shutter never auto-repeat.
- Debounce at input boundary; screens receive semantic events, not GPIO values.
- On screen transition require release before another A action to avoid double capture.
- A dedicated physical shutter, if present, acts only within camera mode in v1.
- Shutdown lives in parent settings and uses confirmed hardware-specific behavior.

## Screen map

HOME → CAMERA → STYLE / ALBUM → PHOTO
HOME → PLAY → MEMORY / COPY PIP / PHOTO GUESS
HOME → EXPLORE → MISSION / PASSPORT
Parent phone companion → settings, queue approvals, export, mission verification.

Home is a horizontal carousel of three cards: Camera, Play, Explore. Left/right moves
one card, A opens it, B does nothing. Show three position dots and neighboring arrows.
Remember the last card, but boot into Home. Games and missions resume inside their
own modes. No modal network or API configuration blocks boot.

## Camera and album

Preview: square crop composed from the camera stream; save the full original frame.
Show a small selected-style badge. A captures; left/right chooses styles; down opens
album. Camera card illustration and lower legend teach these inputs.
During capture, lock duplicate shutter actions until the original is durable.
Then show a short checkmark. If writing fails, say “Could not save” and keep the
camera available to retry; never show false success. Camera failure does not block games.

Styles in v1: Original, Pocket Pixels (local), Mono (local), Clay Crew (AI), Ocean
Explorers (AI), Friendly Robot (AI). Show a distinct wand badge on AI styles.
Local effects run after capture, not on every preview frame. Each derivative links
to its original. An AI capture saves locally and creates an unapproved queue item.
Child copy is “Saved for magic”; it must not imply immediate processing.

Album: left/right browses photos; A toggles original/selected derivative when present;
down opens a large Original/Magic selector if multiple versions exist. B returns.
Queued photos display a small clock; completed ones gain a sparkle until viewed.
No delete action in child mode. Empty album shows Pip plus a camera action.
Games use parent-eligible local originals, not a dependency on completed AI results.

## Play: three explicit rule sets

### Memory

Six cards, 3 columns × 2 rows; positions x=16/88/160, y=44/116; cards 64×64.
Select with directions (stop at edges). A flips a face-down card. Two different
revealed cards lock further flips for 1000ms; a match remains face-up, otherwise both
turn down. Re-selecting an exposed card does nothing. No countdown and no score penalty.
Persist deck order, matches and cursor. On resume, close unmatched exposed cards.
Choose three distinct eligible images and duplicate each; fill gaps with bundled
illustrations. Shuffle with injected RNG for deterministic tests. Celebrate all pairs.

### Copy Pip

Four large directional symbols, distinguished by icon and color. Show a sequence of
length 1; child repeats using directions. Flash each for 600ms, gap 250ms. Ignore
direction input during demonstration. Success adds one item, up to length 5, then
celebrate completion. Mistake gently replays the same sequence; unlimited tries.
A replays instructions/sequence during input; B leaves with progress saved. No audio
dependency. On resume replay current sequence from its beginning.

### Photo Guess

Show a coarse mosaic of one local photo. A reveals the next level (12, 24, 60, 120,
240 pixels per side, scaled into the image area). Family guesses aloud; no microphone,
speech recognition, typing or automatic judging. At full reveal A selects next photo.
Show “Who knows?” visually with Pip and a question mark. If no photos exist, use
bundled object illustrations. Persist current image and reveal level.

## Explore

One mission card at a time. A opens camera with mission ID attached; B returns.
Left/right chooses another mission. After capture, mark evidence “ready to show”.
A parent confirms from companion; lead may add a local parent confirmation screen
if phone-free testing shows it necessary. Do not use image AI as a mandatory judge.
Award exactly one stamp per mission completion, even after retries or restarts.
Passport presents a 3×2 stamp page with additional pages via left/right.

Ship 12 illustrated mission templates: something yellow, something round, a leaf,
a cloud, a shadow, a reflection, a funny family pose, matching colors, something tiny,
something with wheels, a favorite snack, a favorite place. Parent chooses which suit
the location. No task asks the child to leave family, photograph strangers or touch wildlife.
Three optional missions per outing; no calendar streak or automatic daily reset.
Offline manual day/outing selection avoids dependence on correct device time.

## Parent companion

Reuse upstream companion capabilities where practical. Add a queue inbox with source
thumbnail, selected style/provider, pending count, approve-selected and cancel.
Default daily dispatch cap: 10 attempts; default queue cap: 50 items. Both configurable.
When cap is reached, photos still save; explain that extra magic requests were not queued.
No provider keys or raw errors on child screens. Details belong in parent diagnostics.
Parent controls: language, game-photo eligibility, mission verification, generation
provider, export originals/derivatives, radio-off setting and optional brightness if supported.
Parent mode is a usability boundary, not an authentication mechanism; see architecture.

## Later release

Creature cards: original object photo → parent-approved transformation → saved creature.
Use local templates for names/traits initially. Cards remain viewable offline. If generation
fails, original photo gets a themed local frame so collecting still works. No paid rerolls
or random rarity. Introduce cooperative creature challenges only after child testing.
Daily comics, stories, competitive battles, voice and multi-device play are deferred.
