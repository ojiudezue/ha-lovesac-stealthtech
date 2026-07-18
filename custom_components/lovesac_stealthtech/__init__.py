"""Lovesac StealthTech sound system integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import StealthTechCoordinator
from .repairs import async_delete_tracked_issues

PLATFORMS = [
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.SWITCH,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SELECT,
    Platform.BUTTON,
    Platform.UPDATE,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = StealthTechCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # B-LOW-2 (documented, no behavior change): an options-flow save reloads
    # the entry; if a BLE session is in flight at that moment the old
    # coordinator's session finishes against a hub object that is about to be
    # dropped. The race is bounded — the session either completes (state is
    # rebuilt by the new coordinator's first refresh anyway) or fails, and a
    # failure is absorbed by the MAX_CONSECUTIVE_FAILURES tolerance. It
    # self-heals within one poll interval, so no cross-reload sequencing is
    # attempted here.
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: StealthTechCoordinator = hass.data[DOMAIN][entry.entry_id]
        # Stop the poll timer BEFORE dropping the reference. Without this a
        # reload orphans the old coordinator's timer and two pollers then
        # fight over the hub's single BLE slot. Belt-and-braces with the
        # config_entry= binding in the coordinator (which lets the base class
        # register its own shutdown on unload); async_shutdown is idempotent.
        await coordinator.async_shutdown()
        # B-LOW-1: retract the unknown-enum Repairs issues this entry raised.
        async_delete_tracked_issues(hass, coordinator)
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
