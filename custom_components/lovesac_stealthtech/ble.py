"""BLE session layer for the StealthTech hub.

The hub accepts only ONE BLE connection. Contract implemented here:
connect -> subscribe UpStream -> request state dump -> drain notifications
until they go quiet -> send any queued command frames -> disconnect after
idle. The connection is NEVER held between sessions.

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
    StealthTechState,
    StatusNotification,
    VersionNotification,
    apply_status,
    encode_state_request,
    parse_notification,
)

_LOGGER = logging.getLogger(__name__)

# Delay between successive characteristic writes; the hub's MCU relays frames
# over UART and can drop back-to-back writes.
# PROTOCOL-UNCERTAIN: neither source documents a required inter-write gap; the
# homebridge plugin serializes writes through noble without an explicit delay.
# 100 ms is a conservative choice - tune against hardware.
INTER_WRITE_DELAY = 0.1


class BleClientLike(TypingProtocol):
    """Minimal client surface (subset of bleak.BleakClient)."""

    async def start_notify(
        self, char_uuid: str, callback: Callable[[object, bytearray], None]
    ) -> None: ...

    async def stop_notify(self, char_uuid: str) -> None: ...

    async def write_gatt_char(
        self, char_uuid: str, data: bytes, response: bool = False
    ) -> None: ...

    async def disconnect(self) -> None: ...


ConnectCallable = Callable[[], Awaitable[BleClientLike]]


async def run_session(
    connect: ConnectCallable,
    state: StealthTechState,
    pending_frames: list[Frame],
    idle_timeout: float,
    request_dump: bool = True,
) -> StealthTechState:
    """Run one full connect->dump->drain->write->disconnect session.

    `pending_frames` is consumed (cleared) as frames are written.
    Raises whatever `connect` raises on connection failure.
    """
    client = await connect()
    quiet = asyncio.Event()
    loop = asyncio.get_running_loop()
    last_rx = loop.time()

    def _on_notify(_char: object, data: bytearray) -> None:
        nonlocal last_rx
        last_rx = loop.time()
        parsed = parse_notification(bytes(data))
        if isinstance(parsed, StatusNotification):
            apply_status(state, parsed)
        elif isinstance(parsed, VersionNotification):
            state.versions[parsed.component] = parsed.version
        quiet.set()  # wake the drain loop to re-check idle window

    try:
        await client.start_notify(CHAR_UPSTREAM, _on_notify)

        if request_dump:
            dump = encode_state_request()
            await client.write_gatt_char(dump.char_uuid, dump.data, response=False)

        # Drain notifications until idle_timeout of silence.
        while True:
            quiet.clear()
            remaining = idle_timeout - (loop.time() - last_rx)
            if remaining <= 0:
                break
            try:
                await asyncio.wait_for(quiet.wait(), timeout=remaining)
            except asyncio.TimeoutError:  # noqa: UP041 - builtin alias only on py>=3.11
                break

        # Send queued commands, oldest first.
        while pending_frames:
            frame = pending_frames.pop(0)
            await client.write_gatt_char(frame.char_uuid, frame.data, response=False)
            await asyncio.sleep(INTER_WRITE_DELAY)

        # Brief post-write drain so command echoes update state before we drop.
        if last_rx is not None:
            try:
                await asyncio.wait_for(quiet.wait(), timeout=idle_timeout)
            except asyncio.TimeoutError:  # noqa: UP041 - builtin alias only on py>=3.11
                pass
    finally:
        try:
            await client.stop_notify(CHAR_UPSTREAM)
        except Exception:  # noqa: BLE001 - disconnect must always run
            pass
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Disconnect failed (already dropped?)", exc_info=True)

    return state
