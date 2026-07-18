"""DataUpdateCoordinator driving the poll / write cycle."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_IDLE_TIMEOUT,
    CONF_POLL_INTERVAL,
    DEFAULT_IDLE_TIMEOUT,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MAX_CONSECUTIVE_FAILURES,
    UNAVAILABLE_MESSAGE,
)
from .hub import OptimisticUpdate, StealthTechHub
from .protocol import Frame, StealthTechState

_LOGGER = logging.getLogger(__name__)


class StealthTechCoordinator(DataUpdateCoordinator[StealthTechState]):
    """Owns the single-slot BLE contract: never hold the connection.

    Reads: periodic poll session (connect, dump, drain, disconnect).
    Writes: queued with an optimistic state update, then flushed via an
    immediate on-demand session that requests a state dump on the same
    connection AFTER the writes — the dump confirms or corrects the
    optimistic values (e.g. EQ writes the hub ignores in standby snap back).
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.address: str = entry.data["address"]
        poll = entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        idle_timeout: float = entry.options.get(
            CONF_IDLE_TIMEOUT, DEFAULT_IDLE_TIMEOUT
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{self.address}",
            # Explicit config_entry so the base class binds this coordinator
            # (and its poll timer) to the entry lifecycle. The kwarg exists
            # since HA 2024.11.0 (core update_coordinator.py, verified against
            # the 2024.11.0 tag) and omitting it stops working in 2025.11
            # (core issue #128077); hacs.json minimum bumped to match.
            config_entry=entry,
            update_interval=timedelta(seconds=poll),
        )
        self.hub = StealthTechHub(self._connect, idle_timeout)
        self._failures = 0

    @property
    def state(self) -> StealthTechState:
        return self.hub.state

    @property
    def link_ok(self) -> bool | None:
        return self.hub.link_ok

    @property
    def link_reason(self) -> str | None:
        return self.hub.link_reason

    @property
    def last_contact(self) -> datetime | None:
        return self.hub.last_contact

    async def _connect(self):
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            raise UpdateFailed(
                f"StealthTech hub {self.address} not found by any Bluetooth "
                "adapter/proxy (out of range, powered off, or the Lovesac app "
                "is holding its single connection slot)"
            )
        return await establish_connection(
            BleakClientWithServiceCache, device, self.address
        )

    async def _async_update_data(self) -> StealthTechState:
        try:
            state = await self.hub.poll()
        except UpdateFailed:
            self._failures += 1
            if self._failures >= MAX_CONSECUTIVE_FAILURES:
                raise
            return self.hub.state  # tolerate transient slot contention
        except Exception as err:  # noqa: BLE001
            self._failures += 1
            _LOGGER.debug("Poll session failed (%d): %s", self._failures, err)
            if self._failures >= MAX_CONSECUTIVE_FAILURES:
                raise UpdateFailed(
                    UNAVAILABLE_MESSAGE.format(failures=self._failures)
                ) from err
            return self.hub.state
        self._failures = 0
        return state

    async def async_send_frames(
        self, *frames: Frame, optimistic: OptimisticUpdate | None = None
    ) -> None:
        """Queue frames (updating state optimistically) and flush them now.

        ACCEPTED (review B3): if a periodic poll session is mid-dump when a
        write is queued, the dump's frames can briefly revert the optimistic
        value until the flush session (requested below) re-writes and
        re-dumps. Benign and bounded — the UI blips for at most one session
        and self-corrects on the very next dump; not worth cross-session
        sequencing machinery.
        """
        self.hub.queue(*frames, optimistic=optimistic)
        if optimistic is not None:
            self.async_update_listeners()
        await self.async_request_refresh()
