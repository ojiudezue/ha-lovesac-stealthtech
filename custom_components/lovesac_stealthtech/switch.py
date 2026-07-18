"""Quiet Couch Mode switch (Lovesac's product term for night mode)."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import protocol
from .const import DOMAIN
from .coordinator import StealthTechCoordinator
from .entity import StealthTechEntity
from .hub import quiet_mode_writable

_LOGGER = logging.getLogger(__name__)

QUIET_MODE_BEHAVIOR = (
    "Attenuates couch speakers and subwoofer with peak limiting; the center "
    "(dialogue) channel carries at normal level."
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: StealthTechCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([StealthTechQuietModeSwitch(coordinator)])


class StealthTechQuietModeSwitch(StealthTechEntity, SwitchEntity):
    _attr_translation_key = "quiet_mode"
    _attr_extra_state_attributes = {"behavior": QUIET_MODE_BEHAVIOR}

    def __init__(self, coordinator: StealthTechCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_quiet_mode"

    @property
    def is_on(self) -> bool | None:
        return self.state_obj.quiet_mode

    async def _toggle(self, on: bool) -> None:
        # The hub silently ignores EQ writes in standby (hardware-proven,
        # acceptance ledger item 4) — refuse rather than pretend.
        if not quiet_mode_writable(self.state_obj):
            _LOGGER.debug(
                "Ignoring Quiet Couch Mode %s: hub is off (EQ writes are "
                "ignored in standby)",
                "on" if on else "off",
            )
            return
        await self.coordinator.async_send_frames(
            protocol.encode_quiet_mode(on),
            optimistic=lambda state: setattr(state, "quiet_mode", on),
        )

    async def async_turn_on(self, **kwargs) -> None:
        await self._toggle(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._toggle(False)
