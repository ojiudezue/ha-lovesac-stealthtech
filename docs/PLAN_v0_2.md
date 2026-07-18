# Plan v0.2 — Visibility & Livability

**Filed:** 2026-07-18 (pre-paces; final scope confirmed after the in-person
session — coexistence test + PlayerControl verification may add items).
**Principle carried from v0.1:** read-only surfaces are free; writes only on
documented frames; OTA / SystemLayout-write / Covering-write / UserSetting
remain never-touch.
**Operator stance:** redundancy with the media_player is fine — dashboard
directness beats purity.

## D1 — Optimistic writes + same-connection refresh (UX headline)
Every command entity updates its own state optimistically on send, AND the
BLE session requests a state dump on the same connection right after the
write flush (authoritative correction within seconds instead of the 90s
poll). Snap-back only happens when the device genuinely refused (e.g.
standby EQ writes — which then also self-corrects the optimistic value).
- **Verify:** slider move reflects instantly; wrong-in-standby value reverts
  within one session; test with fake client asserting dump-after-write.

## D2 — Input visibility + direct control (operator ask)
- `sensor.lovesac_stealthtech_input` — plain sensor mirroring current source
  (HDMI-ARC / BT / AUX / Optical). Not diagnostic-category: this is
  glanceable living-room state.
- `select.lovesac_stealthtech_input` — standalone dropdown writing the same
  Source frames as the media_player (redundant by design; faster from a
  dashboard, and automations read/write it without media_player service
  ceremony).
- **Verify:** select ↔ media_player ↔ sensor all agree after any of the
  three changes a source.

## D3 — Sound-mode Select (same argument as D2)
`select.lovesac_stealthtech_sound_mode` (Movies/Music/TV/News). Handles the
asymmetric read/write enums; documents (not exposes) the Manual quirk
(write-only 9, no read value → we don't offer it; comment explains).

## D4 — Audio-capability diagnostic in plain sight (operator ask)
`sensor.lovesac_stealthtech_audio_capability`, EntityCategory.DIAGNOSTIC,
state `"Dolby Digital 5.1 / PLII (ARC only)"` with attributes:
`atmos: false`, `dts: false`, `source: hardware teardown (libstealthtech
hardware-teardown.md) — capability is hardware/firmware-fixed`, and the DSP
firmware version once read (D5) so a hypothetical future firmware that
changes the answer is at least visible. Static by design — it exists so the
answer to "why doesn't Atmos show up" lives on the device page.

## D5 — Firmware version sensors
Send `encode_version_request()` once per poll session (frame exists, unused);
expose `sensor.…_mcu_firmware`, `…_dsp_firmware`, `…_eq_firmware`
(DIAGNOSTIC). Zero risk; also anchors D4's attrs.

## D6 — Layout / Covering / ArmType raw diagnostics
Three DIAGNOSTIC sensors surfacing the already-parsed raw ints
(`state.layout` / `covering` / `arm_type`), each with attribute
`decoding: "enum unmapped — values collected to build the table (ledger
item 6)"`. Read-only forever until the enums are reverse-engineered.

## D7 — Connection health (my addition — livability when things "don't work")
- `binary_sensor.lovesac_stealthtech_control_link` — did the last poll
  session connect? OFF + attribute `reason: "connection failed — the
  Lovesac app may be holding the hub's single Bluetooth slot"` turns the
  single-slot contention from a mystery into a sentence.
- `sensor.lovesac_stealthtech_last_contact` — timestamp of last successful
  state dump (DIAGNOSTIC). "How stale is everything I'm looking at."
- **Rationale:** the one support question this integration will ever
  generate is "controls stopped working" — and the answer is almost always
  the app. Put the answer on the device page.

## D8 — "Sync now" button
`button.lovesac_stealthtech_sync` — trigger an immediate poll session
(connect + dump). For the "I just changed things from the app, make HA
catch up" moment instead of waiting ≤90s.

## D9 — Quiet Couch polish
Rename to Lovesac's product term "Quiet Couch Mode"; add the
Homebridge-style power-off guard (refuse + log when hub is off); attribute
documenting what it does (couch/sub attenuation + peak limiting, center
carries).

## Considered, deliberately NOT in v0.2
- Power switch outside media_player (the media_player toggle is one tap;
  add later only if dashboards want it).
- Volume number (media_player volume + automations via volume_set suffice).
- Mute switch (same).
- Manual preset exposure (read-side gap makes it a lie-prone entity).
- Anything touching OTA / SystemLayout write / Covering write / UserSetting.

## Acceptance
- All new entities appear with correct categories; D2 tri-surface agreement;
  D1 instant-reflect + standby-revert; D5/D6 values populate from a real
  dump; D7 goes OFF with the reason attr when the app holds the slot
  (testable live: open the app, wait a poll); D8 refreshes within seconds.
- Unit tests per entity; fake-client tests for dump-after-write and
  version-request-per-session; suite stays green.
- Live write-back into this doc post-deploy, per house style.
