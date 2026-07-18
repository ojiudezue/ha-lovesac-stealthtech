"""Tests for the pure hub layer: optimistic writes + correction, connection
health tracking (control link / last contact), and the quiet-mode power
guard. Time is frozen via an injected clock."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from lovesac_stealthtech import ble, protocol as p
from lovesac_stealthtech.hub import StealthTechHub, quiet_mode_writable

FROZEN = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)


class FakeClient:
    def __init__(self, notifications: list[bytes]):
        self.notifications = notifications
        self.writes: list[bytes] = []
        self._cb = None

    async def start_notify(self, char_uuid, callback):
        self._cb = callback

    async def stop_notify(self, char_uuid):
        pass

    async def write_gatt_char(self, char_uuid, data, response=False):
        self.writes.append(bytes(data))
        if bytes(data) == p.encode_state_request().data:
            for raw in self.notifications:
                self._cb(None, bytearray(raw))

    async def disconnect(self):
        pass


def notif(code, value):
    return bytes([0xCC, 0x05, 0xAA, code, value])


def make_hub(fake, clock=lambda: FROZEN):
    async def connect():
        if isinstance(fake, Exception):
            raise fake
        return fake

    return StealthTechHub(connect, idle_timeout=0.05, clock=clock)


@pytest.mark.asyncio
async def test_optimistic_queue_updates_state_immediately():
    hub = make_hub(FakeClient([]))
    hub.queue(p.encode_volume(9), optimistic=lambda s: setattr(s, "volume", 9))
    assert hub.state.volume == 9  # before any session ran
    assert hub.pending == [p.encode_volume(9)]


@pytest.mark.asyncio
async def test_optimistic_value_corrected_by_dump(monkeypatch):
    """Standby-EQ-rejected case: optimistic value snaps back to the dump's
    truth within the same flush session."""
    monkeypatch.setattr(ble, "INTER_WRITE_DELAY", 0)
    fake = FakeClient([notif(0x01, 12)])  # device reports volume 12
    hub = make_hub(fake)
    hub.queue(p.encode_volume(30), optimistic=lambda s: setattr(s, "volume", 30))
    assert hub.state.volume == 30
    await hub.poll()
    assert hub.state.volume == 12  # corrected
    assert hub.pending == []
    # The queued write went out before the dump request.
    assert fake.writes.index(p.encode_volume(30).data) < fake.writes.index(
        p.encode_state_request().data
    )


@pytest.mark.asyncio
async def test_poll_success_sets_link_ok_and_last_contact():
    hub = make_hub(FakeClient([notif(0x0A, 0x00)]))
    assert hub.link_ok is None
    assert hub.last_contact is None
    await hub.poll()
    assert hub.link_ok is True
    assert hub.last_contact == FROZEN


@pytest.mark.asyncio
async def test_poll_failure_sets_link_off_and_keeps_last_contact():
    hub = make_hub(FakeClient([]))
    await hub.poll()
    assert hub.link_ok is True

    # Next session: app holds the hub's single slot.
    async def connect():
        raise TimeoutError("slot held by Lovesac app")

    hub._connect = connect
    with pytest.raises(TimeoutError):
        await hub.poll()
    assert hub.link_ok is False
    assert hub.last_contact == FROZEN  # stale timestamp preserved


@pytest.mark.asyncio
async def test_link_recovers_on_next_success():
    fake = FakeClient([])
    hub = make_hub(TimeoutError("slot held"))
    with pytest.raises(TimeoutError):
        await hub.poll()
    assert hub.link_ok is False

    async def connect():
        return fake

    hub._connect = connect
    await hub.poll()
    assert hub.link_ok is True


def test_quiet_mode_guard_refuses_when_off_or_unknown():
    state = p.StealthTechState()
    assert quiet_mode_writable(state) is False  # power unknown
    state.power = False
    assert quiet_mode_writable(state) is False  # hub in standby
    state.power = True
    assert quiet_mode_writable(state) is True
