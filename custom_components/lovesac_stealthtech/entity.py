"""Shared base entity."""
from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import StealthTechCoordinator


class StealthTechEntity(CoordinatorEntity[StealthTechCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: StealthTechCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            connections={(CONNECTION_BLUETOOTH, coordinator.address)},
            manufacturer="Lovesac / Harman Kardon",
            model="StealthTech Sound + Charge",
            name="Lovesac StealthTech",
            sw_version=coordinator.state.versions.get("mcu"),
        )

    @property
    def state_obj(self):
        return self.coordinator.state
