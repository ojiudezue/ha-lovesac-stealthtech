"""Minimal Home Assistant stub for testing the HA-facing layer without an
HA install.

Models the surface the integration actually touches, pinned to HA >= 2024.11
behavior: `DataUpdateCoordinator` accepts an explicit `config_entry` keyword
(added in core 2024.11.0; required from 2025.11 per core issue #128077).
Import this module BEFORE importing any `lovesac_stealthtech` HA-layer
module; it installs stub modules into sys.modules.
"""
from __future__ import annotations

import sys
import types
from dataclasses import dataclass


class _Undefined:
    pass


UNDEFINED = _Undefined()


def _module(name: str) -> types.ModuleType:
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


# --- homeassistant.config_entries -------------------------------------------
class ConfigEntry:
    def __init__(self, *, entry_id="test-entry", data=None, options=None):
        self.entry_id = entry_id
        self.data = data or {}
        self.options = options or {}

    def add_update_listener(self, listener):
        return lambda: None

    def async_on_unload(self, func):
        return None


# --- homeassistant.const ----------------------------------------------------
class Platform:
    MEDIA_PLAYER = "media_player"
    NUMBER = "number"
    SWITCH = "switch"
    BINARY_SENSOR = "binary_sensor"
    SENSOR = "sensor"
    SELECT = "select"
    BUTTON = "button"
    UPDATE = "update"


# --- homeassistant.core -----------------------------------------------------
class HomeAssistant:
    def __init__(self):
        self.data = {}


# --- homeassistant.helpers.update_coordinator -------------------------------
class UpdateFailed(Exception):
    pass


class DataUpdateCoordinator:
    """Stub modeling the >= 2024.11 signature: explicit config_entry kwarg."""

    def __class_getitem__(cls, item):
        return cls

    def __init__(
        self,
        hass,
        logger,
        *,
        name=None,
        update_interval=None,
        config_entry=UNDEFINED,
        always_update=True,
    ):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval
        self.received_explicit_config_entry = config_entry is not UNDEFINED
        self.config_entry = None if config_entry is UNDEFINED else config_entry
        self.always_update = always_update
        self.last_update_success = True
        self.shutdown_calls = 0

    async def async_shutdown(self):
        self.shutdown_calls += 1

    async def async_config_entry_first_refresh(self):
        pass

    async def async_request_refresh(self):
        pass

    def async_update_listeners(self):
        pass


class CoordinatorEntity:
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, coordinator, context=None):
        self.coordinator = coordinator

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success


# --- homeassistant.helpers.entity / entity_platform / device_registry -------
class EntityCategory:
    CONFIG = "config"
    DIAGNOSTIC = "diagnostic"


AddEntitiesCallback = object
CONNECTION_BLUETOOTH = "bluetooth"


class DeviceInfo(dict):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


# --- homeassistant.components.binary_sensor / sensor ------------------------
class BinarySensorDeviceClass:
    CONNECTIVITY = "connectivity"


class BinarySensorEntity:
    pass


class SensorDeviceClass:
    TIMESTAMP = "timestamp"


@dataclass(frozen=True, kw_only=True)
class SensorEntityDescription:
    key: str
    translation_key: str | None = None
    entity_category: str | None = None
    device_class: str | None = None
    icon: str | None = None


class SensorEntity:
    pass


# --- homeassistant.components.select ----------------------------------------
@dataclass(frozen=True, kw_only=True)
class SelectEntityDescription:
    key: str
    translation_key: str | None = None
    entity_category: str | None = None
    icon: str | None = None
    options: list | None = None


class SelectEntity:
    pass


# --- homeassistant.components.update ----------------------------------------
class UpdateDeviceClass:
    FIRMWARE = "firmware"


@dataclass(frozen=True, kw_only=True)
class UpdateEntityDescription:
    key: str
    translation_key: str | None = None
    entity_category: str | None = None
    device_class: str | None = None


class UpdateEntity:
    pass


# --- homeassistant.helpers.issue_registry ------------------------------------
class IssueSeverity:
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"


created_issues: list[dict] = []
deleted_issues: list[tuple] = []


def async_create_issue(
    hass,
    domain,
    issue_id,
    *,
    breaks_in_ha_version=None,
    data=None,
    is_fixable,
    is_persistent=False,
    issue_domain=None,
    learn_more_url=None,
    severity,
    translation_key,
    translation_placeholders=None,
):
    """Signature mirrors HA core 2024.11.0 helpers/issue_registry.py so a
    kwarg typo in the integration fails these tests."""
    created_issues.append(
        {
            "domain": domain,
            "issue_id": issue_id,
            "is_fixable": is_fixable,
            "severity": severity,
            "translation_key": translation_key,
            "translation_placeholders": translation_placeholders,
            "learn_more_url": learn_more_url,
        }
    )


def async_delete_issue(hass, domain, issue_id):
    """Signature mirrors HA core 2024.11.0 helpers/issue_registry.py
    (positional hass, domain, issue_id)."""
    deleted_issues.append((domain, issue_id))


# --- homeassistant.config_entries flow surface + voluptuous ------------------
class ConfigFlow:
    """Stub: accepts the domain= class keyword like the real base."""

    def __init_subclass__(cls, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._domain = domain


class OptionsFlow:
    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}


ConfigFlowResult = dict


def ha_callback(func):
    return func


class BluetoothServiceInfoBleak:
    pass


class _VolMarker:
    def __init__(self, key, default=None):
        self.key = key
        self.default = default

    def __hash__(self):
        return hash(self.key)

    def __eq__(self, other):
        return getattr(other, "key", other) == self.key


class _Voluptuous(types.ModuleType):
    class Schema:
        def __init__(self, schema):
            self.schema = schema

    Required = _VolMarker
    Optional = _VolMarker

    @staticmethod
    def All(*validators):
        return validators

    @staticmethod
    def Range(min=None, max=None):
        return ("range", min, max)

    @staticmethod
    def Coerce(t):
        return t


# --- homeassistant.components.bluetooth / bleak_retry_connector -------------
def async_ble_device_from_address(hass, address, connectable=True):
    return None


class BleakClientWithServiceCache:
    pass


async def establish_connection(klass, device, address):
    raise NotImplementedError


def install() -> None:
    ha = _module("homeassistant")
    ce = _module("homeassistant.config_entries")
    ce.ConfigEntry = ConfigEntry
    ce.ConfigFlow = ConfigFlow
    ce.ConfigFlowResult = ConfigFlowResult
    ce.OptionsFlow = OptionsFlow
    const = _module("homeassistant.const")
    const.Platform = Platform
    core = _module("homeassistant.core")
    core.HomeAssistant = HomeAssistant
    core.callback = ha_callback

    helpers = _module("homeassistant.helpers")
    uc = _module("homeassistant.helpers.update_coordinator")
    uc.DataUpdateCoordinator = DataUpdateCoordinator
    uc.CoordinatorEntity = CoordinatorEntity
    uc.UpdateFailed = UpdateFailed
    entity = _module("homeassistant.helpers.entity")
    entity.EntityCategory = EntityCategory
    ep = _module("homeassistant.helpers.entity_platform")
    ep.AddEntitiesCallback = AddEntitiesCallback
    dr = _module("homeassistant.helpers.device_registry")
    dr.CONNECTION_BLUETOOTH = CONNECTION_BLUETOOTH
    dr.DeviceInfo = DeviceInfo

    components = _module("homeassistant.components")
    bt = _module("homeassistant.components.bluetooth")
    bt.async_ble_device_from_address = async_ble_device_from_address
    bt.BluetoothServiceInfoBleak = BluetoothServiceInfoBleak
    if "voluptuous" not in sys.modules:
        sys.modules["voluptuous"] = _Voluptuous("voluptuous")
    bs = _module("homeassistant.components.binary_sensor")
    bs.BinarySensorDeviceClass = BinarySensorDeviceClass
    bs.BinarySensorEntity = BinarySensorEntity
    sensor = _module("homeassistant.components.sensor")
    sensor.SensorDeviceClass = SensorDeviceClass
    sensor.SensorEntity = SensorEntity
    sensor.SensorEntityDescription = SensorEntityDescription
    select = _module("homeassistant.components.select")
    select.SelectEntity = SelectEntity
    select.SelectEntityDescription = SelectEntityDescription
    update = _module("homeassistant.components.update")
    update.UpdateDeviceClass = UpdateDeviceClass
    update.UpdateEntity = UpdateEntity
    update.UpdateEntityDescription = UpdateEntityDescription
    ir = _module("homeassistant.helpers.issue_registry")
    ir.IssueSeverity = IssueSeverity
    ir.async_create_issue = async_create_issue
    ir.async_delete_issue = async_delete_issue
    helpers.issue_registry = ir

    ha.config_entries = ce
    ha.const = const
    ha.core = core
    ha.helpers = helpers
    ha.components = components

    brc = _module("bleak_retry_connector")
    brc.BleakClientWithServiceCache = BleakClientWithServiceCache
    brc.establish_connection = establish_connection


install()
