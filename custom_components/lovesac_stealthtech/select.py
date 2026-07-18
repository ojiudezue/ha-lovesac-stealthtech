"""Select entities: input source and sound mode.

Redundant with the media_player by design — a standalone dropdown is faster
from a dashboard, and automations read/write it without media_player service
ceremony. Both write the exact same frames as the media_player.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import protocol
from .const import DOMAIN
from .coordinator import StealthTechCoordinator
from .entity import StealthTechEntity
from .protocol import Frame, StealthTechState


def _current_source(state: StealthTechState) -> str | None:
    src = state.source
    return None if src is None else protocol.SOURCE_NAMES[src]


def _encode_source(option: str) -> Frame:
    return protocol.encode_source(protocol.SOURCE_NAME_TO_VALUE[option])


def _optimistic_source(state: StealthTechState, option: str) -> None:
    state.source = protocol.SOURCE_NAME_TO_VALUE[option]


def _current_sound_mode(state: StealthTechState) -> str | None:
    preset = state.preset
    return None if preset is None else protocol.PRESET_NAMES[preset]


def _encode_sound_mode(option: str) -> Frame:
    return protocol.encode_preset(protocol.PRESET_NAME_TO_WRITE[option])


def _optimistic_sound_mode(state: StealthTechState, option: str) -> None:
    state.preset = protocol.PRESET_WRITE_TO_READ[
        protocol.PRESET_NAME_TO_WRITE[option]
    ]


@dataclass(frozen=True, kw_only=True)
class StealthTechSelectDescription(SelectEntityDescription):
    current: Callable[[StealthTechState], str | None]
    encode: Callable[[str], Frame]
    optimistic: Callable[[StealthTechState, str], None]


DESCRIPTIONS: tuple[StealthTechSelectDescription, ...] = (
    StealthTechSelectDescription(
        key="input", translation_key="input",
        options=list(protocol.SOURCE_NAME_TO_VALUE),
        current=_current_source,
        encode=_encode_source,
        optimistic=_optimistic_source,
    ),
    # Manual (write-only preset 9) is deliberately NOT offered: the hub has
    # no read value for it, so an entity exposing it could never confirm the
    # selection and would sit on a stale mode — a lie-prone option.
    StealthTechSelectDescription(
        key="sound_mode", translation_key="sound_mode",
        options=list(protocol.PRESET_NAME_TO_WRITE),
        current=_current_sound_mode,
        encode=_encode_sound_mode,
        optimistic=_optimistic_sound_mode,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: StealthTechCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        StealthTechSelect(coordinator, desc) for desc in DESCRIPTIONS
    )


class StealthTechSelect(StealthTechEntity, SelectEntity):
    entity_description: StealthTechSelectDescription

    def __init__(
        self,
        coordinator: StealthTechCoordinator,
        description: StealthTechSelectDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"

    @property
    def current_option(self) -> str | None:
        return self.entity_description.current(self.state_obj)

    async def async_select_option(self, option: str) -> None:
        desc = self.entity_description
        await self.coordinator.async_send_frames(
            desc.encode(option),
            optimistic=lambda state: desc.optimistic(state, option),
        )
