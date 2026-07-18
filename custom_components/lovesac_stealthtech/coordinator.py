"""DataUpdateCoordinator driving the poll / write cycle."""
from __future__ import annotations

import logging
from datetime import timedelta

from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .ble import run_session
from .const import (
    CONF_IDLE_TIMEOUT,
    CONF_POLL_INTERVAL,
    DEFAULT_IDLE_TIMEOUT,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MAX_CONSECUTIVE_FAILURES,
    UNAVAILABLE_MESSAGE,
)
from .protocol import Frame, StealthTechState

_LOGGER = logging.getLogger(__name__)


class StealthTechCoordinator(DataUpdateCoordinator[StealthTechState]):
    """Owns the single-slot BLE contract: never hold the connection.

    Reads: periodic poll session (connect, dump, drain, disconnect).
    Writes: queued, then flushed via an immediate on-demand session.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.address: str = entry.data["address"]
        poll = entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        self.idle_timeout: float = entry.options.get(
            CONF_IDLE_TIMEOUT, DEFAULT_IDLE_TIMEOUT
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{self.address}",
            update_interval=timedelta(seconds=poll),
        )
        self.state = StealthTechState()
        self._pending: list[Frame] = []
        self._failures = 0

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

    async def _run(self) -> StealthTechState:
        state = await run_session(
            self._connect, self.state, self._pending, self.idle_timeout
        )
        self._failures = 0
        return state

    async def _async_update_data(self) -> StealthTechState:
        try:
            return await self._run()
        except UpdateFailed:
            self._failures += 1
            if self._failures >= MAX_CONSECUTIVE_FAILURES:
                raise
            return self.state  # tolerate transient slot contention
        except Exception as err:  # noqa: BLE001
            self._failures += 1
            _LOGGER.debug("Poll session failed (%d): %s", self._failures, err)
            if self._failures >= MAX_CONSECUTIVE_FAILURES:
                raise UpdateFailed(
                    UNAVAILABLE_MESSAGE.format(failures=self._failures)
                ) from err
            return self.state

    async def async_send_frames(self, *frames: Frame) -> None:
        """Queue frames and flush them now via a connect-on-demand session."""
        self._pending.extend(frames)
        await self.async_request_refresh()
