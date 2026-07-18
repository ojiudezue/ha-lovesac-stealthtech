"""Sensors: current input, audio capability, firmware versions, raw
layout/covering/arm-type bytes, and last-contact timestamp."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import protocol
from .const import DOMAIN
from .coordinator import StealthTechCoordinator
from .entity import StealthTechEntity

# D4: hardware/firmware-fixed capability, from the libstealthtech hardware
# teardown — exists so "why doesn't Atmos show up" is answered on the device
# page instead of in an issue tracker.
AUDIO_CAPABILITY = "Dolby Digital 5.1 / PLII (ARC only)"
AUDIO_CAPABILITY_SOURCE = (
    "hardware teardown (libstealthtech hardware-teardown.md) — "
    "capability is hardware/firmware-fixed"
)

# D6: enum values are collected raw until the table is reverse-engineered.
# Mapped names land in protocol.LAYOUT_NAMES / ARM_TYPE_NAMES / COVERING_NAMES
# from user-reported app-config vs raw-value pairs.
RAW_DECODING_NOTE = (
    "enum table built from user reports — pair your raw value with the "
    "Lovesac app's setting at "
    "https://github.com/ojiudezue/ha-lovesac-stealthtech/issues"
)


def _source_name(coordinator: StealthTechCoordinator) -> str | None:
    src = coordinator.state.source
    return None if src is None else protocol.SOURCE_NAMES[src]


def _mapped_enum(raw: int | None, names: dict[int, str]) -> str | int | None:
    """Render the empirically-bound name when known, else the raw int."""
    if raw is None:
        return None
    return names.get(raw, raw)


def _enum_attributes(raw: int | None) -> dict[str, object]:
    return {"raw_value": raw, "decoding": RAW_DECODING_NOTE}


@dataclass(frozen=True, kw_only=True)
class StealthTechSensorDescription(SensorEntityDescription):
    get_value: Callable[[StealthTechCoordinator], str | int | datetime | None]
    attributes: Callable[[StealthTechCoordinator], dict[str, object]] | None = None
    # Stays available through sustained connection failures (outage-reporting
    # entities must not go unavailable with everything else).
    always_available: bool = False


DESCRIPTIONS: tuple[StealthTechSensorDescription, ...] = (
    # Glanceable living-room state — deliberately NOT diagnostic-category.
    StealthTechSensorDescription(
        key="input", translation_key="input",
        icon="mdi:video-input-hdmi",
        get_value=_source_name,
    ),
    StealthTechSensorDescription(
        key="audio_capability", translation_key="audio_capability",
        icon="mdi:surround-sound",
        entity_category=EntityCategory.DIAGNOSTIC,
        get_value=lambda c: AUDIO_CAPABILITY,
        attributes=lambda c: {
            "atmos": False,
            "dts": False,
            "source": AUDIO_CAPABILITY_SOURCE,
            "dsp_firmware": c.state.versions.get("dsp"),
        },
    ),
    StealthTechSensorDescription(
        key="mcu_firmware", translation_key="mcu_firmware",
        icon="mdi:chip",
        entity_category=EntityCategory.DIAGNOSTIC,
        get_value=lambda c: c.state.versions.get("mcu"),
    ),
    StealthTechSensorDescription(
        key="dsp_firmware", translation_key="dsp_firmware",
        icon="mdi:chip",
        entity_category=EntityCategory.DIAGNOSTIC,
        get_value=lambda c: c.state.versions.get("dsp"),
    ),
    StealthTechSensorDescription(
        key="eq_firmware", translation_key="eq_firmware",
        icon="mdi:chip",
        entity_category=EntityCategory.DIAGNOSTIC,
        get_value=lambda c: c.state.versions.get("eq"),
    ),
    StealthTechSensorDescription(
        key="layout", translation_key="layout",
        icon="mdi:floor-plan",
        entity_category=EntityCategory.DIAGNOSTIC,
        get_value=lambda c: _mapped_enum(c.state.layout, protocol.LAYOUT_NAMES),
        attributes=lambda c: _enum_attributes(c.state.layout),
    ),
    StealthTechSensorDescription(
        key="covering", translation_key="covering",
        icon="mdi:texture-box",
        entity_category=EntityCategory.DIAGNOSTIC,
        get_value=lambda c: _mapped_enum(c.state.covering, protocol.COVERING_NAMES),
        attributes=lambda c: _enum_attributes(c.state.covering),
    ),
    StealthTechSensorDescription(
        key="arm_type", translation_key="arm_type",
        icon="mdi:sofa-single-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        get_value=lambda c: _mapped_enum(c.state.arm_type, protocol.ARM_TYPE_NAMES),
        attributes=lambda c: _enum_attributes(c.state.arm_type),
    ),
    StealthTechSensorDescription(
        key="last_contact", translation_key="last_contact",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.TIMESTAMP,
        get_value=lambda c: c.last_contact,
        # "How stale is everything" must survive the outage it measures.
        always_available=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: StealthTechCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        StealthTechSensor(coordinator, desc) for desc in DESCRIPTIONS
    )


class StealthTechSensor(StealthTechEntity, SensorEntity):
    entity_description: StealthTechSensorDescription

    def __init__(
        self,
        coordinator: StealthTechCoordinator,
        description: StealthTechSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"

    @property
    def available(self) -> bool:
        if self.entity_description.always_available:
            return True
        return super().available

    @property
    def native_value(self) -> str | int | datetime | None:
        return self.entity_description.get_value(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        if self.entity_description.attributes is None:
            return None
        return self.entity_description.attributes(self.coordinator)
