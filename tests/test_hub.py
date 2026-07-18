"""Tests for the pure hub layer: optimistic writes + correction, connection
health tracking (control link / last contact), session serialization, and the
quiet-mode power guard. Time is injected via a mutable clock holder."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from lovesac_stealthtech import ble, protocol as p
from lovesac_stealthtech.hub import (
    LINK_REASON_CONNECT_FAILED,
    LINK_REASON_NO_DATA,
    StealthTechHub,
    quiet_mode_writable,
)

T0 = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)


class Clock:
    """Mutable injected clock — advance between polls so timestamp assertions
    can't pass tautologically (review C-MED-1)."""

    def __init__(self, now: datetime = T0):
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


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


def make_hub(fake, clock=None):
    async def connect():
        if isinstance(fake, Exception):
            raise fake
        return fake

    return StealthTechHub(connect, idle_timeout=0.05, clock=clock or Clock())


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
    clock = Clock()
    hub = make_hub(FakeClient([notif(0x0A, 0x00)]), clock)
    assert hub.link_ok is None
    assert hub.last_contact is None
    await hub.poll()
    assert hub.link_ok is True
    assert hub.link_reason is None
    assert hub.last_contact == T0


@pytest.mark.asyncio
async def test_poll_failure_sets_link_off_and_keeps_last_contact():
    clock = Clock()
    hub = make_hub(FakeClient([notif(0x01, 20)]), clock)
    await hub.poll()
    assert hub.link_ok is True
    success_time = hub.last_contact
    assert success_time == T0

    # Real time moves on before the failure (C-MED-1: without this advance
    # the preservation assertion below would be a frozen-clock tautology).
    clock.advance(300)

    # Next session: app holds the hub's single slot.
    async def connect():
        raise TimeoutError("slot held by Lovesac app")

    hub._connect = connect
    with pytest.raises(TimeoutError):
        await hub.poll()
    assert hub.link_ok is False
    assert hub.link_reason == LINK_REASON_CONNECT_FAILED
    # Stale timestamp preserved: still the SUCCESS time, not the failure time.
    assert hub.last_contact == success_time
    assert hub.last_contact != clock()


@pytest.mark.asyncio
async def test_link_recovers_on_next_success():
    fake = FakeClient([notif(0x0A, 0x00)])
    hub = make_hub(TimeoutError("slot held"))
    with pytest.raises(TimeoutError):
        await hub.poll()
    assert hub.link_ok is False

    async def connect():
        return fake

    hub._connect = connect
    await hub.poll()
    assert hub.link_ok is True
    assert hub.link_reason is None


@pytest.mark.asyncio
async def test_silent_session_is_not_a_contact():
    """B4: a session that connects but delivers zero status frames must not
    claim success — link goes False with a distinct reason and last_contact
    keeps the previous (real) contact time."""
    clock = Clock()
    hub = make_hub(FakeClient([notif(0x01, 20)]), clock)
    await hub.poll()
    assert hub.link_ok is True
    success_time = hub.last_contact

    clock.advance(90)
    hub_fake_silent = FakeClient([])  # connects fine, says nothing

    async def connect():
        return hub_fake_silent

    hub._connect = connect
    await hub.poll()  # no exception — but not a contact either
    assert hub.link_ok is False
    assert hub.link_reason == LINK_REASON_NO_DATA
    assert hub.last_contact == success_time  # did NOT advance


@pytest.mark.asyncio
async def test_silent_session_first_ever_leaves_last_contact_none():
    hub = make_hub(FakeClient([]))
    await hub.poll()
    assert hub.link_ok is False
    assert hub.link_reason == LINK_REASON_NO_DATA
    assert hub.last_contact is None


@pytest.mark.asyncio
async def test_concurrent_polls_serialize_sessions(monkeypatch):
    """B2: the single-session invariant lives in the hub — two concurrent
    poll() calls must never overlap connect..disconnect windows."""
    monkeypatch.setattr(ble, "INTER_WRITE_DELAY", 0)
    active = 0
    max_active = 0

    class SlowClient(FakeClient):
        async def start_notify(self, char_uuid, callback):
            await asyncio.sleep(0.02)  # widen the overlap window
            await super().start_notify(char_uuid, callback)

        async def disconnect(self):
            nonlocal active
            active -= 1

    clients = [SlowClient([notif(0x01, 20)]) for _ in range(2)]

    async def connect():
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        return clients.pop(0)

    hub = StealthTechHub(connect, idle_timeout=0.01, clock=Clock())
    await asyncio.gather(hub.poll(), hub.poll())
    assert max_active == 1  # second session waited for full teardown
    assert clients == []  # both sessions actually ran


@pytest.mark.asyncio
async def test_select_movies_round_trip_pure_layer():
    """A-LOW-2: selecting "Movies" queues the asymmetric WRITE value (7)
    while the optimistic state lands on the READ enum (MOVIES=0)."""
    hub = make_hub(FakeClient([]))
    write_val = p.PRESET_NAME_TO_WRITE["Movies"]
    hub.queue(
        p.encode_preset(write_val),
        optimistic=lambda s: setattr(s, "preset", p.PRESET_WRITE_TO_READ[write_val]),
    )
    assert hub.state.preset == p.PresetRead.MOVIES
    assert hub.pending == [p.encode_preset(p.PresetWrite.MOVIES)]
    assert int(p.PresetWrite.MOVIES) == 7
    assert 7 in hub.pending[0].data  # frame carries the write-value byte


@pytest.mark.asyncio
async def test_select_source_round_trip_pure_layer():
    """A-LOW-2: source uses the symmetric enum — Optical writes and reads 3."""
    hub = make_hub(FakeClient([]))
    value = p.SOURCE_NAME_TO_VALUE["Optical"]
    hub.queue(
        p.encode_source(value),
        optimistic=lambda s: setattr(s, "source", value),
    )
    assert hub.state.source == p.Source.OPTICAL
    assert hub.pending == [p.encode_source(p.Source.OPTICAL)]
    assert int(p.Source.OPTICAL) == 3
    assert 3 in hub.pending[0].data


def test_quiet_mode_guard_refuses_when_off_or_unknown():
    state = p.StealthTechState()
    assert quiet_mode_writable(state) is False  # power unknown
    state.power = False
    assert quiet_mode_writable(state) is False  # hub in standby
    state.power = True
    assert quiet_mode_writable(state) is True
