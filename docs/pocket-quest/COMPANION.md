# Paired parent companion

The server is opt-in and independent of upstream ImageGenCam's phone server.

For testing on the Mac itself:

```sh
bash software/scripts/run_quest.sh --companion
```

For a phone on the same trusted home network/personal hotspot, bind to the Mac/Pi's
actual local IPv4 address. For example only, if the device address is `192.168.1.25`:

```sh
bash software/scripts/run_quest.sh --companion --companion-host 192.168.1.25
```

Port defaults to 8765; `--companion-port` changes it. No server starts in normal runs.
Use `--provider none` for real camera/local games without an API provider, or `--demo`
for fixture-only testing. The server rejects wildcard/public bind addresses.

## Pairing and actions

On the device: Home → Up → Pair phone. Scan the QR, or open the printed address,
then enter the six-digit code from the device. QR contains only the address, never
the code or an API key. Each code lasts five minutes, works once, and allows at most
five attempts. A new code (Enter on Pair phone) revokes the previous browser session.
Sessions last up to twelve hours, remain in memory only, and are revoked on restart.

After pairing a parent can:

- Review photos before approving transformations, explicitly authorize API credit
  usage, retry failed/unknown jobs, and cancel queued work.
- Pause new API dispatches. In-flight requests may still finish and incur charges.
- Choose zero to three outing missions (zero means all twelve), review evidence,
  and award a stamp exactly once.
- Exclude/include photos in games. Originals stay in the album/export; an existing
  Memory board containing an excluded photo resets.
- Build a ZIP in the background and download it once ready. The photo gallery shows
  the latest hundred originals; export includes the complete saved library.

## Security and operational boundaries

The page uses an HttpOnly SameSite=Strict session cookie. State, photos, downloads
and mutations require authentication; POST checks exact Origin and Host. Request
bodies are bounded, pairing is rate limited, and request logging is disabled. Mutations
run on the device UI thread through a bounded command queue; HTTP threads do not write
game/queue state directly. Queued actions recheck session validity before execution;
expired or revoked sessions cannot execute previously queued actions. A busy response
can occur after a request was queued: refresh
state before trying again. Approvals and stamps are idempotent.

This is local HTTP, not encrypted transport or a public service. Use a trusted local
network, do not expose/forward its port, and do not use it on shared airport/hotel Wi-Fi.
A private hotspot or travel router is the intended route. Some hotspots isolate clients
or prevent the host phone reaching a client; test the actual arrangement before the
trip. Local grown-up controls and CLI export are the fallback when phone access fails.

Pause/offline is an application dispatch control, not OS airplane mode. This software
does not change Wi-Fi/Bluetooth radios. The local grown-up menu itself is a usability
screen, not a child-proof authentication lock.

## Verification performed

- Real localhost HTTP tests: unpaired access rejection, one-use/expiring pairing,
  attempt cap, session revocation, wrong Origin/Host rejection, photo path restrictions,
  UI-thread dispatch, explicit upload consent and duplicate approvals/stamps.
- Headless Chrome at 390×844: pair, approve a demo request, pause, select an outing,
  exclude a photo, build/download ZIP; no page errors or horizontal overflow.
- Software QR decoding from the native 240×240 Pair phone frame succeeded.

Actual phone/hotspot access and QR scanning from the physical LCD remain pending.
