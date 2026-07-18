# Plan & Acceptance — v0.1 (pre-hardware)

Written 2026-07-17, after the initial build (the plan-before-build step was
skipped; this doc back-fills it and GATES the live pairing test — nothing
ships to HACS or gets an activation recommendation until the acceptance
table below is filled from real hardware).

## Deployment prerequisites (verified)
- **BLE connectivity:** HA host adapter in range of the sactional hub, OR an
  ESPHome BLE proxy (ESP32, firmware ≥ 2022.9.3 for active connections).
  **Shelly proxies verified NOT viable for control** (advertisement-only per
  HA Bluetooth docs, checked 2026-07-17) — they can surface discovery only.
- Single-connection contract: the hub accepts one BLE client. The Lovesac
  app and this integration contend; the integration connects briefly
  (default 90 s poll, 5 s idle disconnect, connect-on-demand for commands).

## Live pairing test plan (= the PROTOCOL-UNCERTAIN ledger)
| # | Item | How to test | Resolution |
|---|---|---|---|
| 1 | PlayerControl values (play/pause toggle=1?, skip 0=next/1=prev?) — guessed, neither source documents them | BT source, press play/pause/skip from HA, observe sofa + notification echoes | pending |
| 2 | Inter-write gap (100 ms assumed) | Rapid EQ slider drags; try 0 ms, watch for dropped frames | pending |
| 3 | Auto-discovery: hub advertises service UUID while unconnected | Fresh HA discovery card appears without manual address | **CLOSED 2026-07-18: discovered via ESPHome proxy (Ziri room ESP32), no manual address** |
| 4 | Post-write notification echo (drain-after-command assumes yes) | Volume change from HA reflects in HA state within one cycle without waiting for next poll | **CLOSED 2026-07-18 03:33: with media_player ON, EQ writes land AND persist in HA state (operator: Balance 50→59, Treble 10→16 stuck; quiet mode round-trips). Earlier snap-back = hub ignores EQ writes in STANDBY (device behavior, not integration bug — document in README). Power-on command also proven. Inter-write gap (item 2) survives normal slider use. |
| 5 | Pairing/bonding requirement (assumed none) | First connect from a never-bonded adapter succeeds | **CLOSED 2026-07-18: GATT connect THROUGH the proxy succeeded; state dump returned real values (bass 14, treble 10, center 20, rear 22, balance 50, sub connected); no bonding** |
| 6 | Layout/Covering/ArmType raw bytes | Log values; recline/re-arrange sactional, diff | pending |
| 7 | State-dump version frames (MCU/DSP/EQ) parse without polluting status | Check logs for mimic misparses (CC 06 guard) | **CLOSED 2026-07-18: entity values sane post-dump (no 71-volume mimic artifacts); device info shows Harman Kardon strings** |

## Acceptance criteria (fill from hardware, README-write-back style)
- **Verify:** config flow discovers or accepts manual address; entry loads; entities appear.
- **media_player:** power ON **PASS 2026-07-18** / off, volume slider renders **PASS**; sources ×4, sound modes ×4 (asymmetric enum), play/pause on BT — pending.
- **BLE-control × BT-audio coexistence (operator priority):** with HA holding the GATT control slot, select source=BT from HA, stream audio from a phone via classic A2DP, and confirm (a) audio plays, (b) HA source/volume commands still land, (c) play/pause/skip from HA affect the stream (this simultaneously closes ledger item 1). Hypothesis: control (BLE GATT) and audio (A2DP) are separate planes and never contend — neither reference doc states it explicitly, so this is the proof.
- **number ×5:** balance + treble round-trip **PASS 2026-07-18** (50→59, 10→16 persisted); bass/center/rear presumed same path — spot-check pending.
- **switch:** quiet mode toggles and reads back **PASS 2026-07-18**.
- **binary_sensor:** subwoofer connected matches reality.
- **Contention:** with the Lovesac app foregrounded, integration marks unavailable with the app-contention message (not a crash), recovers when app closes.
- **Suite:** 53 unit tests stay green; any hardware-driven protocol fix gets a regression fixture from captured bytes.

## Out of scope v0.1
Recline motors / lighting (not in this protocol surface), OTA characteristic
(read-never-write), multi-hub.
