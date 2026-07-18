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
from homeassistant.helpers.entity import EntityCategory
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


def _current_couch_shape(state: StealthTechState) -> str | None:
    """Best-effort readback: the Layout READ scale differs from the write
    enum (physical L-Shape reads raw 5), so the current option is only shown
    when the shipped LAYOUT_NAMES binding maps the raw value to one of the
    four shape names. Unknown raw values render as no selection."""
    if state.layout is None:
        return None
    name = protocol.LAYOUT_NAMES.get(state.layout)
    return name if name in protocol.COUCH_SHAPE_NAME_TO_WRITE else None


def _encode_couch_shape(option: str) -> Frame:
    return protocol.encode_config_shape(protocol.COUCH_SHAPE_NAME_TO_WRITE[option])


def _note_couch_shape_write(coordinator, option: str) -> None:
    # Arm the read-scale pairing instrumentation (hub logs INFO when the
    # device's Layout status answers this write).
    coordinator.hub.note_shape_write(
        option, int(protocol.COUCH_SHAPE_NAME_TO_WRITE[option])
    )


@dataclass(frozen=True, kw_only=True)
class StealthTechSelectDescription(SelectEntityDescription):
    current: Callable[[StealthTechState], str | None]
    encode: Callable[[str], Frame]
    # None = NO optimistic update (calibration writes wait for the device's
    # own status notification instead of pretending the write landed).
    optimistic: Callable[[StealthTechState, str], None] | None = None
    # Optional pre-write hook on the coordinator (instrumentation).
    on_write: Callable[[object, str], None] | None = None
    # Optional user-facing warning, exposed as a state attribute (HA has no
    # per-entity description surface, so the attribute is the visible home).
    warning: str | None = None


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
    # Couch Shape is a CALIBRATION write (AA 06 <0-3> 00 on SystemLayout,
    # libstealthtech commands.rs:171-197,336): the hub recalibrates the
    # surround sound field for the selected shape. Deliberately NO optimistic
    # update — the entity waits for the device's Layout notification, and the
    # write→read pairing is logged for read-scale decoding.
    StealthTechSelectDescription(
        key="couch_shape", translation_key="couch_shape",
        options=list(protocol.COUCH_SHAPE_NAME_TO_WRITE),
        entity_category=EntityCategory.CONFIG,
        current=_current_couch_shape,
        encode=_encode_couch_shape,
        optimistic=None,
        on_write=_note_couch_shape_write,
        warning=(
            "Changing the couch shape RECALIBRATES the surround sound field "
            "for the selected configuration — only set it to match the "
            "physical couch. The selection is confirmed by the device's own "
            "Layout notification (no optimistic update)."
        ),
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

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        if self.entity_description.warning is None:
            return None
        return {"warning": self.entity_description.warning}

    async def async_select_option(self, option: str) -> None:
        desc = self.entity_description
        if desc.on_write is not None:
            desc.on_write(self.coordinator, option)
        optimistic = None
        if desc.optimistic is not None:
            opt_fn = desc.optimistic
            optimistic = lambda state: opt_fn(state, option)  # noqa: E731
        await self.coordinator.async_send_frames(
            desc.encode(option), optimistic=optimistic
        )
