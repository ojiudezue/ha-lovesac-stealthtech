"""Fake-client tests for the connect -> write -> version -> dump -> drain ->
disconnect session and the queued-write path."""
from __future__ import annotations

import itertools

import pytest

from lovesac_stealthtech import ble, protocol as p


@pytest.fixture(autouse=True)
def deterministic_session(monkeypatch):
    """B-HIGH-2: end the drain on a deterministic signal, not wall time.

    The fake client delivers every notification synchronously inside
    write_gatt_char, so by the time run_session reaches the drain loop there
    is nothing left to receive. Substituting an ever-advancing virtual clock
    for the session's monotonic source (the `ble._monotonic` test seam) makes
    the idle window already elapsed at the first drain check — the session
    ends because all frames were delivered, never because 0.05 real seconds
    happened to pass on a loaded machine. INTER_WRITE_DELAY is zeroed for the
    same reason (pure wall-clock sleep with no ordering significance).
    """
    ticks = itertools.count()
    monkeypatch.setattr(ble, "_monotonic", lambda loop: float(next(ticks)) * 1000.0)
    monkeypatch.setattr(ble, "INTER_WRITE_DELAY", 0)


class FakeClient:
    """Records the session's calls and replays canned notifications."""

    def __init__(self, notifications: list[bytes], versions: list[bytes] | None = None):
        self.notifications = notifications
        self.versions = versions or []
        self.calls: list[tuple] = []
        self._cb = None

    async def start_notify(self, char_uuid, callback):
        self.calls.append(("start_notify", char_uuid))
        self._cb = callback

    async def stop_notify(self, char_uuid):
        self.calls.append(("stop_notify", char_uuid))

    async def write_gatt_char(self, char_uuid, data, response=False):
        self.calls.append(("write", char_uuid, bytes(data)))
        # State-dump / version requests trigger the canned notification bursts.
        if bytes(data) == p.encode_state_request().data:
            for raw in self.notifications:
                self._cb(None, bytearray(raw))
        elif bytes(data) == p.encode_version_request().data:
            for raw in self.versions:
                self._cb(None, bytearray(raw))

    async def disconnect(self):
        self.calls.append(("disconnect",))

    def writes(self):
        return [c for c in self.calls if c[0] == "write"]


def notif(code, value):
    return bytes([0xCC, 0x05, 0xAA, code, value])


def version_notif(component, major, minor):
    return bytes([0xCC, 0x06, 0xAA, 0x01, 0x03, component, major, minor])


@pytest.fixture
def fake():
    return FakeClient(
        [notif(0x0A, 0x00), notif(0x01, 20), notif(0x09, 1)],
        versions=[version_notif(0x01, 1, 71)],
    )


async def run(fake, pending=None, idle=0.05):
    state = p.StealthTechState()
    connects = []

    async def connect():
        connects.append(1)
        return fake

    applied = await ble.run_session(connect, state, pending if pending is not None else [], idle)
    return applied, state, connects


@pytest.mark.asyncio
async def test_connect_dump_drain_disconnect_cycle(fake):
    applied, state, connects = await run(fake)
    assert connects == [1]  # exactly one connection per session
    assert applied == 3  # count of StatusNotifications applied (B4)
    # Ordering: notify subscription, version request, dump request, teardown.
    assert fake.calls[0] == ("start_notify", p.CHAR_UPSTREAM)
    assert fake.calls[1] == ("write", p.CHAR_DEVICE_INFO, p.encode_version_request().data)
    assert fake.calls[2] == ("write", p.CHAR_DEVICE_INFO, p.encode_state_request().data)
    assert fake.calls[-2] == ("stop_notify", p.CHAR_UPSTREAM)
    assert fake.calls[-1] == ("disconnect",)
    # Notifications were applied to state.
    assert state.power is True
    assert state.volume == 20
    assert state.source == p.Source.BLUETOOTH


@pytest.mark.asyncio
async def test_version_request_sent_once_per_session(fake):
    _, state, _ = await run(fake)
    version_writes = [
        c for c in fake.writes() if c[2] == p.encode_version_request().data
    ]
    assert len(version_writes) == 1
    assert state.versions == {"mcu": "1.71"}


@pytest.mark.asyncio
async def test_silent_session_returns_zero_applied():
    """B4: version frames alone are not status data — applied count is 0."""
    fake = FakeClient([], versions=[version_notif(0x01, 1, 71)])
    applied, state, _ = await run(fake)
    assert applied == 0
    assert state.versions == {"mcu": "1.71"}


@pytest.mark.asyncio
async def test_queued_writes_flushed_before_dump(fake, monkeypatch):
    """D1: queued commands go FIRST; the dump on the same connection follows
    so it is authoritative for post-write state."""
    monkeypatch.setattr(ble, "INTER_WRITE_DELAY", 0)
    pending = [p.encode_volume(5), p.encode_mute(True)]
    await run(fake, pending=pending)
    writes = fake.writes()
    # queued commands in FIFO order, then version request, then dump — all
    # before disconnect.
    assert writes[0] == ("write", p.CHAR_EQ_CONTROL, p.encode_volume(5).data)
    assert writes[1] == ("write", p.CHAR_EQ_CONTROL, p.encode_mute(True).data)
    assert writes[2] == ("write", p.CHAR_DEVICE_INFO, p.encode_version_request().data)
    assert writes[3] == ("write", p.CHAR_DEVICE_INFO, p.encode_state_request().data)
    assert pending == []  # queue consumed
    assert fake.calls.index(writes[3]) < fake.calls.index(("disconnect",))


@pytest.mark.asyncio
async def test_dump_corrects_state_after_writes(monkeypatch):
    """The dump's values win over anything set before the session (the
    optimistic-write correction path, e.g. EQ writes ignored in standby)."""
    monkeypatch.setattr(ble, "INTER_WRITE_DELAY", 0)
    fake = FakeClient([notif(0x01, 12)])  # device says volume is 12
    state = p.StealthTechState()
    state.volume = 30  # optimistic value the device refused

    async def connect():
        return fake

    await ble.run_session(connect, state, [p.encode_volume(30)], 0.05)
    assert state.volume == 12


@pytest.mark.asyncio
async def test_disconnect_runs_even_if_session_body_fails(fake):
    async def boom_write(char_uuid, data, response=False):
        raise OSError("gatt error")

    fake.write_gatt_char = boom_write
    state = p.StealthTechState()

    async def connect():
        return fake

    with pytest.raises(OSError):
        await ble.run_session(connect, state, [], 0.05)
    assert ("disconnect",) in fake.calls


@pytest.mark.asyncio
async def test_connect_failure_propagates():
    async def connect():
        raise TimeoutError("slot held by Lovesac app")

    with pytest.raises(TimeoutError):
        await ble.run_session(connect, p.StealthTechState(), [], 0.05)
