"""v0.3 deliverable tests: update entities (D1), power-off burst guard (D2),
couch-shape select + read-scale instrumentation (D3), local overrides (D4),
Repairs nudge + prefilled issue URL (D5), response=False audit (D6a)."""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

if sys.version_info < (3, 10):
    pytest.skip("HA-layer modules require Python >= 3.10", allow_module_level=True)

import ha_stub  # noqa: F401  (installs the homeassistant stub modules)

from lovesac_stealthtech import ble, protocol as p
from lovesac_stealthtech import repairs as repairs_mod
from lovesac_stealthtech import select as select_mod
from lovesac_stealthtech import sensor as sensor_mod
from lovesac_stealthtech import update as update_mod
from lovesac_stealthtech.config_flow import StealthTechOptionsFlow
from lovesac_stealthtech.hub import StealthTechHub

PKG_DIR = Path(__file__).parent.parent / "custom_components" / "lovesac_stealthtech"


def notif(code, value):
    return bytes([0xCC, 0x05, 0xAA, code, value])


def version_notif(component, major, minor):
    return bytes([0xCC, 0x06, 0xAA, 0x01, 0x03, component, major, minor])


class FakeClient:
    def __init__(self, notifications, versions=None):
        self.notifications = notifications
        self.versions = versions or []
        self.calls = []
        self._cb = None

    async def start_notify(self, char_uuid, callback):
        self._cb = callback

    async def stop_notify(self, char_uuid):
        pass

    async def write_gatt_char(self, char_uuid, data, response=False):
        self.calls.append((char_uuid, bytes(data), response))
        if bytes(data) == p.encode_state_request().data:
            for raw in self.notifications:
                self._cb(None, bytearray(raw))
        elif bytes(data) == p.encode_version_request().data:
            for raw in self.versions:
                self._cb(None, bytearray(raw))

    async def disconnect(self):
        pass


async def run_session_with(notifications, state=None):
    state = state or p.StealthTechState()
    fake = FakeClient(notifications)

    async def connect():
        return fake

    applied = await ble.run_session(connect, state, [], idle_timeout=0.05)
    return applied, state


def fake_coordinator(**overrides):
    defaults = dict(
        address="AA:BB:CC:DD:EE:FF",
        state=p.StealthTechState(),
        config_entry=None,
        last_update_success=True,
        reported_enum_issues=set(),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def entry_with_options(**options):
    return SimpleNamespace(options=options)


# --- D1: latest-version table + update entities ------------------------------
def test_latest_versions_table_matches_libstealthtech():
    # libstealthtech characteristics.rs:268-275 (update-package numbering).
    assert p.LATEST_VERSIONS == {"mcu": (1, 71), "dsp": (1, 68), "eq": (1, 23)}
    assert p.latest_version_str("mcu") == "1.71"
    assert p.latest_version_str("nope") is None


def test_update_entities_one_per_component():
    keys = {d.key for d in update_mod.COMPONENTS}
    assert keys == {"mcu_update", "dsp_update", "eq_update"}


@pytest.mark.parametrize(
    ("key", "component", "latest"),
    [("mcu_update", "mcu", "1.71"), ("dsp_update", "dsp", "1.68"), ("eq_update", "eq", "1.23")],
)
def test_update_entity_versions(key, component, latest):
    coordinator = fake_coordinator()
    coordinator.state.versions[component] = "1.70"
    desc = next(d for d in update_mod.COMPONENTS if d.key == key)
    entity = update_mod.StealthTechUpdate(coordinator, desc)
    assert entity.installed_version == "1.70"
    assert entity.latest_version == latest
    assert entity._attr_release_url == update_mod.RELEASE_URL


def test_update_entity_none_safe_before_first_dump():
    desc = update_mod.COMPONENTS[0]
    entity = update_mod.StealthTechUpdate(fake_coordinator(), desc)
    assert entity.installed_version is None  # no versions reported yet
    assert entity.latest_version == "1.71"


def test_update_entity_has_no_install_support():
    desc = update_mod.COMPONENTS[0]
    entity = update_mod.StealthTechUpdate(fake_coordinator(), desc)
    assert entity._attr_supported_features == 0  # no INSTALL feature
    # Where updates actually happen is stated on the entity.
    assert "Lovesac mobile app" in entity.extra_state_attributes["install_note"]


# --- D2: power-off burst guard -----------------------------------------------
@pytest.mark.asyncio
async def test_power_off_burst_discards_garbage_audio_status():
    state = p.StealthTechState()
    state.volume = 10
    state.preset = p.PresetRead.MOVIES
    # Burst: power OFF (read-inverted: value 1 = off) then garbage audio/EQ.
    applied, state = await run_session_with(
        [
            notif(0x0A, 0x01),  # POWER off
            notif(0x01, 22),  # garbage volume
            notif(0x0B, 0x01),  # garbage preset (Music)
            notif(0x0E, 0x01),  # subwoofer — NOT audio/EQ, still applies
        ],
        state,
    )
    assert state.power is False
    assert state.volume == 10  # garbage discarded
    assert state.preset == p.PresetRead.MOVIES
    assert state.subwoofer_connected is True
    assert applied == 2  # power + subwoofer only


@pytest.mark.asyncio
async def test_power_on_session_applies_audio_status_normally():
    applied, state = await run_session_with(
        [notif(0x0A, 0x00), notif(0x01, 22)]  # power ON, volume 22
    )
    assert state.power is True
    assert state.volume == 22
    assert applied == 2


@pytest.mark.asyncio
async def test_burst_guard_is_session_scoped():
    _, state = await run_session_with([notif(0x0A, 0x01), notif(0x01, 22)])
    assert state.volume is None
    # Next session starts clean: audio status applies again.
    _, state = await run_session_with([notif(0x0A, 0x00), notif(0x01, 22)], state)
    assert state.volume == 22


@pytest.mark.asyncio
async def test_power_off_burst_versions_still_apply():
    state = p.StealthTechState()
    fake = FakeClient([notif(0x0A, 0x01)], versions=[version_notif(0x01, 1, 71)])

    async def connect():
        return fake

    await ble.run_session(connect, state, [], idle_timeout=0.05)
    assert state.versions == {"mcu": "1.71"}


# --- D3: couch shape ---------------------------------------------------------
@pytest.mark.parametrize(
    ("name", "value"),
    [("Straight", 0), ("L-Shape", 1), ("U-Shape", 2), ("Pit", 3)],
)
def test_encode_config_shape_frame(name, value):
    frame = p.encode_config_shape(p.COUCH_SHAPE_NAME_TO_WRITE[name])
    assert frame.char_uuid == p.CHAR_SYSTEM_LAYOUT
    assert frame.data == bytes([0xAA, 0x06, value, 0x00])


def _couch_shape_desc():
    return next(d for d in select_mod.DESCRIPTIONS if d.key == "couch_shape")


def test_couch_shape_select_shape():
    desc = _couch_shape_desc()
    assert desc.options == ["Straight", "L-Shape", "U-Shape", "Pit"]
    assert desc.optimistic is None  # calibration write: no optimistic update
    assert "RECALIBRATES" in desc.warning


def test_couch_shape_current_option_uses_shipped_read_binding():
    desc = _couch_shape_desc()
    state = p.StealthTechState()
    assert desc.current(state) is None
    state.layout = 5  # known fixed point: physical L-Shape reads raw 5
    assert desc.current(state) == "L-Shape"
    state.layout = 7  # undecoded read value → no selection shown
    assert desc.current(state) is None


@pytest.mark.asyncio
async def test_couch_shape_write_has_no_optimistic_update_and_arms_pairing():
    noted = []
    sent = []

    class FakeHub:
        def note_shape_write(self, label, write_value):
            noted.append((label, write_value))

    coordinator = fake_coordinator(hub=FakeHub())

    async def send_frames(*frames, optimistic=None):
        sent.append((frames, optimistic))

    coordinator.async_send_frames = send_frames
    entity = select_mod.StealthTechSelect(coordinator, _couch_shape_desc())
    await entity.async_select_option("Pit")
    assert noted == [("Pit", 3)]
    (frames, optimistic) = sent[0]
    assert optimistic is None  # waits for the device's Layout notification
    assert frames[0].data == bytes([0xAA, 0x06, 0x03, 0x00])
    assert entity.extra_state_attributes == {
        "warning": _couch_shape_desc().warning
    }


@pytest.mark.asyncio
async def test_shape_pairing_logged_on_layout_report(caplog):
    fake = FakeClient([notif(0x08, 5)])  # session dump reports layout raw 5

    async def connect():
        return fake

    hub = StealthTechHub(connect, idle_timeout=0.05)
    hub.note_shape_write("L-Shape", 1)
    with caplog.at_level(logging.INFO, logger="lovesac_stealthtech.hub"):
        await hub.poll()
    assert "wrote shape L-Shape (write-enum 1)" in caplog.text
    assert "layout raw 5" in caplog.text
    assert hub._pending_shape is None  # one log per write


@pytest.mark.asyncio
async def test_shape_pairing_expires_after_two_layoutless_sessions(caplog):
    def make_connect(notifs):
        fake = FakeClient(notifs)

        async def connect():
            return fake

        return connect

    hub = StealthTechHub(make_connect([notif(0x0A, 0x00)]), idle_timeout=0.05)
    hub.note_shape_write("Pit", 3)
    with caplog.at_level(logging.INFO, logger="lovesac_stealthtech.hub"):
        await hub.poll()
        await hub.poll()
        assert hub._pending_shape is None  # expired, never logged
        hub._connect = make_connect([notif(0x08, 9)])
        await hub.poll()  # layout arrives too late — no pairing log
    assert "wrote shape" not in caplog.text


# --- D4: local overrides -----------------------------------------------------
def _desc(key):
    return next(d for d in sensor_mod.DESCRIPTIONS if d.key == key)


@pytest.mark.parametrize(
    ("key", "attr", "conf"),
    [
        ("layout", "layout", "my_couch_shape"),
        ("arm_type", "arm_type", "my_arm_style"),
        ("covering", "covering", "my_fabric"),
    ],
)
def test_override_renders_when_raw_value_undecoded(key, attr, conf):
    coordinator = fake_coordinator(
        config_entry=entry_with_options(**{conf: "My Label"})
    )
    setattr(coordinator.state, attr, 0x42)
    sensor = sensor_mod.StealthTechSensor(coordinator, _desc(key))
    assert sensor.native_value == "My Label"
    assert sensor.extra_state_attributes["raw_value"] == 0x42  # attr unchanged


def test_shipped_table_takes_precedence_over_override():
    coordinator = fake_coordinator(
        config_entry=entry_with_options(my_couch_shape="Wrong Label")
    )
    coordinator.state.layout = 5  # shipped binding: L-Shape
    sensor = sensor_mod.StealthTechSensor(coordinator, _desc("layout"))
    assert sensor.native_value == "L-Shape"


def test_empty_override_falls_back_to_raw_int():
    coordinator = fake_coordinator(
        config_entry=entry_with_options(my_couch_shape="")
    )
    coordinator.state.layout = 7
    sensor = sensor_mod.StealthTechSensor(coordinator, _desc("layout"))
    assert sensor.native_value == 7


@pytest.mark.asyncio
async def test_options_flow_exposes_override_fields():
    flow = StealthTechOptionsFlow()
    flow.config_entry = entry_with_options()
    result = await flow.async_step_init(None)
    keys = {marker.key for marker in result["data_schema"].schema}
    assert {"my_couch_shape", "my_arm_style", "my_fabric"} <= keys


@pytest.mark.parametrize(
    "path", ["strings.json", "translations/en.json"], ids=["strings", "en"]
)
def test_strings_cover_new_surfaces(path):
    import json

    data = json.loads((PKG_DIR / path).read_text())
    opts = data["options"]["step"]["init"]
    for key in ("my_couch_shape", "my_arm_style", "my_fabric"):
        assert key in opts["data"]
        # Descriptions ask the operator to report the pairing upstream.
        assert "issues" in opts["data_description"][key]
    assert data["entity"]["select"]["couch_shape"]["name"] == "Couch Shape"
    assert set(data["entity"]["update"]) == {"mcu_update", "dsp_update", "eq_update"}
    assert "unknown_enum_value" in data["issues"]


# --- D5: Repairs nudge -------------------------------------------------------
@pytest.fixture(autouse=True)
def _clear_issues():
    ha_stub.created_issues.clear()
    ha_stub.deleted_issues.clear()
    yield
    ha_stub.created_issues.clear()
    ha_stub.deleted_issues.clear()


def test_unknown_enum_raises_dismissible_issue_once():
    coordinator = fake_coordinator(config_entry=entry_with_options())
    coordinator.state.layout = 7
    coordinator.state.versions["mcu"] = "1.71"
    repairs_mod.async_check_unknown_enums(None, coordinator)
    repairs_mod.async_check_unknown_enums(None, coordinator)  # dedupe
    assert len(ha_stub.created_issues) == 1
    issue = ha_stub.created_issues[0]
    assert issue["issue_id"] == "unknown_enum_layout_7"
    assert issue["is_fixable"] is False
    assert issue["severity"] == "warning"
    assert issue["translation_placeholders"] == {"kind": "layout", "value": "7"}
    url = issue["learn_more_url"]
    assert url.startswith("https://github.com/ojiudezue/ha-lovesac-stealthtech/issues/new?")
    assert "template=enum_report.yml" in url
    assert "raw_layout=7" in url
    assert "firmware_versions=mcu+1.71" in url


def test_shipped_binding_suppresses_issue():
    coordinator = fake_coordinator(config_entry=entry_with_options())
    coordinator.state.layout = 5  # in LAYOUT_NAMES
    repairs_mod.async_check_unknown_enums(None, coordinator)
    assert ha_stub.created_issues == []


def test_operator_override_suppresses_issue():
    coordinator = fake_coordinator(
        config_entry=entry_with_options(my_couch_shape="Mine")
    )
    coordinator.state.layout = 7
    repairs_mod.async_check_unknown_enums(None, coordinator)
    assert ha_stub.created_issues == []


def test_unreported_kinds_raise_nothing():
    coordinator = fake_coordinator(config_entry=entry_with_options())
    repairs_mod.async_check_unknown_enums(None, coordinator)  # all None
    assert ha_stub.created_issues == []


def test_each_kind_value_pair_gets_its_own_issue():
    coordinator = fake_coordinator(config_entry=entry_with_options())
    coordinator.state.arm_type = 2
    coordinator.state.covering = 9
    repairs_mod.async_check_unknown_enums(None, coordinator)
    ids = {i["issue_id"] for i in ha_stub.created_issues}
    assert ids == {"unknown_enum_arm_type_2", "unknown_enum_covering_9"}


def test_operator_override_retracts_previously_reported_issue():
    """A-3: setting the local override deletes the already-raised issue."""
    coordinator = fake_coordinator(config_entry=entry_with_options())
    coordinator.state.layout = 7
    repairs_mod.async_check_unknown_enums(None, coordinator)
    assert len(ha_stub.created_issues) == 1
    coordinator.config_entry = entry_with_options(my_couch_shape="Mine")
    repairs_mod.async_check_unknown_enums(None, coordinator)
    assert ha_stub.deleted_issues == [
        (repairs_mod.DOMAIN, "unknown_enum_layout_7")
    ]
    assert coordinator.reported_enum_issues == set()
    assert len(ha_stub.created_issues) == 1  # nothing re-raised


def test_shipped_binding_update_retracts_previously_reported_issue(monkeypatch):
    """A-3: a table update that now maps the value deletes the old issue."""
    coordinator = fake_coordinator(config_entry=entry_with_options())
    coordinator.state.layout = 7
    repairs_mod.async_check_unknown_enums(None, coordinator)
    assert coordinator.reported_enum_issues == {"unknown_enum_layout_7"}
    monkeypatch.setitem(p.LAYOUT_NAMES, 7, "Newly Decoded")
    repairs_mod.async_check_unknown_enums(None, coordinator)
    assert ha_stub.deleted_issues == [
        (repairs_mod.DOMAIN, "unknown_enum_layout_7")
    ]
    assert coordinator.reported_enum_issues == set()
    assert len(ha_stub.created_issues) == 1  # only the original create


def test_delete_tracked_issues_clears_everything():
    """B-LOW-1 helper: unload retracts every tracked issue."""
    coordinator = fake_coordinator(
        reported_enum_issues={"unknown_enum_layout_7", "unknown_enum_arm_type_2"}
    )
    repairs_mod.async_delete_tracked_issues(None, coordinator)
    assert set(ha_stub.deleted_issues) == {
        (repairs_mod.DOMAIN, "unknown_enum_layout_7"),
        (repairs_mod.DOMAIN, "unknown_enum_arm_type_2"),
    }
    assert coordinator.reported_enum_issues == set()


def test_issue_template_field_ids_match_repairs_urls():
    text = (
        Path(__file__).parent.parent / ".github/ISSUE_TEMPLATE/enum_report.yml"
    ).read_text()
    for field_id in ("raw_layout", "raw_arm_type", "raw_covering", "firmware_versions"):
        assert f"id: {field_id}" in text


# --- D6a: response=False audit -----------------------------------------------
def test_every_ble_write_uses_write_without_response():
    import re

    source = (PKG_DIR / "ble.py").read_text()
    # Every write_gatt_char CALL must pass response=False (the audit comment
    # in ble.py mentions response=True in prose, so match call sites only).
    calls = re.findall(r"await client\.write_gatt_char\(([^)]*)\)", source)
    assert len(calls) >= 3  # flush, version request, dump request
    for args in calls:
        assert "response=False" in args

def test_update_supported_features_is_intflag_not_bare_int():
    """Live incident 2026-07-18: HA's update.state_attributes does
    'PROGRESS in supported_features', which raises TypeError on a bare
    int. supported_features must be an IntFlag instance (empty flag)."""
    import enum
    from custom_components.lovesac_stealthtech import update as update_mod
    feats = update_mod.StealthTechUpdate._attr_supported_features
    assert isinstance(feats, enum.IntFlag)
    # HA-style membership test must not raise. Import the SAME class the
    # production module resolved via sys.modules (a direct tests.ha_stub
    # import can be a second module instance whose enum members fail
    # cross-class containment).
    from homeassistant.components.update import UpdateEntityFeature
    assert (UpdateEntityFeature.PROGRESS in feats) is False
