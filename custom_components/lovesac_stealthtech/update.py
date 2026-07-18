"""Update entities: latest known firmware per component (mcu / dsp / eq).

Informational only — there is NO install support. Firmware updates are only
deliverable through the Lovesac mobile app (no public OTA payload), so these
entities surface "an update exists" without offering to install it; the
entity attributes say so explicitly.

Latest-version table: protocol.LATEST_VERSIONS, from libstealthtech
characteristics.rs:268-275 (update-PACKAGE version numbering — see the
caveat on the table).
"""
from __future__ import annotations

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityDescription,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import protocol
from .const import DOMAIN
from .coordinator import StealthTechCoordinator
from .entity import StealthTechEntity

RELEASE_URL = "https://www.lovesac.com/stealthtech-firmware-updates"
INSTALL_NOTE = (
    "Updates can only be installed from the Lovesac mobile app — this entity "
    "is informational and offers no install action."
)

# One description per firmware component reported on the version frames.
COMPONENTS: tuple[UpdateEntityDescription, ...] = (
    UpdateEntityDescription(
        key="mcu_update",
        translation_key="mcu_update",
        device_class=UpdateDeviceClass.FIRMWARE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    UpdateEntityDescription(
        key="dsp_update",
        translation_key="dsp_update",
        device_class=UpdateDeviceClass.FIRMWARE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    UpdateEntityDescription(
        key="eq_update",
        translation_key="eq_update",
        device_class=UpdateDeviceClass.FIRMWARE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

_KEY_TO_COMPONENT = {"mcu_update": "mcu", "dsp_update": "dsp", "eq_update": "eq"}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: StealthTechCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        StealthTechUpdate(coordinator, desc) for desc in COMPONENTS
    )


class StealthTechUpdate(StealthTechEntity, UpdateEntity):
    """Informational firmware-update entity for one component.

    No UpdateEntityFeature flags are set — in particular not INSTALL — so HA
    never offers an install action (verified against core 2024.11.0
    components/update/__init__.py: async_install raises without INSTALL).
    """

    # UpdateEntityFeature(0): HA's state_attributes does membership tests
    # ("PROGRESS in supported_features") which require the IntFlag type —
    # a bare int raises TypeError at entity-add on HA 2025+ (seen live
    # 2026-07-18 on 2026.7). Empty flag = no install support, as intended.
    _attr_supported_features = UpdateEntityFeature(0)  # deliberately no INSTALL
    _attr_release_url = RELEASE_URL

    def __init__(
        self,
        coordinator: StealthTechCoordinator,
        description: UpdateEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._component = _KEY_TO_COMPONENT[description.key]
        self._attr_unique_id = f"{coordinator.address}_{description.key}"

    @property
    def installed_version(self) -> str | None:
        # None-safe pre-first-dump: versions dict is empty until the first
        # successful version request.
        return self.coordinator.state.versions.get(self._component)

    @property
    def latest_version(self) -> str | None:
        return protocol.latest_version_str(self._component)

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        return {"install_note": INSTALL_NOTE}
