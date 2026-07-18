"""Number entities: bass, treble, center volume, rear volume, balance.

Ranges are documented in libstealthtech docs/protocol-mapping.md (Command
Encoding Table) and match the clamps in homebridge commands.ts - none guessed.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import protocol
from .const import DOMAIN
from .coordinator import StealthTechCoordinator
from .entity import StealthTechEntity
from .protocol import Frame, StealthTechState


@dataclass(frozen=True, kw_only=True)
class StealthTechNumberDescription(NumberEntityDescription):
    get_value: Callable[[StealthTechState], int | None]
    set_value: Callable[[StealthTechState, int], None]
    encode: Callable[[int], Frame]


def _setter(attr: str) -> Callable[[StealthTechState, int], None]:
    return lambda state, value: setattr(state, attr, value)


DESCRIPTIONS: tuple[StealthTechNumberDescription, ...] = (
    StealthTechNumberDescription(
        key="bass", translation_key="bass",
        native_min_value=0, native_max_value=protocol.BASS_MAX, native_step=1,
        get_value=lambda s: s.bass, set_value=_setter("bass"),
        encode=protocol.encode_bass,
        entity_category=EntityCategory.CONFIG,
    ),
    StealthTechNumberDescription(
        key="treble", translation_key="treble",
        native_min_value=0, native_max_value=protocol.TREBLE_MAX, native_step=1,
        get_value=lambda s: s.treble, set_value=_setter("treble"),
        encode=protocol.encode_treble,
        entity_category=EntityCategory.CONFIG,
    ),
    StealthTechNumberDescription(
        key="center_volume", translation_key="center_volume",
        native_min_value=0, native_max_value=protocol.CENTER_VOLUME_MAX, native_step=1,
        get_value=lambda s: s.center_volume, set_value=_setter("center_volume"),
        encode=protocol.encode_center_volume,
        entity_category=EntityCategory.CONFIG,
    ),
    StealthTechNumberDescription(
        key="rear_volume", translation_key="rear_volume",
        native_min_value=0, native_max_value=protocol.REAR_VOLUME_MAX, native_step=1,
        get_value=lambda s: s.rear_volume, set_value=_setter("rear_volume"),
        encode=protocol.encode_rear_volume,
        entity_category=EntityCategory.CONFIG,
    ),
    StealthTechNumberDescription(
        key="balance", translation_key="balance",
        native_min_value=0, native_max_value=protocol.BALANCE_MAX, native_step=1,
        get_value=lambda s: s.balance, set_value=_setter("balance"),
        encode=protocol.encode_balance,
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: StealthTechCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        StealthTechNumber(coordinator, desc) for desc in DESCRIPTIONS
    )


class StealthTechNumber(StealthTechEntity, NumberEntity):
    entity_description: StealthTechNumberDescription

    def __init__(
        self,
        coordinator: StealthTechCoordinator,
        description: StealthTechNumberDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"

    @property
    def native_value(self) -> int | None:
        return self.entity_description.get_value(self.state_obj)

    async def async_set_native_value(self, value: float) -> None:
        desc = self.entity_description
        level = int(value)
        await self.coordinator.async_send_frames(
            desc.encode(level),
            optimistic=lambda state: desc.set_value(state, level),
        )
