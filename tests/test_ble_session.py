"""Fake-client tests for the connect -> dump -> drain -> write -> disconnect
session and the queued-write path."""
import asyncio

import pytest

from lovesac_stealthtech import ble, protocol as p


class FakeClient:
    """Records the session's calls and replays canned notifications."""

    def __init__(self, notifications: list[bytes]):
        self.notifications = notifications
        self.calls: list[tuple] = []
        self._cb = None

    async def start_notify(self, char_uuid, callback):
        self.calls.append(("start_notify", char_uuid))
        self._cb = callback

    async def stop_notify(self, char_uuid):
        self.calls.append(("stop_notify", char_uuid))

    async def write_gatt_char(self, char_uuid, data, response=False):
        self.calls.append(("write", char_uuid, bytes(data)))
        # State-dump request triggers the canned notification burst.
        if bytes(data) == p.encode_state_request().data:
            for raw in self.notifications:
                self._cb(None, bytearray(raw))

    async def disconnect(self):
        self.calls.append(("disconnect",))


def notif(code, value):
    return bytes([0xCC, 0x05, 0xAA, code, value])


@pytest.fixture
def fake():
    return FakeClient([notif(0x0A, 0x00), notif(0x01, 20), notif(0x09, 1)])


async def run(fake, pending=None, idle=0.05):
    state = p.StealthTechState()
    connects = []

    async def connect():
        connects.append(1)
        return fake

    result = await ble.run_session(connect, state, pending if pending is not None else [], idle)
    return result, connects


@pytest.mark.asyncio
async def test_connect_dump_drain_disconnect_cycle(fake):
    state, connects = await run(fake)
    assert connects == [1]  # exactly one connection per session
    # Ordering: notify subscription, then dump request, then teardown.
    assert fake.calls[0] == ("start_notify", p.CHAR_UPSTREAM)
    assert fake.calls[1] == ("write", p.CHAR_DEVICE_INFO, p.encode_state_request().data)
    assert fake.calls[-2] == ("stop_notify", p.CHAR_UPSTREAM)
    assert fake.calls[-1] == ("disconnect",)
    # Notifications were applied to state.
    assert state.power is True
    assert state.volume == 20
    assert state.source == p.Source.BLUETOOTH


@pytest.mark.asyncio
async def test_queued_writes_flushed_after_drain(fake, monkeypatch):
    monkeypatch.setattr(ble, "INTER_WRITE_DELAY", 0)
    pending = [p.encode_volume(5), p.encode_mute(True)]
    await run(fake, pending=pending)
    writes = [c for c in fake.calls if c[0] == "write"]
    # dump + the two queued commands, in FIFO order
    assert writes[1] == ("write", p.CHAR_EQ_CONTROL, p.encode_volume(5).data)
    assert writes[2] == ("write", p.CHAR_EQ_CONTROL, p.encode_mute(True).data)
    assert pending == []  # queue consumed
    # Writes happen before disconnect.
    assert fake.calls.index(writes[2]) < fake.calls.index(("disconnect",))


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
