"""Media player entity for the StealthTech hub."""
from __future__ import annotations

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import protocol
from .const import DOMAIN
from .coordinator import StealthTechCoordinator
from .entity import StealthTechEntity

BASE_FEATURES = (
    MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.SELECT_SOURCE
    | MediaPlayerEntityFeature.SELECT_SOUND_MODE
)
BT_FEATURES = (
    MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: StealthTechCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([StealthTechMediaPlayer(coordinator)])


class StealthTechMediaPlayer(StealthTechEntity, MediaPlayerEntity):
    _attr_name = None  # takes the device name
    _attr_source_list = list(protocol.SOURCE_NAME_TO_VALUE)
    _attr_sound_mode_list = list(protocol.PRESET_NAME_TO_WRITE)

    def __init__(self, coordinator: StealthTechCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_media_player"

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        features = BASE_FEATURES
        # BT transport controls only make sense on the Bluetooth source.
        if self.state_obj.source == protocol.Source.BLUETOOTH:
            features |= BT_FEATURES
        return features

    @property
    def state(self) -> MediaPlayerState | None:
        power = self.state_obj.power
        if power is None:
            return None
        return MediaPlayerState.ON if power else MediaPlayerState.OFF

    @property
    def volume_level(self) -> float | None:
        vol = self.state_obj.volume
        return None if vol is None else vol / protocol.VOLUME_MAX

    @property
    def is_volume_muted(self) -> bool | None:
        return self.state_obj.mute

    @property
    def source(self) -> str | None:
        src = self.state_obj.source
        return None if src is None else protocol.SOURCE_NAMES[src]

    @property
    def sound_mode(self) -> str | None:
        preset = self.state_obj.preset
        return None if preset is None else protocol.PRESET_NAMES[preset]

    async def async_turn_on(self) -> None:
        await self.coordinator.async_send_frames(
            protocol.encode_power(True),
            optimistic=lambda state: setattr(state, "power", True),
        )

    async def async_turn_off(self) -> None:
        await self.coordinator.async_send_frames(
            protocol.encode_power(False),
            optimistic=lambda state: setattr(state, "power", False),
        )

    async def async_set_volume_level(self, volume: float) -> None:
        level = round(volume * protocol.VOLUME_MAX)
        await self.coordinator.async_send_frames(
            protocol.encode_volume(level),
            optimistic=lambda state: setattr(state, "volume", level),
        )

    async def async_mute_volume(self, mute: bool) -> None:
        await self.coordinator.async_send_frames(
            protocol.encode_mute(mute),
            optimistic=lambda state: setattr(state, "mute", mute),
        )

    async def async_select_source(self, source: str) -> None:
        value = protocol.SOURCE_NAME_TO_VALUE[source]
        await self.coordinator.async_send_frames(
            protocol.encode_source(value),
            optimistic=lambda state: setattr(state, "source", value),
        )

    async def async_select_sound_mode(self, sound_mode: str) -> None:
        write = protocol.PRESET_NAME_TO_WRITE[sound_mode]
        read = protocol.PRESET_WRITE_TO_READ[write]
        await self.coordinator.async_send_frames(
            protocol.encode_preset(write),
            optimistic=lambda state: setattr(state, "preset", read),
        )

    # PROTOCOL-UNCERTAIN: play/pause/skip values are guesses (see protocol.py).
    async def async_media_play(self) -> None:
        await self.coordinator.async_send_frames(protocol.encode_play_pause())

    async def async_media_pause(self) -> None:
        await self.coordinator.async_send_frames(protocol.encode_play_pause())

    async def async_media_next_track(self) -> None:
        await self.coordinator.async_send_frames(protocol.encode_skip(0))

    async def async_media_previous_track(self) -> None:
        await self.coordinator.async_send_frames(protocol.encode_skip(1))
