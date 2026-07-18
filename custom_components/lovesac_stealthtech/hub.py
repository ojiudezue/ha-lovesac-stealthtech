"""Pure hub model: write queue, optimistic state, and connection health.

No Home Assistant imports — everything here is unit-testable with a fake
BLE client and an injected clock. The coordinator wraps this class and only
adds HA plumbing (device resolution, DataUpdateCoordinator listeners).
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone

from .ble import ConnectCallable, run_session
from .protocol import Frame, StealthTechState

# Type of an optimistic state mutation applied at queue time; the state dump
# run on the same connection right after the write flush corrects it.
OptimisticUpdate = Callable[[StealthTechState], None]

# Human-readable causes surfaced on the control-link binary sensor.
LINK_REASON_CONNECT_FAILED = (
    "connection failed — the Lovesac app may be holding the hub's single "
    "Bluetooth slot"
)
LINK_REASON_NO_DATA = "connected but no data received"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def quiet_mode_writable(state: StealthTechState) -> bool:
    """Whether a quiet-mode toggle would land.

    The hub silently ignores EQ-control writes in standby (proven on
    hardware, acceptance ledger item 4) — refuse rather than lie.
    """
    return state.power is True


class StealthTechHub:
    """Owns state, the pending-write queue, and last-session health.

    Single-session invariant: the device accepts only ONE BLE connection, so
    `poll()` serializes end-to-end (connect through disconnect) behind an
    asyncio.Lock. A second caller waits for the first session to fully tear
    down before its own connect is attempted.
    """

    def __init__(
        self,
        connect: ConnectCallable,
        idle_timeout: float,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._connect = connect
        self.idle_timeout = idle_timeout
        self._clock = clock
        self.state = StealthTechState()
        self.pending: list[Frame] = []
        self.link_ok: bool | None = None  # None = never attempted
        self.link_reason: str | None = None  # set whenever link_ok is False
        self.last_contact: datetime | None = None
        self._session_lock = asyncio.Lock()

    def queue(
        self, *frames: Frame, optimistic: OptimisticUpdate | None = None
    ) -> None:
        """Queue frames for the next session, optionally updating state now."""
        self.pending.extend(frames)
        if optimistic is not None:
            optimistic(self.state)

    async def poll(self) -> StealthTechState:
        """Run one session: flush queued writes, then dump for correction.

        `last_contact` only advances (and `link_ok` only goes True) when the
        session actually delivered data — at least one StatusNotification
        applied. A session that connects but stays silent is NOT a successful
        contact: `link_ok` goes False with a distinct reason and the previous
        `last_contact` timestamp is preserved as the honest staleness marker.
        """
        async with self._session_lock:
            try:
                applied = await run_session(
                    self._connect, self.state, self.pending, self.idle_timeout
                )
            except Exception:
                self.link_ok = False
                self.link_reason = LINK_REASON_CONNECT_FAILED
                raise
            if applied >= 1:
                self.link_ok = True
                self.link_reason = None
                self.last_contact = self._clock()
            else:
                self.link_ok = False
                self.link_reason = LINK_REASON_NO_DATA
            return self.state
