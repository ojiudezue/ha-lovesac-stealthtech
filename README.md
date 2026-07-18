# ha-lovesac-stealthtech

Home Assistant custom integration for the **Lovesac StealthTech Sound + Charge**
system (the Harman Kardon sound system embedded in Sactionals), controlled over
Bluetooth Low Energy.

## Credits

The BLE protocol was reverse-engineered by others; this integration only ports it
to Home Assistant. All protocol knowledge comes from these MIT-licensed projects:

- [ohmantics/homebridge-lovesac-stealthtech](https://github.com/ohmantics/homebridge-lovesac-stealthtech) — the original HomeKit plugin and reference implementation (Alex Rosenberg)
- [jackspirou/libstealthtech](https://github.com/jackspirou/libstealthtech) — full protocol spec from firmware analysis (`docs/protocol-mapping.md`)

## Features

- **Media player**: power, volume (0–36 mapped to 0–100%), mute, input source
  (HDMI-ARC / Bluetooth / AUX / Optical), sound mode presets
  (Movies / Music / TV / News), and play/pause/skip when the source is Bluetooth
- **Numbers**: bass (0–20), treble (0–20), center volume (0–30), rear volume (0–30), balance (0–100, 50 = center)
- **Switch**: quiet mode (night mode)
- **Binary sensor**: subwoofer connected

## Install

1. HACS → Custom repositories → add this repo as type *Integration*
2. Install "Lovesac StealthTech", restart Home Assistant
3. The hub should be auto-discovered via Bluetooth (it advertises a service UUID
   encoding `excelpoint.com`); otherwise add it manually with its BLE MAC address

## The single-connection caveat (important)

**The StealthTech hub accepts exactly ONE BLE connection at a time.** This
integration never holds the connection: it connects, requests a state dump,
drains notifications, sends any queued commands, and disconnects after a short
idle period (default 5 s). Polling defaults to every 90 s (both configurable in
the integration options).

Consequences:

- If the **Lovesac mobile app** is open on a phone in range, it holds the slot
  and the integration cannot connect. After 6 consecutive failures the entities
  go unavailable with a message saying exactly this. Close the app to recover.
- Conversely, while the integration is mid-poll (a few seconds), the app can't
  connect. With the default 90 s interval this is rarely noticeable.

## Range / ESPHome BLE proxy

If the hub is far from your Home Assistant host, an
[ESPHome Bluetooth proxy](https://esphome.io/components/bluetooth_proxy.html)
works well — the integration uses HA's standard Bluetooth stack, so any active
connectable proxy extends its range transparently (ESP32 firmware 2022.9.3+
for connections).

**Shelly Bluetooth proxies will NOT work for control.** Shelly Gen2+ devices
proxy advertisements only — per the HA Bluetooth docs they support no active
connections ("Single active connection: not supported"). A Shelly near the
couch lets HA *discover* the hub but never connect to it. You need the HA
host's own adapter in range, or an ESPHome proxy.

## Untested against hardware

This integration was written from the protocol documentation above and has
**not yet been validated against a real hub**. All `# PROTOCOL-UNCERTAIN:`
comments in the source mark spots where the docs are ambiguous (notably the
play/pause/skip byte values and inter-write timing). Bug reports with
`bleak` debug logs are very welcome.

## Development

```bash
pip install pytest pytest-asyncio
pytest tests/ -v
```

The protocol layer (`protocol.py`) is pure Python with no BLE or HA
dependencies and is fully unit-tested from fixtures constructed out of the
protocol docs.

## License

MIT — see [LICENSE](LICENSE). Upstream protocol sources are also MIT.
