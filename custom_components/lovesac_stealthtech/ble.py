"""BLE session layer for the StealthTech hub.

The hub accepts only ONE BLE connection. Contract implemented here:
connect -> subscribe UpStream -> flush any queued command frames -> request
firmware versions -> request state dump -> drain notifications until they go
quiet -> disconnect. The connection is NEVER held between sessions.

Writes go FIRST so the state dump on the same connection is authoritative
for post-write state: optimistic entity values get corrected within seconds
(e.g. EQ writes the hub silently ignores in standby snap back to truth)
instead of waiting for the next 90 s poll.

This module has no hard Home Assistant import; the bleak client is injected
via a `connect` callable so the session logic is testable with a fake client.
The real connector (bleak-retry-connector against a BLEDevice resolved by
HA's bluetooth helpers) lives in coordinator.py.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol as TypingProtocol

from .protocol import (
    CHAR_UPSTREAM,
    Frame,
    StatusCode,
    StealthTechState,
    StatusNotification,
    VersionNotification,
    apply_status,
    encode_state_request,
    encode_version_request,
    parse_notification,
)

_LOGGER = logging.getLogger(__name__)

# Power-off burst guard [libstealthtech commands.rs:452-468 is_audio_state]:
# during a power-off burst the hub emits garbage audio/EQ status frames, so
# once a POWER=off status arrives in a session's drain, subsequent audio/EQ
# codes are discarded for the remainder of that session. POWER, SUBWOOFER,
# the raw config codes (LAYOUT/COVERING/ARM_TYPE) and version frames still
# apply. The guard is session-scoped: the next session starts clean.
_AUDIO_EQ_CODES = frozenset(
    {
        StatusCode.VOLUME,
        StatusCode.CENTER_VOLUME,
        StatusCode.TREBLE,
        StatusCode.BASS,
        StatusCode.MUTE,
        StatusCode.QUIET_MODE,
        StatusCode.BALANCE,
        StatusCode.PRESET,
        StatusCode.SOURCE,
        StatusCode.REAR_VOLUME,
    }
)

# Delay between successive characteristic writes; the hub's MCU relays frames
# over UART and can drop back-to-back writes.
# PROTOCOL-UNCERTAIN: neither source documents a required inter-write gap; the
# homebridge plugin serializes writes through noble without an explicit delay.
# 100 ms is a conservative choice - survived normal slider use on hardware
# (acceptance ledger item 2, 2026-07-18).
INTER_WRITE_DELAY = 0.1


class BleClientLike(TypingProtocol):
    """Minimal client surface (subset of bleak.BleakClient)."""

    async def start_notify(
        self, char_uuid: str, callback: Callable[[object, bytearray], None]
    ) -> None: ...

    async def stop_notify(self, char_uuid: str) -> None: ...

    # AUDIT (v0.3 D6a): every write in this module passes response=False —
    # write-WITHOUT-response is mandatory. libstealthtech found that
    # write-with-response (WithResponse) hangs the device; do not "fix" a
    # write to response=True.
    async def write_gatt_char(
        self, char_uuid: str, data: bytes, response: bool = False
    ) -> None: ...

    async def disconnect(self) -> None: ...


ConnectCallable = Callable[[], Awaitable[BleClientLike]]


def _monotonic(loop: asyncio.AbstractEventLoop) -> float:
    """Session clock — test seam ONLY.

    In production this is exactly ``loop.time()`` (no behavior change). The
    ble-session tests substitute a virtual clock so the idle-drain window
    ends deterministically once the fake client has delivered every frame,
    instead of after a load-sensitive wall-clock wait.
    """
    return loop.time()


async def run_session(
    connect: ConnectCallable,
    state: StealthTechState,
    pending_frames: list[Frame],
    idle_timeout: float,
    request_dump: bool = True,
    request_versions: bool = True,
) -> int:
    """Run one full connect->write->dump->drain->disconnect session.

    `pending_frames` is consumed (cleared) as frames are written.
    Raises whatever `connect` raises on connection failure.

    Returns the number of StatusNotifications applied to `state` during the
    session. A session that connects but applies zero status frames delivered
    no data — the hub layer treats it as a failed contact, not a success.
    """
    client = await connect()
    quiet = asyncio.Event()
    loop = asyncio.get_running_loop()
    last_rx = _monotonic(loop)
    applied = 0
    # Burst guard, see _AUDIO_EQ_CODES above. NOTE: a POWER=on status does
    # NOT clear this latch within the session by design — the next session's
    # dump corrects any state the guard discarded.
    power_off_seen = False

    def _on_notify(_char: object, data: bytearray) -> None:
        nonlocal last_rx, applied, power_off_seen
        last_rx = _monotonic(loop)
        parsed = parse_notification(bytes(data))
        if isinstance(parsed, StatusNotification):
            if parsed.code == StatusCode.POWER and parsed.value == 1:
                # READ power is inverted: value 1 = OFF. [LST / HB responses.ts]
                power_off_seen = True
            elif power_off_seen and parsed.code in _AUDIO_EQ_CODES:
                _LOGGER.debug(
                    "Discarding %s=%d after power-off in this session "
                    "(power-off burst emits garbage audio/EQ status)",
                    parsed.code.name,
                    parsed.value,
                )
                quiet.set()
                return
            apply_status(state, parsed)
            applied += 1
        elif isinstance(parsed, VersionNotification):
            state.versions[parsed.component] = parsed.version
        quiet.set()  # wake the drain loop to re-check idle window

    try:
        await client.start_notify(CHAR_UPSTREAM, _on_notify)

        # Flush queued commands first (oldest first) so the dump below
        # reflects post-write state and corrects optimistic entity values.
        while pending_frames:
            frame = pending_frames.pop(0)
            await client.write_gatt_char(frame.char_uuid, frame.data, response=False)
            await asyncio.sleep(INTER_WRITE_DELAY)

        if request_versions:
            version = encode_version_request()
            await client.write_gatt_char(
                version.char_uuid, version.data, response=False
            )
            await asyncio.sleep(INTER_WRITE_DELAY)

        if request_dump:
            dump = encode_state_request()
            await client.write_gatt_char(dump.char_uuid, dump.data, response=False)

        # Drain notifications (command echoes, version frames, the dump)
        # until idle_timeout of silence.
        # ACCEPTED (review B5): a dump frame arriving AFTER idle_timeout of
        # silence is dropped with the connection. The 5 s default window is
        # ~50x the observed inter-frame gap on hardware; a later frame implies
        # a link so degraded the next session's full dump is the better fix.
        while True:
            quiet.clear()
            remaining = idle_timeout - (_monotonic(loop) - last_rx)
            if remaining <= 0:
                break
            try:
                await asyncio.wait_for(quiet.wait(), timeout=remaining)
            except asyncio.TimeoutError:  # noqa: UP041 - builtin alias only on py>=3.11
                break
    finally:
        try:
            await client.stop_notify(CHAR_UPSTREAM)
        except Exception:  # noqa: BLE001 - disconnect must always run
            pass
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Disconnect failed (already dropped?)", exc_info=True)

    return applied
