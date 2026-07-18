"""Pure hub model: write queue, optimistic state, and connection health.

No Home Assistant imports — everything here is unit-testable with a fake
BLE client and an injected clock. The coordinator wraps this class and only
adds HA plumbing (device resolution, DataUpdateCoordinator listeners).
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from .ble import ConnectCallable, run_session
from .protocol import Frame, StealthTechState

# Type of an optimistic state mutation applied at queue time; the state dump
# run on the same connection right after the write flush corrects it.
OptimisticUpdate = Callable[[StealthTechState], None]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def quiet_mode_writable(state: StealthTechState) -> bool:
    """Whether a quiet-mode toggle would land.

    The hub silently ignores EQ-control writes in standby (proven on
    hardware, acceptance ledger item 4) — refuse rather than lie.
    """
    return state.power is True


class StealthTechHub:
    """Owns state, the pending-write queue, and last-session health."""

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
        self.last_contact: datetime | None = None

    def queue(
        self, *frames: Frame, optimistic: OptimisticUpdate | None = None
    ) -> None:
        """Queue frames for the next session, optionally updating state now."""
        self.pending.extend(frames)
        if optimistic is not None:
            optimistic(self.state)

    async def poll(self) -> StealthTechState:
        """Run one session: flush queued writes, then dump for correction."""
        try:
            await run_session(
                self._connect, self.state, self.pending, self.idle_timeout
            )
        except Exception:
            self.link_ok = False
            raise
        self.link_ok = True
        self.last_contact = self._clock()
        return self.state
