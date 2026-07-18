"""Binary sensors: subwoofer connected + control-link health."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import StealthTechCoordinator
from .entity import StealthTechEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: StealthTechCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            StealthTechSubwooferSensor(coordinator),
            StealthTechControlLinkSensor(coordinator),
        ]
    )


class StealthTechSubwooferSensor(StealthTechEntity, BinarySensorEntity):
    _attr_translation_key = "subwoofer"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: StealthTechCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_subwoofer"

    @property
    def is_on(self) -> bool | None:
        return self.state_obj.subwoofer_connected


class StealthTechControlLinkSensor(StealthTechEntity, BinarySensorEntity):
    """Did the last poll session connect?

    The one support question this integration will ever generate is
    "controls stopped working" — and the answer is almost always the app
    holding the hub's single BLE slot. Put the answer on the device page.
    """

    _attr_translation_key = "control_link"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: StealthTechCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_control_link"

    @property
    def available(self) -> bool:
        # This sensor reports on the outage — it must never join it. After
        # MAX_CONSECUTIVE_FAILURES the coordinator marks entities unavailable;
        # control_link stays up to show OFF + the reason instead.
        return True

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.link_ok

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        reason = self.coordinator.link_reason
        if self.coordinator.link_ok is False and reason is not None:
            return {"reason": reason}
        return None
