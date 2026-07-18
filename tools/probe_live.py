#!/usr/bin/env python3
"""Live BLE probe for the StealthTech hub — closes the PROTOCOL-UNCERTAIN ledger.

Run from a laptop NEAR THE COUCH (quit the Lovesac app first — single
connection slot). Requires: pip install bleak

    python3 tools/probe_live.py scan
    python3 tools/probe_live.py dump <address>
    python3 tools/probe_live.py player <address>      # PlayerControl sweep (item 1)
    python3 tools/probe_live.py gap <address>         # inter-write gap test (item 2)
    python3 tools/probe_live.py send <address> <hex>  # raw frame, e.g. AA05000101

Every notification is printed with a monotonic timestamp so command→echo
latency and dropped-frame behavior are visible. Findings go into
docs/PLAN_v0_1_acceptance.md.
"""
from __future__ import annotations

import asyncio
import sys
import time

sys.path.insert(0, "custom_components/lovesac_stealthtech")
import protocol  # noqa: E402  (pure module — no HA imports)

from bleak import BleakClient, BleakScanner  # noqa: E402

SERVICE = protocol.SERVICE_UUID
UPSTREAM = protocol.CHAR_UPSTREAM
PLAYER = protocol.CHAR_PLAYER_CONTROL
DEVINFO = protocol.CHAR_DEVICE_INFO

T0 = time.monotonic()


def _log(tag: str, data: bytes | None = None) -> None:
    ts = time.monotonic() - T0
    suffix = f"  {data.hex(' ')}" if data is not None else ""
    print(f"[{ts:8.3f}] {tag}{suffix}")
    if data is not None:
        for parsed in protocol.parse_notification(bytes(data)):
            print(f"[{ts:8.3f}]   -> {parsed}")


def _on_notify(_char, data: bytearray) -> None:
    _log("NOTIFY", bytes(data))


async def scan() -> None:
    print("Scanning 15s for service", SERVICE)
    devices = await BleakScanner.discover(timeout=15.0, service_uuids=[SERVICE])
    for d in devices:
        print(f"  {d.address}  rssi={getattr(d, 'rssi', '?')}  {d.name}")
    if not devices:
        print("  none found — is the hub powered and the Lovesac app CLOSED?")
        print("  (ledger item 3: does the hub advertise while unconnected?)")


async def _connected(address: str):
    client = BleakClient(address, timeout=20.0)
    await client.connect()
    _log(f"CONNECTED {address} (ledger item 5: no bonding needed if this worked)")
    await client.start_notify(UPSTREAM, _on_notify)
    return client


async def dump(address: str) -> None:
    client = await _connected(address)
    try:
        f = protocol.encode_state_request()
        _log("WRITE state-dump", f.data)
        await client.write_gatt_char(f.char_uuid, f.data, response=False)
        await asyncio.sleep(5.0)  # drain — watch for version frames (item 7)
    finally:
        await client.disconnect()


async def player_sweep(address: str) -> None:
    """Ledger item 1: PlayerControl values. Put the hub on BT source with
    music playing, then watch which value actually toggles play/pause and
    which direction each skip value goes. 3s between candidates."""
    client = await _connected(address)
    try:
        for sub, val, label in [
            (0x00, 0x01, "play/pause candidate sub=00 val=01"),
            (0x00, 0x00, "play/pause candidate sub=00 val=00"),
            (0x01, 0x00, "skip candidate sub=01 val=00 (next?)"),
            (0x01, 0x01, "skip candidate sub=01 val=01 (prev?)"),
        ]:
            frame = bytes([0xAA, 0x05, sub, 0x01, val])
            input(f"ENTER to send: {label}  [{frame.hex(' ')}] ... ")
            _log(f"WRITE {label}", frame)
            await client.write_gatt_char(PLAYER, frame, response=False)
            await asyncio.sleep(3.0)
    finally:
        await client.disconnect()


async def gap_test(address: str) -> None:
    """Ledger item 2: inter-write gap. Ramps volume 10→20 with gaps of
    100/50/20/0 ms; if the final NOTIFY volume matches the last write for a
    gap, that gap is safe. Restores volume 15 at the end."""
    client = await _connected(address)
    try:
        for gap_ms in (100, 50, 20, 0):
            print(f"--- gap {gap_ms} ms: volume ramp 10..20 ---")
            for v in range(10, 21):
                f = protocol.encode_volume(v)
                await client.write_gatt_char(f.char_uuid, f.data, response=False)
                if gap_ms:
                    await asyncio.sleep(gap_ms / 1000.0)
            await asyncio.sleep(2.0)  # observe final echo
        f = protocol.encode_volume(15)
        await client.write_gatt_char(f.char_uuid, f.data, response=False)
    finally:
        await client.disconnect()


async def send_raw(address: str, hexstr: str) -> None:
    frame = bytes.fromhex(hexstr)
    client = await _connected(address)
    try:
        _log("WRITE raw", frame)
        # Route by cmd byte: 0x05 → PlayerControl, else EqControl
        char = PLAYER if len(frame) > 1 and frame[1] == 0x05 else protocol.CHAR_EQ_CONTROL
        await client.write_gatt_char(char, frame, response=False)
        await asyncio.sleep(3.0)
    finally:
        await client.disconnect()


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "scan":
        asyncio.run(scan())
    elif cmd in ("dump", "player", "gap") and len(sys.argv) == 3:
        asyncio.run({"dump": dump, "player": player_sweep, "gap": gap_test}[cmd](sys.argv[2]))
    elif cmd == "send" and len(sys.argv) == 4:
        asyncio.run(send_raw(sys.argv[2], sys.argv[3]))
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
