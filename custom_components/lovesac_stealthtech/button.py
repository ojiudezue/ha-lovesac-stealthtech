"""Sync-now button: trigger an immediate poll session."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import StealthTechCoordinator
from .entity import StealthTechEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: StealthTechCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([StealthTechSyncButton(coordinator)])


class StealthTechSyncButton(StealthTechEntity, ButtonEntity):
    """Connect + dump right now — for the "I just changed things from the
    Lovesac app, make HA catch up" moment instead of waiting for the poll."""

    _attr_translation_key = "sync"

    def __init__(self, coordinator: StealthTechCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_sync"

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()
