"""HA-layer tests against the stub in ha_stub.py.

Covers the v0.2 review ledger's HA-facing fixes:
- B1: unload shuts the coordinator down (poll timer cannot orphan across a
  reload and double-book the hub's single BLE slot), and the coordinator
  passes config_entry= explicitly to DataUpdateCoordinator.
- A-MED-1: control_link binary sensor and last_contact sensor stay available
  through sustained failures.
- B4: control_link reason attribute maps through from the hub.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

if sys.version_info < (3, 10):
    # The HA-facing modules use kw_only dataclasses (py>=3.10), matching the
    # real HA runtime (>=3.12). Pure-layer tests still run on older pythons.
    pytest.skip("HA-layer modules require Python >= 3.10", allow_module_level=True)

import ha_stub  # noqa: F401  (installs the homeassistant stub modules)

from lovesac_stealthtech import binary_sensor as bs_mod
from lovesac_stealthtech import sensor as sensor_mod
from lovesac_stealthtech.const import DOMAIN
from lovesac_stealthtech.coordinator import StealthTechCoordinator
from lovesac_stealthtech.hub import (
    LINK_REASON_CONNECT_FAILED,
    LINK_REASON_NO_DATA,
)
from lovesac_stealthtech.protocol import StealthTechState

PKG_DIR = Path(__file__).parent.parent / "custom_components" / "lovesac_stealthtech"


def _load_integration_init():
    """Load __init__.py under the package (conftest registers the package
    without executing it, so the HA-importing module is loaded explicitly)."""
    spec = importlib.util.spec_from_file_location(
        "lovesac_stealthtech._integration_init", PKG_DIR / "__init__.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # required for its relative imports
    spec.loader.exec_module(module)
    return module


integration = _load_integration_init()


def make_entry(entry_id="e1"):
    return ha_stub.ConfigEntry(
        entry_id=entry_id, data={"address": "AA:BB:CC:DD:EE:FF"}, options={}
    )


# --- B1 ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unload_shuts_down_coordinator_before_dropping_it():
    entry = make_entry()
    events: list[str] = []
    hass = ha_stub.HomeAssistant()

    class SpyCoordinator:
        async def async_shutdown(self):
            events.append("shutdown")
            # Reference must still be held at shutdown time (pop comes after).
            assert entry.entry_id in hass.data[DOMAIN]

    hass.data[DOMAIN] = {entry.entry_id: SpyCoordinator()}

    async def unload_platforms(e, platforms):
        events.append("unload_platforms")
        assert platforms == integration.PLATFORMS
        return True

    hass.config_entries = SimpleNamespace(async_unload_platforms=unload_platforms)

    assert await integration.async_unload_entry(hass, entry) is True
    assert events == ["unload_platforms", "shutdown"]
    assert entry.entry_id not in hass.data[DOMAIN]


@pytest.mark.asyncio
async def test_failed_platform_unload_keeps_coordinator_running():
    entry = make_entry()
    hass = ha_stub.HomeAssistant()

    class SpyCoordinator:
        async def async_shutdown(self):
            raise AssertionError("must not shut down on failed unload")

    hass.data[DOMAIN] = {entry.entry_id: SpyCoordinator()}

    async def unload_platforms(e, platforms):
        return False

    hass.config_entries = SimpleNamespace(async_unload_platforms=unload_platforms)

    assert await integration.async_unload_entry(hass, entry) is False
    assert entry.entry_id in hass.data[DOMAIN]


def test_coordinator_passes_config_entry_explicitly():
    """B1 belt two: the base class receives config_entry= so it can bind the
    coordinator (and register its own shutdown) to the entry lifecycle."""
    entry = make_entry()
    coordinator = StealthTechCoordinator(ha_stub.HomeAssistant(), entry)
    assert coordinator.received_explicit_config_entry is True
    assert coordinator.config_entry is entry


# --- A-MED-1 + B4 -----------------------------------------------------------
def fake_coordinator(**overrides):
    defaults = dict(
        address="AA:BB:CC:DD:EE:FF",
        state=StealthTechState(),
        link_ok=False,
        link_reason=LINK_REASON_CONNECT_FAILED,
        last_contact=None,
        last_update_success=False,  # sustained-outage shape
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_control_link_sensor_available_during_sustained_outage():
    sensor = bs_mod.StealthTechControlLinkSensor(fake_coordinator())
    assert sensor.available is True
    assert sensor.is_on is False
    assert sensor.extra_state_attributes == {"reason": LINK_REASON_CONNECT_FAILED}


def test_control_link_reason_maps_silent_session():
    sensor = bs_mod.StealthTechControlLinkSensor(
        fake_coordinator(link_reason=LINK_REASON_NO_DATA)
    )
    assert sensor.extra_state_attributes == {"reason": LINK_REASON_NO_DATA}


def test_control_link_no_reason_attr_when_link_ok():
    sensor = bs_mod.StealthTechControlLinkSensor(
        fake_coordinator(link_ok=True, link_reason=None, last_update_success=True)
    )
    assert sensor.extra_state_attributes is None


def test_subwoofer_sensor_still_follows_coordinator_availability():
    sensor = bs_mod.StealthTechSubwooferSensor(fake_coordinator())
    assert sensor.available is False  # only the two outage reporters override


def _desc(key: str) -> sensor_mod.StealthTechSensorDescription:
    return next(d for d in sensor_mod.DESCRIPTIONS if d.key == key)


def test_last_contact_sensor_available_during_sustained_outage():
    sensor = sensor_mod.StealthTechSensor(fake_coordinator(), _desc("last_contact"))
    assert _desc("last_contact").always_available is True
    assert sensor.available is True


def test_other_sensors_follow_coordinator_availability():
    sensor = sensor_mod.StealthTechSensor(fake_coordinator(), _desc("mcu_firmware"))
    assert sensor.available is False


# --- v0.2.2: icons ----------------------------------------------------------
EXPECTED_ICONS = {
    "input": "mdi:video-input-hdmi",
    "audio_capability": "mdi:surround-sound",
    "mcu_firmware": "mdi:chip",
    "dsp_firmware": "mdi:chip",
    "eq_firmware": "mdi:chip",
    "layout": "mdi:floor-plan",
    "covering": "mdi:texture-box",
    "arm_type": "mdi:sofa-single-outline",
    # last_contact keeps the timestamp device-class default icon on purpose.
    "last_contact": None,
}


def test_sensor_icons_match_expected_table():
    assert {d.key: d.icon for d in sensor_mod.DESCRIPTIONS} == EXPECTED_ICONS


# --- v0.2.2: renames (strings.json + en.json in lockstep) -------------------
@pytest.mark.parametrize(
    "path", ["strings.json", "translations/en.json"], ids=["strings", "en"]
)
def test_entity_renames(path):
    import json

    data = json.loads((PKG_DIR / path).read_text())
    entity = data["entity"]
    assert entity["sensor"]["arm_type"]["name"] == "Couch Arm Type (raw)"
    assert entity["sensor"]["covering"]["name"] == "Couch Cover (raw)"
    assert entity["binary_sensor"]["subwoofer"]["name"] == "Subwoofer link"


def test_strings_and_en_translation_identical():
    assert (PKG_DIR / "strings.json").read_text() == (
        PKG_DIR / "translations/en.json"
    ).read_text()


# --- v0.2.2: enum-map mechanism ---------------------------------------------
from lovesac_stealthtech import protocol  # noqa: E402


@pytest.mark.parametrize(
    ("key", "attr", "names"),
    [
        ("layout", "layout", "LAYOUT_NAMES"),
        ("covering", "covering", "COVERING_NAMES"),
        ("arm_type", "arm_type", "ARM_TYPE_NAMES"),
    ],
)
def test_raw_enum_unmapped_renders_int_with_raw_value_attr(key, attr, names):
    coordinator = fake_coordinator()
    setattr(coordinator.state, attr, 0x42)
    sensor = sensor_mod.StealthTechSensor(coordinator, _desc(key))
    assert sensor.native_value == 0x42  # maps ship empty; raw int shows
    attrs = sensor.extra_state_attributes
    assert attrs["raw_value"] == 0x42
    assert "issues" in attrs["decoding"]  # points at the issue tracker


@pytest.mark.parametrize(
    ("key", "attr", "names"),
    [
        ("layout", "layout", "LAYOUT_NAMES"),
        ("covering", "covering", "COVERING_NAMES"),
        ("arm_type", "arm_type", "ARM_TYPE_NAMES"),
    ],
)
def test_raw_enum_mapped_renders_name_keeps_raw_attr(key, attr, names, monkeypatch):
    monkeypatch.setitem(getattr(protocol, names), 3, "Test Name")
    coordinator = fake_coordinator()
    setattr(coordinator.state, attr, 3)
    sensor = sensor_mod.StealthTechSensor(coordinator, _desc(key))
    assert sensor.native_value == "Test Name"
    assert sensor.extra_state_attributes["raw_value"] == 3


def test_enum_name_maps_hold_only_confirmed_bindings():
    # Every entry must be an owner-confirmed empirical binding with a
    # provenance comment in protocol.py. First binding landed 2026-07-18:
    # layout raw 5 = L-Shape.
    assert protocol.LAYOUT_NAMES == {5: "L-Shape"}
    assert protocol.ARM_TYPE_NAMES == {}
    assert protocol.COVERING_NAMES == {}


def test_raw_enum_none_stays_none():
    sensor = sensor_mod.StealthTechSensor(fake_coordinator(), _desc("layout"))
    assert sensor.native_value is None
    assert sensor.extra_state_attributes["raw_value"] is None
