# v0.3 Plan — update entities, power-off burst guard, couch shape, enum crowdsourcing

Ground truth: libstealthtech source study (characteristics.rs, commands.rs,
shared.js, firmware-analysis). Baseline: 88 tests passing at ed16da1.
Version: manifest 0.3.0.

## D1: Firmware update entities

`protocol.py` gains `LATEST_VERSIONS = {"mcu": (1, 71), "dsp": (1, 68), "eq": (1, 23)}`
(libstealthtech characteristics.rs:268-275; package-version numbering caveat
noted). New `update` platform: one UpdateEntity per component (mcu/dsp/eq),
installed_version from `state.versions`, latest_version from the table,
release_url to lovesac.com firmware page, NO install support (updates happen
in the Lovesac app — stated in the entity attributes). None-safe pre-dump.

- **Verify:** installed 1.70 + latest 1.71 → update pending; equal → up to date.
- **Verify:** no version dump yet → installed_version None, entity harmless.
- **Test:** `test_update.py` — latest table, installed/latest/None-safety, no INSTALL feature.

## D2: Power-off burst guard

Per libstealthtech commands.rs:452-468 (`is_audio_state`), the hub emits
garbage audio/EQ status during power-off bursts. In `ble.run_session`'s
notification path: once a POWER=off status is seen in a drain, subsequent
audio/EQ codes (volume, bass, treble, center, rear, balance, mute, preset,
source) are ignored for the remainder of that session; power, subwoofer and
version frames still apply. Guard is session-scoped (resets each session).

- **Verify:** burst fixture (power-off then garbage volume) leaves volume unchanged.
- **Verify:** normal powered-on session applies everything as before.
- **Test:** `test_ble_session.py` additions.

## D3: Couch Shape select + read-scale instrumentation

`encode_config_shape(value)` → `AA 06 <0|1|2|3> 00` on CHAR_SYSTEM_LAYOUT
(libstealthtech commands.rs:171-197,336). New select "Couch Shape"
[Straight, L-Shape, U-Shape, Pit], description WARNS it recalibrates the
surround field. NO optimistic update — waits for the device's Layout
notification. Instrumentation: hub remembers the last shape write; when a
subsequent session (same or next) reports Layout, log INFO
"wrote shape X (write-enum N) → device now reports layout raw M" — this is
how the read-scale table gets decoded (known fixed point: physical L-Shape
reads raw 5).

- **Verify:** frame bytes for each option; select has no optimistic mutation.
- **Verify:** pairing INFO logged on the first layout-bearing session after a
  shape write; cleared after two sessions.
- **Test:** `test_protocol.py` + `test_hub.py` + `test_ha_layer.py` additions.

## D4: Local override options flow

Options flow adds optional text fields `my_couch_shape`, `my_arm_style`,
`my_fabric`. Raw-sensor state precedence: shipped table (LAYOUT_NAMES etc.)
→ operator override → raw int; `raw_value` attr always the raw int. Field
descriptions ask the operator to also report the pairing on the issue
tracker. strings.json / translations/en.json in lockstep.

- **Verify:** override renders as sensor state only when the raw value is
  not in the shipped table; raw_value attr unchanged.
- **Test:** sensor precedence tests + options-schema key test + lockstep test.

## D5: Issue template + Repairs nudge

`.github/ISSUE_TEMPLATE/enum_report.yml` form (raw layout/arm/covering,
what the app/eyes say, firmware versions). Repairs: when a raw sensor
reports a value not in the shipped table AND no operator override is set,
raise a non-fixable, dismissible Repairs issue, one per (kind, value), with
learn_more_url deep-linking the form prefilled via query params
(GitHub issue forms support `?template=enum_report.yml&<field_id>=<value>&title=…`
— docs.github.com "Creating an issue from a URL query").
`async_create_issue` kwargs verified against HA core 2024.11.0
`helpers/issue_registry.py` (is_fixable, severity, translation_key,
translation_placeholders, learn_more_url, is_persistent — no invented kwargs).

- **Verify:** unknown raw value + no override → issue created once; override
  or shipped mapping suppresses it.
- **Test:** repairs tests against a stubbed issue_registry.

## D6: Audits + comment upgrades

(a) every ble.py write uses response=False + comment (WithResponse hangs the
device, per libstealthtech); (b) config_flow comment: matching is by service
UUID via manifest; app name-prefix list (HK_Lovesac, EE4034) noted as
fallback knowledge only; (c) PlayerControl PROTOCOL-UNCERTAIN → CONFIRMED
(libstealthtech shared.js:861-865: play/pause=1, skip fwd=0, back=1);
(d) Surround dead-end fence comment in protocol.py (removed upstream
2cb7f25, verified no-op on hardware).

- **Verify:** grep shows 3/3 writes response=False; comments present.
- **Test:** existing player-control tests still pass with confirmed values.

## Acceptance

- Full suite green (88 baseline + new tests), py_compile clean on all modules.
- manifest.json version 0.3.0; strings/en.json identical.
