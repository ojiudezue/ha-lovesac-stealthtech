"""Quiet mode (night mode) switch."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import protocol
from .const import DOMAIN
from .coordinator import StealthTechCoordinator
from .entity import StealthTechEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: StealthTechCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([StealthTechQuietModeSwitch(coordinator)])


class StealthTechQuietModeSwitch(StealthTechEntity, SwitchEntity):
    _attr_translation_key = "quiet_mode"

    def __init__(self, coordinator: StealthTechCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_quiet_mode"

    @property
    def is_on(self) -> bool | None:
        return self.state_obj.quiet_mode

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_send_frames(protocol.encode_quiet_mode(True))

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_send_frames(protocol.encode_quiet_mode(False))
